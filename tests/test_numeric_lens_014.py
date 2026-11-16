"""TASK-014: numeric Lens. Oracles: (a) fresh SQL connection over Source and
(b) a plain Python dict model; neither uses the code under test."""
import os
import random
import sqlite3
import tempfile
import unittest

from opdb import NumericTruthStore, SourceIntegrityError

GROUPS = ["a", "b", "é", "日本", "", "g/x"] + [f"grp{i}" for i in range(30)]
EDGE = [0, 1, -1, 5, 5, -5, 2**62, -2**62, 2**63 - 1, -2**63]


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def model_stats(model, fn=gof):
    out = {}
    for k, x in model.items():
        out.setdefault(fn(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


def sql_stats(path):
    """Independent SQL recomputation: group by a SQL expression, decode in Python."""
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT substr(k,1,instr(k||'/','/')-1), v FROM opdb_source_kv").fetchall()
    finally:
        con.close()
    out = {}
    for g, v in rows:
        out.setdefault(g, []).append(int.from_bytes(v, "big", signed=True))
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


class NumericLens(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "n.db")

    def check(self, store, model, path=None):
        exp = model_stats(model)
        self.assertEqual(exp, sql_stats(path or self.path))
        for g in set(exp) | {"zzz", "a", "b"}:
            got = store.numeric_stats(g)
            ref = store.numeric_stats_source(g)
            want = exp.get(g, (0, 0, None, None))
            self.assertEqual(got.served_from, "LENS", g)
            self.assertEqual((got.count, got.total, got.minimum, got.maximum), want, g)
            self.assertEqual((ref.count, ref.total, ref.minimum, ref.maximum), want, g)
        src = {k: int.from_bytes(v, "big", signed=True) for k, v in
               store._db.execute("SELECT k,v FROM opdb_source_kv")}
        self.assertEqual(src, model)
        idx = {k: x for g, x, k in store._db.execute("SELECT g,x,k FROM opdb_nlens_val")}
        self.assertEqual(idx, model)                     # value index has no stray rows

    def test_25_seeds_random_batches_and_reopen(self):
        for seed in range(25):
            path = os.path.join(self.tmp.name, f"s{seed}.db")
            rnd, model = random.Random(seed), {}
            store = NumericTruthStore(path)
            for step in range(8):
                ops = []
                for _ in range(rnd.choice([1, 3, 40, 299, 300, 301, 700])):
                    key = rnd.choice(GROUPS) + rnd.choice(["/1", "/2", "/3/4", "/k%d" % rnd.randint(0, 40)])
                    r = rnd.random()
                    if r < 0.3:
                        ops.append(("delete", key)); model.pop(key, None)
                    else:
                        x = rnd.choice(EDGE[:6] + [rnd.randint(-9, 9), rnd.randint(-10**9, 10**9)])
                        ops.append(("put", key, enc(x))); model[key] = x
                store.apply(ops)
                self.check(store, model, path)
            store.close()
            store = NumericTruthStore(path)
            self.assertEqual(store.open_mode, "PERSISTED", seed)
            self.check(store, model, path)
            store.close()

    def test_delete_only_extreme_ties_and_empty_group(self):
        s = NumericTruthStore(self.path)
        s.apply([("put", "g/a", enc(7)), ("put", "g/b", enc(7)), ("put", "g/c", enc(-3)),
                 ("put", "h/a", enc(0))])
        s.delete("g/c")                                   # only minimum
        st = s.numeric_stats("g")
        self.assertEqual((st.count, st.total, st.minimum, st.maximum), (2, 14, 7, 7))
        s.delete("g/a")                                   # tie: other copy remains
        self.assertEqual(s.numeric_stats("g").maximum, 7)
        s.put("g/b", enc(-100))                           # overwrite the extreme
        st = s.numeric_stats("g")
        self.assertEqual((st.minimum, st.maximum, st.total), (-100, -100, -100))
        s.delete("g/b")                                   # group becomes empty
        st = s.numeric_stats("g")
        self.assertEqual((st.count, st.total, st.minimum, st.maximum, st.served_from),
                         (0, 0, None, None, "LENS"))
        self.assertEqual(s._db.execute(
            "SELECT count(*) FROM opdb_nlens_group WHERE g='g'").fetchone()[0], 0)
        s.apply([("put", "g/z", enc(4)), ("put", "g/z", enc(9)), ("delete", "g/z"),
                 ("put", "g/z", enc(2))])                 # repeated key in one batch
        self.assertEqual(s.numeric_stats("g").total, 2)
        s.close()

    def test_wrong_width_and_type_rejected_without_effect(self):
        s = NumericTruthStore(self.path)
        s.put("a/1", enc(1))
        for bad in (b"", b"1234567", b"123456789"):
            with self.assertRaises(ValueError):
                s.apply([("put", "a/2", enc(5)), ("put", "a/3", bad)])
        with self.assertRaises(ValueError):
            s.apply([("put", "a/4", "text")])
        self.assertEqual(s.get("a/2"), None)
        self.assertEqual(s.numeric_stats("a").count, 1)
        s.close()

    def test_overflow_falls_back_to_source_python_ints(self):
        s = NumericTruthStore(self.path)
        s.apply([("put", "o/1", enc(2**63 - 1)), ("put", "p/1", enc(3))])
        s.put("o/2", enc(5))                              # sum > int64 max
        st = s.numeric_stats("o")
        self.assertEqual((st.served_from, st.total), ("SOURCE", 2**63 + 4))
        self.assertEqual(s.numeric_stats("p").total, 3)   # still correct
        s.put("p/2", enc(4))
        self.assertEqual(s.numeric_stats("p").total, 7)
        s.delete("o/2")                                   # back in range
        st = s.numeric_stats("o")
        self.assertEqual((st.total, st.minimum, st.maximum), (2**63 - 1, 2**63 - 1, 2**63 - 1))
        self.assertEqual(st.served_from, "LENS")
        s.put("o/3", enc(1))
        s.close()
        s = NumericTruthStore(self.path)                  # reopen with overflow present
        self.assertEqual(s.open_mode, "SOURCE_FALLBACK")
        self.assertEqual(s.numeric_stats("o").total, 2**63)
        s.delete("o/3")
        self.assertEqual(s.numeric_stats("o").served_from, "LENS")
        s.close()
        s = NumericTruthStore(self.path)
        self.assertEqual(s.open_mode, "PERSISTED")        # rebuilt when it fit again
        s.close()

    def test_negative_overflow(self):
        s = NumericTruthStore(self.path)
        s.apply([("put", "n/1", enc(-2**63)), ("put", "n/2", enc(-1))])
        st = s.numeric_stats("n")
        self.assertEqual((st.served_from, st.total, st.minimum), ("SOURCE", -2**63 - 1, -2**63))
        s.close()

    def test_grouping_name_mismatch_rebuilds(self):
        by_len = lambda k: str(len(k))
        s = NumericTruthStore(self.path, groupers={"len": by_len}, grouping="len")
        s.apply([("put", "ab", enc(1)), ("put", "cd", enc(2)), ("put", "xyz", enc(9))])
        self.assertEqual(s.numeric_stats("2").total, 3)
        s.close()
        s = NumericTruthStore(self.path)                  # default "prefix"
        self.assertEqual(s.open_mode, "REBUILT")
        self.assertIn("grouping", s.open_reason)
        self.assertEqual(s.numeric_stats("ab").total, 1)
        self.assertEqual(s.numeric_stats("2").count, 0)
        s.close()
        s = NumericTruthStore(self.path, groupers={"len": by_len}, grouping="len")
        self.assertEqual(s.open_mode, "REBUILT")
        self.assertEqual(s.numeric_stats("3").maximum, 9)
        s.close()
        with self.assertRaises(ValueError):
            NumericTruthStore(self.path, grouping="nope")

    def test_custom_grouping_oracle(self):
        fn = lambda k: k[:2]
        rnd, model = random.Random(7), {}
        s = NumericTruthStore(self.path, groupers={"p2": fn}, grouping="p2")
        for _ in range(6):
            ops = []
            for _ in range(200):
                k = rnd.choice("abcd") + rnd.choice("xyz") + str(rnd.randint(0, 20))
                if rnd.random() < 0.3:
                    ops.append(("delete", k)); model.pop(k, None)
                else:
                    x = rnd.randint(-50, 50); ops.append(("put", k, enc(x))); model[k] = x
            s.apply(ops)
            for g, want in model_stats(model, fn).items():
                st = s.numeric_stats(g)
                self.assertEqual((st.count, st.total, st.minimum, st.maximum), want)
                self.assertEqual(st.served_from, "LENS")
        s.close()

    def test_second_store_on_same_file(self):
        a, b = NumericTruthStore(self.path), NumericTruthStore(self.path)
        a.apply([("put", "g/1", enc(5)), ("put", "g/2", enc(8))])
        b.apply([("put", "g/3", enc(-4)), ("delete", "g/2")])
        a.apply([("put", "g/4", enc(1))])
        model = {"g/1": 5, "g/3": -4, "g/4": 1}
        self.check(a, model)
        self.check(b, model)
        a.close(); b.close()

    def test_raw_write_to_source_while_open(self):
        s = NumericTruthStore(self.path)
        s.apply([("put", "g/1", enc(5)), ("put", "g/2", enc(8))])
        raw = sqlite3.connect(self.path)
        raw.execute("DELETE FROM opdb_source_kv WHERE k='g/2'")
        raw.execute("INSERT INTO opdb_source_kv VALUES ('g/9', ?)", (enc(-30),))
        raw.commit()
        st = s.numeric_stats("g")
        self.assertEqual((st.count, st.total, st.minimum, st.maximum), (2, -25, -30, 5))
        raw.execute("INSERT INTO opdb_source_kv VALUES ('g/bad', ?)", (b"xyz",))
        raw.commit(); raw.close()
        with self.assertRaises(SourceIntegrityError):     # never silently ignored
            s.numeric_stats("g")
        self.assertFalse(s.lens_enabled)
        s.delete("g/bad")
        self.assertEqual(s.numeric_stats("g").served_from, "LENS")
        s.close()

    def test_damaged_lens_detected(self):
        s = NumericTruthStore(self.path)
        s.apply([("put", f"g/{i}", enc(i)) for i in range(10)])
        s.close()
        con = sqlite3.connect(self.path)
        con.execute("UPDATE opdb_nlens_group SET n=n+1")  # totals disagree
        con.commit(); con.close()
        s = NumericTruthStore(self.path)
        self.assertEqual(s.open_mode, "REBUILT")
        self.assertEqual(s.numeric_stats("g").maximum, 9)
        s.close()
        con = sqlite3.connect(self.path)                  # stale index entry at the extreme
        con.execute("UPDATE opdb_nlens_val SET x=1000 WHERE k='g/9'")
        con.commit(); con.close()
        s = NumericTruthStore(self.path)
        st = s.numeric_stats("g")                         # caught by the Source cross-check
        self.assertEqual((st.maximum, st.minimum), (9, 0))
        self.assertEqual(st.served_from, "SOURCE")
        self.assertEqual(s.numeric_stats("g").served_from, "LENS")   # rebuilt
        s.close()

    def test_rollback_leaves_lens_equal_to_source(self):
        s = NumericTruthStore(self.path)
        s.put("g/1", enc(5))
        real = s._fn
        def flaky(k):
            if k == "g/boom":
                raise RuntimeError("boom")
            return real(k)
        s._fn = flaky
        with self.assertRaises(RuntimeError):
            s.apply([("put", "g/2", enc(7)), ("put", "g/boom", enc(1))])
        s._fn = real
        self.assertIsNone(s.get("g/2"))
        st = s.numeric_stats("g")
        self.assertEqual((st.count, st.total), (1, 5))
        s.close()


if __name__ == "__main__":
    unittest.main()
