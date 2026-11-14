"""TASK-012: persisted Lens. Oracles: Source recomputation + a Python dict."""
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opdb import PersistentTruthStore, SourceIntegrityError, TruthStore

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ["a", "b", "c", "", "g/x", "é"]


def model_stats(model):
    out = {}
    for k, v in model.items():
        g = k.split("/", 1)[0]
        n, b = out.get(g, (0, 0))
        out[g] = (n + 1, b + len(v))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "db.sqlite")

    def check(self, store, model, mode=None):
        exp = model_stats(model)
        for g in set(GROUPS) | set(exp):
            ref = store.group_stats_source(g)
            got = store.group_stats(g)
            self.assertEqual((got.row_count, got.value_bytes),
                             (ref.row_count, ref.value_bytes), g)
            self.assertEqual((got.row_count, got.value_bytes), exp.get(g, (0, 0)), g)
            if mode:
                self.assertEqual(got.served_from, mode)

    def raw(self, sql, args=()):
        con = sqlite3.connect(self.path)
        try:
            con.execute(sql, args)
            con.commit()
        finally:
            con.close()


class Oracle(Base):
    def test_20_seeds_with_reopen(self):
        for seed in range(20):
            path = f"{self.path}.{seed}"
            self.path = path
            rnd, model = random.Random(seed), {}
            store = PersistentTruthStore(path)
            for step in range(25):
                ops = []
                for _ in range(rnd.randint(1, 12)):
                    key = rnd.choice(GROUPS) + rnd.choice(["", "/1", "/2", "/3/4"])
                    if not key:
                        key = "k"
                    if rnd.random() < 0.35:
                        ops.append(("delete", key)); model.pop(key, None)
                    else:
                        val = bytes(rnd.randint(0, 9) for _ in range(rnd.choice([0, 0, 1, 5, 40])))
                        ops.append(("put", key, val)); model[key] = val
                store.apply(ops)
                if step % 8 == 7:
                    store.close()
                    store = PersistentTruthStore(path)
                    self.assertEqual(store.open_mode, "PERSISTED", seed)
                self.check(store, model, "LENS")
            store.close()

    def test_failed_validation_changes_nothing(self):
        with PersistentTruthStore(self.path) as s:
            s.put("a/1", b"xx")
            with self.assertRaises(ValueError):
                s.apply([("put", "a/2", b"y"), ("put", "a/3", "not bytes")])
            self.check(s, {"a/1": b"xx"}, "LENS")


class Atomicity(Base):
    def child(self, when):
        code = f"""
import os, sys
from opdb import PersistentTruthStore
s = PersistentTruthStore({self.path!r})
def t(sql):
    if {when!r} == 'before' and sql.strip().upper().startswith('COMMIT'):
        os._exit(7)
s._db.set_trace_callback(t)
s.apply([('put','a/1',b'new'),('put','b/9',b'zz'),('delete','a/0')])
os._exit(8)
"""
        return subprocess.run([sys.executable, "-c", code], cwd=ROOT).returncode

    def test_kill_before_and_after_commit(self):
        old = {"a/0": b"1", "a/5": b"22"}
        with PersistentTruthStore(self.path) as s:
            s.apply([("put", k, v) for k, v in old.items()])
        self.assertEqual(self.child("before"), 7)
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "PERSISTED")   # old, consistent
            self.check(s, old, "LENS")
        self.assertEqual(self.child("after"), 8)
        new = {"a/5": b"22", "a/1": b"new", "b/9": b"zz"}
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "PERSISTED")   # new, consistent
            self.check(s, new, "LENS")

    def test_injected_errors_roll_back_and_retry(self):
        class Boom:
            def __init__(self, db, needle): self.db, self.needle, self.armed = db, needle, True
            def execute(self, sql, *a):
                if self.armed and self.needle in sql:
                    self.armed = False
                    raise sqlite3.OperationalError("injected")
                return self.db.execute(sql, *a)
            def __getattr__(self, name): return getattr(self.db, name)
        for needle in ("INSERT INTO opdb_source_kv", "UPDATE opdb_meta SET commit_seq",
                       "INSERT INTO opdb_lens_group", "UPDATE opdb_lens_meta"):
            self.path = f"{self.tmp.name}/{abs(hash(needle))}.db"
            s = PersistentTruthStore(self.path)
            s.apply([("put", "a/1", b"1")])
            real = s._db
            s._db = Boom(real, needle)
            ops = [("put", "a/2", b"22"), ("put", "z/1", b"")]
            with self.assertRaises(sqlite3.OperationalError):
                s.apply(ops)
            s._db = real
            self.check(s, {"a/1": b"1"})          # both old
            s.apply(ops)                           # retry works
            self.check(s, {"a/1": b"1", "a/2": b"22", "z/1": b""}, "LENS")
            s.close()
            with PersistentTruthStore(self.path) as r:
                self.assertEqual(r.open_mode, "PERSISTED")
                self.check(r, {"a/1": b"1", "a/2": b"22", "z/1": b""}, "LENS")


