"""TASK-034: an invalid batch is rejected and changes nothing.

Oracles: a fresh sqlite3 connection over Source (SELECT k,v ...) and
numeric_stats(g) recorded before each batch. Neither oracle uses the code
under test beyond the public API being exercised.
"""
import os
import sqlite3
import tempfile
import unittest

from opdb import NumericTruthStore


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def source_rows(path):
    con = sqlite3.connect(path)
    try:
        return con.execute(
            "SELECT k, v FROM opdb_source_kv ORDER BY k").fetchall()
    finally:
        con.close()


class NumericValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "n.db")

    def fresh_store(self):
        s = NumericTruthStore(self.path)
        s.apply([
            ("put", "a/1", enc(1)),
            ("put", "a/2", enc(2)),
            ("put", "b/1", enc(10)),
            ("put", "b/2", enc(20)),
        ])
        return s

    def stats_before(self, s):
        before = source_rows(self.path)
        snap = {}
        for g in ("a", "b", "zzz"):
            st = s.numeric_stats(g)
            snap[g] = (st.count, st.total, st.minimum, st.maximum)
        return before, snap

    def assert_unchanged(self, s, before, snap):
        self.assertEqual(source_rows(self.path), before)
        for g, want in snap.items():
            st = s.numeric_stats(g)
            self.assertEqual((st.count, st.total, st.minimum, st.maximum), want)

    def test_invalid_batches_rejected_without_effect(self):
        s = self.fresh_store()
        try:
            before, snap = self.stats_before(s)
            bad_batches = [
                [("put", "a/1", enc(5)), ("put", "a/3", b"abc")],
                [("put", "a/1", enc(5)), ("put", "a/3", b"1234567")],
                [("put", "a/1", enc(5)), ("put", "a/3", b"123456789")],
                [("put", "a/1", enc(5)), ("upsert", "a/1", enc(7))],
                [("put", "a/1", enc(5)), "put"],
                [("put", "a/1", enc(5)), ("put", "a/1")],
                [("put", "a/1", enc(5)), ("delete", "a/1", b"x")],
                [("put", "a/1", enc(5)), ("put", 5, enc(7))],
                [("put", "a/1", enc(5)), ("put", "a\x00b", enc(7))],
            ]
            for bad in bad_batches:
                with self.assertRaises(ValueError):
                    s.apply(bad)
                self.assert_unchanged(s, before, snap)

            model = {"a/1": 1, "a/2": 2, "b/1": 10, "b/2": 20}
            s.apply([("put", "c/1", enc(3)), ("delete", "b/1")])
            model["c/1"] = 3
            del model["b/1"]
            self.assertEqual(source_rows(self.path),
                             sorted((k, enc(v)) for k, v in model.items()))
            for g, want in {
                "a": (2, 3, 1, 2),
                "b": (1, 20, 20, 20),
                "c": (1, 3, 3, 3),
            }.items():
                st = s.numeric_stats(g)
                self.assertEqual((st.count, st.total, st.minimum, st.maximum), want)
                ref = s.numeric_stats_source(g)
                self.assertEqual((ref.count, ref.total, ref.minimum, ref.maximum), want)
        finally:
            s.close()

    def test_invalid_batch_last_operation(self):
        s = self.fresh_store()
        try:
            before, snap = self.stats_before(s)
            with self.assertRaises(ValueError):
                s.apply([("put", "a/9", enc(9)), ("put", "a/10", b"short")])
            self.assert_unchanged(s, before, snap)
        finally:
            s.close()


if __name__ == "__main__":
    unittest.main()
