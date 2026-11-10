"""TASK-008: M3 experimental opt-in persisted aggregate, Source oracle.

Test mutable Source against independent Python and SQLite. No production
storage, no privileged-writer security claim, no existing tests edited.
"""
from __future__ import annotations

import os
from pathlib import Path
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from opdb import SourceIntegrityError, TruthStore


class PersistedLensTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="opdb-m3-")
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "store.db"

    def verify(self, store, model):
        for group in ("g0", "g1", "g2", "", "missing"):
            values = [v for key, v in model.items()
                      if key.split("/", 1)[0] == group]
            expected = (len(values), sum(len(v) for v in values))
            a = store.group_stats(group)
            b = store.group_stats_source(group)
            self.assertEqual((a.row_count, a.value_bytes), expected)
            self.assertEqual((b.row_count, b.value_bytes), expected)
            with sqlite3.connect(self.path) as raw:
                got = raw.execute(
                    "SELECT k,v FROM opdb_source_kv"
                ).fetchall()
            self.assertEqual(dict(got), model)

    def test_default_modes_do_not_create_disk_cache(self):
        with self.assertRaises(ValueError):
            TruthStore(self.path, persist_lens=True)
        for lens in (False, True):
            with TruthStore(self.path, lens=lens):
                pass
        with sqlite3.connect(self.path) as raw:
            names = {row[0] for row in raw.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            self.assertFalse(any(x.startswith("opdb_lens_") for x in names))

    def test_20_seeded_reopen_and_no_source_scan(self):
        for seed in range(20):
            path = Path(self.tmp.name) / f"seed-{seed}.db"
            rng = random.Random(seed + 800)
            model = {}
            with TruthStore(path, lens=True, persist_lens=True) as store:
                for batch_no in range(8):
                    ops = []
                    for _ in range(60):
                        key = f"g{rng.randrange(3)}/{rng.randrange(25)}"
                        if rng.randrange(4) == 0:
                            ops.append(("delete", key))
                            model.pop(key, None)
                        else:
                            value = bytes([rng.randrange(256)]) * rng.randrange(40)
                            ops.append(("put", key, value))
                            model[key] = value
                    store.apply(ops)
                    self.assertTrue(store.lens_enabled)
                with sqlite3.connect(path) as raw:
                    current = dict(raw.execute("SELECT k,v FROM opdb_source_kv"))
                self.assertEqual(current, model)
            # Independent trap: any full Source scan through Lens._metric fails.
            with patch("opdb.lens._metric", side_effect=AssertionError("Source scan")):
                with TruthStore(path, lens=True, persist_lens=True) as reopened:
                    self.assertTrue(reopened._lens.loaded_from_disk)
                    self.assertTrue(reopened.lens_enabled)
            with TruthStore(path, lens=True, persist_lens=True) as reopened:
                for group in ("g0", "g1", "g2"):
                    vals = [v for k, v in model.items()
                            if k.split("/", 1)[0] == group]
                    self.assertEqual(
                        (reopened.group_stats(group).row_count,
                         reopened.group_stats(group).value_bytes),
                        (len(vals), sum(map(len, vals)))
                    )

    def test_stale_metadata_and_corrupt_counts_rebuild(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.apply([("put", "g1/a", b"abc"),
                         ("put", "g1/b", b"defg")])
        for sql in (
            "UPDATE opdb_lens_state_v1 SET source_seq=-100",
            "UPDATE opdb_lens_groups_v1 SET value_bytes=123456",
            "UPDATE opdb_lens_groups_v1 SET row_count='broken'",
        ):
            with sqlite3.connect(self.path) as raw:
                raw.execute(sql)
            with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
                self.assertFalse(reopened._lens.loaded_from_disk)
                self.assertTrue(reopened.lens_enabled)
                self.assertEqual(reopened.group_stats("g1").value_bytes, 7)

    def test_roll_back_source_if_persistent_write_fails(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.put("g1/a", b"one")
            store._db.execute(
                "CREATE TRIGGER block_lens_save BEFORE DELETE "
                "ON opdb_lens_groups_v1 BEGIN "
                "SELECT RAISE(ABORT,'inject'); END"
            )
            with self.assertRaises(sqlite3.DatabaseError):
                store.apply([("put", "g1/a", b"two"),
                             ("put", "g1/b", b"three")])
            self.assertEqual(store.get("g1/a"), b"one")
            self.assertIsNone(store.get("g1/b"))
            self.assertEqual(store.group_stats("g1").value_bytes, 3)
        with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
            self.assertTrue(reopened._lens.loaded_from_disk)
            self.assertEqual(reopened.group_stats("g1").value_bytes, 3)

    def test_untracked_writer_in_live_connection_falls_back(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.put("g1/a", b"a")
            with sqlite3.connect(self.path) as outsider:
                outsider.execute(
                    "UPDATE opdb_source_kv SET v=? WHERE k=?",
                    (b"changed", "g1/a"),
                )
            first = store.group_stats("g1")
            self.assertEqual(first.value_bytes, len(b"changed"))
            self.assertEqual(first.served_from, "SOURCE")
        with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
            self.assertEqual(reopened.group_stats("g1").value_bytes, 7)

    def test_malformed_initial_source_disables_lens(self):
        with TruthStore(self.path, lens=False):
            pass
        with sqlite3.connect(self.path) as raw:
            raw.execute(
                "INSERT INTO opdb_source_kv(k,v) VALUES (?,?)",
                ("bad/x", 123)
            )
            raw.execute(
                "INSERT INTO opdb_source_kv(k,v) VALUES (?,?)",
                ("g1/good", b"okay")
            )
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            self.assertFalse(store.lens_enabled)
            self.assertEqual(store.get("g1/good"), b"okay")
            with self.assertRaises(SourceIntegrityError):
                store.get("bad/x")

    def test_crash_before_commit_keeps_old_source_and_cache(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.put("g1/a", b"old")
        script = (
            "import os,sys;"
            "from opdb import TruthStore;"
            "s=TruthStore(sys.argv[1],lens=True,persist_lens=True);"
            "s._db.execute('BEGIN IMMEDIATE');"
            "s._db.execute('UPDATE opdb_source_kv SET v=? WHERE k=?',"
            "(b'not-committed','g1/a'));"
            "s._db.execute('UPDATE opdb_lens_state_v1 SET source_seq=-1');"
            "os._exit(19)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script, str(self.path)],
            cwd=Path(__file__).resolve().parents[1],
            timeout=15, check=False,
        )
        self.assertEqual(proc.returncode, 19)
        with patch("opdb.lens._metric", side_effect=AssertionError("Source scan")):
            with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
                self.assertTrue(reopened._lens.loaded_from_disk)
                self.assertEqual(reopened.get("g1/a"), b"old")
                self.assertEqual(reopened.group_stats("g1").value_bytes, 3)

    def test_checksum_field_tamper_forces_rebuild(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.put("g1/a", b"one")
        with sqlite3.connect(self.path) as raw:
            raw.execute(
                "UPDATE opdb_lens_state_v1 SET checksum=? WHERE singleton=1",
                ("0" * 64,),
            )
        with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
            self.assertFalse(reopened._lens.loaded_from_disk)
            self.assertTrue(reopened.lens_enabled)
            self.assertEqual(reopened.group_stats("g1").value_bytes, 3)

    def test_crash_after_commit_before_memory_publish(self):
        with TruthStore(self.path, lens=True, persist_lens=True) as store:
            store.put("g1/a", b"old")
        script = (
            "import os,sys;"
            "from opdb import TruthStore;"
            "s=TruthStore(sys.argv[1],lens=True,persist_lens=True);"
            "s._lens.advance=lambda *args:os._exit(17);"
            "s.put('g1/a',b'new');"
            "os._exit(77)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", script, str(self.path)],
            cwd=Path(__file__).resolve().parents[1],
            timeout=15, check=False,
        )
        self.assertEqual(proc.returncode, 17)
        with patch("opdb.lens._metric", side_effect=AssertionError("Source scan")):
            with TruthStore(self.path, lens=True, persist_lens=True) as reopened:
                self.assertTrue(reopened._lens.loaded_from_disk)
                self.assertEqual(reopened.get("g1/a"), b"new")
                self.assertEqual(reopened.group_stats("g1").value_bytes, 3)


if __name__ == "__main__":
    unittest.main()