class StaleAndDamage(Base):
    MODEL = {"a/1": b"11", "a/2": b"", "b/1": b"333"}

    def seed(self):
        with PersistentTruthStore(self.path) as s:
            s.apply([("put", k, v) for k, v in self.MODEL.items()])

    def reopen_ok(self, reason_part):
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "REBUILT")
            self.assertIn(reason_part, s.open_reason)
            self.check(s, self.MODEL, "LENS")
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "PERSISTED")

    def test_tampered_aggregate(self):
        self.seed(); self.raw("UPDATE opdb_lens_group SET n=n+1 WHERE g='a'")
        self.reopen_ok("totals")

    def test_missing_lens_row(self):
        self.seed(); self.raw("DELETE FROM opdb_lens_group WHERE g='b'")
        self.reopen_ok("totals")

    def test_corrupt_lens_row(self):
        self.seed(); self.raw("UPDATE opdb_lens_group SET b='x' WHERE g='a'")
        self.reopen_ok("")

    def test_metadata_damage(self):
        self.seed(); self.raw("UPDATE opdb_lens_meta SET schema_version=99")
        self.reopen_ok("schema")
        self.raw("DELETE FROM opdb_lens_meta")
        self.reopen_ok("missing")

    def test_plain_store_write_makes_generation_stale(self):
        self.seed()
        with TruthStore(self.path) as plain:
            plain.put("a/7", b"7777")
        self.MODEL = {**self.MODEL, "a/7": b"7777"}
        self.reopen_ok("stale")

    def test_foreign_writes_while_open_are_caught(self):
        self.seed()
        s = PersistentTruthStore(self.path)
        other = PersistentTruthStore(self.path)        # second store, same file
        other.put("a/9", b"9")
        s.put("b/2", b"22")
        model = {**self.MODEL, "a/9": b"9", "b/2": b"22"}
        self.check(s, model, "LENS"); self.check(other, model, "LENS")
        self.raw("INSERT INTO opdb_source_kv VALUES ('c/1', x'0102')")  # raw SQL
        model["c/1"] = b"\x01\x02"
        self.check(s, model, "LENS")
        # sum-preserving tamper while open: totals still match, data_version differs
        self.raw("UPDATE opdb_lens_group SET n=n+1 WHERE g='a'")
        self.raw("UPDATE opdb_lens_group SET n=n-1 WHERE g='b'")
        self.check(s, model, "LENS")
        s.close(); other.close()

    def test_interrupted_and_repeated_rebuild(self):
        self.seed(); self.raw("UPDATE opdb_lens_group SET n=n+1 WHERE g='a'")
        class Boom:
            def __init__(self, db): self.db = db
            def execute(self, sql, *a):
                if sql.startswith("INSERT OR REPLACE INTO opdb_lens_meta"):
                    raise sqlite3.OperationalError("injected")
                return self.db.execute(sql, *a)
            def __getattr__(self, name): return getattr(self.db, name)
        s = PersistentTruthStore(self.path)           # healthy open path: rebuilt
        s._db = Boom(s._db)
        with self.assertRaises(sqlite3.OperationalError):
            s.rebuild()
        s._db = s._db.db
        self.assertFalse(s._trusted)
        self.check(s, self.MODEL)                     # fell back / repaired, correct
        s.close()
        for _ in range(3):
            with PersistentTruthStore(self.path) as r:
                r.rebuild(); r.rebuild()
                self.check(r, self.MODEL, "LENS")

    def test_invalid_source_fails_closed(self):
        self.seed(); self.raw("UPDATE opdb_source_kv SET v=5 WHERE k='a/1'")
        self.raw("DELETE FROM opdb_lens_meta")
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "SOURCE_FALLBACK")
            self.assertFalse(s.lens_enabled)
            with self.assertRaises(SourceIntegrityError):
                s.group_stats("a")

    def test_documented_boundary_closed_raw_write_not_detected(self):
        """Pins the threat boundary in docs/M3_PERSISTENT_LENS.md: a raw SQL
        write to Source while NO store is open touches neither commit_seq nor
        the Lens, so a bounded open cannot see it. Not a guarantee; a change
        here must be a deliberate, owner-approved decision."""
        self.seed()
        self.raw("INSERT INTO opdb_source_kv VALUES ('a/99', x'01')")
        with PersistentTruthStore(self.path) as s:
            self.assertEqual(s.open_mode, "PERSISTED")
            self.assertNotEqual(s.group_stats("a").row_count,
                                s.group_stats_source("a").row_count)


class ColdOpen(Base):
    def test_one_million_rows_no_source_scan(self):
        rows = int(os.environ.get("OPDB_M3_ROWS", "1000000"))
        s = PersistentTruthStore(self.path)
        s.close()
        con = sqlite3.connect(self.path)
        con.executemany("INSERT INTO opdb_source_kv VALUES (?,?)",
                        ((f"g{i % 1000}/{i}", b"v" * (i % 7)) for i in range(rows)))
        con.commit(); con.close()
        s = PersistentTruthStore(self.path)           # raw rows are invisible to a
        s.rebuild(); s.close()                        # bounded open: explicit rebuild scans
        seen = []
        s = PersistentTruthStore(self.path, trace=seen.append)
        self.assertEqual(s.open_mode, "PERSISTED")
        self.assertFalse([q for q in seen if "opdb_source_kv" in q], seen)
        self.assertLess(s.open_vm_steps, 50000)       # a scan costs millions
        for g in (0, 17, 999):
            exp_n = sum(1 for i in range(g, rows, 1000))
            exp_b = sum(i % 7 for i in range(g, rows, 1000))
            got = s.group_stats(f"g{g}")
            self.assertEqual((got.row_count, got.value_bytes, got.served_from),
                             (exp_n, exp_b, "LENS"))
        self.assertEqual(s.group_stats("none").row_count, 0)
        s.close()


if __name__ == "__main__":
    unittest.main()
