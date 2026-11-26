"""TASK-030: order of operations inside one batch against a plain Python dict model.

Oracles: (a) a fresh sqlite3 connection over Source and (b) a plain Python dict;
neither uses the code under test. The engine is not changed.
"""
import os
import random
import sqlite3
import tempfile
import unittest

from opdb import NumericTruthStore

GROUPS = ["a", "b", "g", "h"]


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def sql_source(path):
    """Independent Source read with a fresh sqlite3 connection."""
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT k, v FROM opdb_source_kv ORDER BY k").fetchall()
    finally:
        con.close()
    return {k: int.from_bytes(v, "big", signed=True) for k, v in rows}


def model_stats(model):
    out = {}
    for k, x in model.items():
        out.setdefault(gof(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


class BatchSemantics(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def fresh_store(self, name):
        path = os.path.join(self.tmp.name, name)
        return NumericTruthStore(path), path

    def check_all(self, store, model, path):
        self.assertEqual(sql_source(path), model)
        for g in set(model_stats(model)) | set(GROUPS) | {"zzz"}:
            want = model_stats(model).get(g, (0, 0, None, None))
            got = store.numeric_stats(g)
            ref = store.numeric_stats_source(g)
            self.assertEqual(got.served_from, "LENS", g)
            self.assertEqual((got.count, got.total, got.minimum, got.maximum), want, g)
            self.assertEqual((ref.count, ref.total, ref.minimum, ref.maximum), want, g)

    def test_two_puts_same_key_second_wins(self):
        store, path = self.fresh_store("two_puts.db")
        try:
            model = {}
            store.apply([("put", "g/a", enc(1)), ("put", "g/a", enc(2))])
            model["g/a"] = 2
            self.check_all(store, model, path)
            self.assertEqual(store.get("g/a"), enc(2))
        finally:
            store.close()

    def test_put_then_delete_key_absent(self):
        store, path = self.fresh_store("put_delete.db")
        try:
            model = {}
            store.apply([("put", "g/a", enc(1)), ("delete", "g/a")])
            self.check_all(store, model, path)
            self.assertIsNone(store.get("g/a"))
        finally:
            store.close()

    def test_delete_then_put_key_present(self):
        store, path = self.fresh_store("delete_put.db")
        try:
            model = {}
            store.apply([("delete", "g/a"), ("put", "g/a", enc(3))])
            model["g/a"] = 3
            self.check_all(store, model, path)
            self.assertEqual(store.get("g/a"), enc(3))
        finally:
            store.close()

    def test_delete_missing_with_valid_put_allowed(self):
        store, path = self.fresh_store("delete_missing.db")
        try:
            model = {}
            store.apply([("delete", "g/missing"), ("put", "g/a", enc(4))])
            model["g/a"] = 4
            self.check_all(store, model, path)
            self.assertEqual(store.get("g/a"), enc(4))
        finally:
            store.close()

    def test_empty_batch_no_error_nothing_changes(self):
        store, path = self.fresh_store("empty_batch.db")
        try:
            store.apply([("put", "g/a", enc(5))])
            model = {"g/a": 5}
            self.check_all(store, model, path)
            store.apply([])
            self.check_all(store, model, path)
            self.assertEqual(store.get("g/a"), enc(5))
        finally:
            store.close()

    def test_overwrite_with_same_value_answers_unchanged(self):
        store, path = self.fresh_store("same_value.db")
        try:
            model = {}
            store.apply([("put", "g/a", enc(7))])
            model["g/a"] = 7
            self.check_all(store, model, path)
            store.apply([("put", "g/a", enc(7))])
            self.check_all(store, model, path)
            self.assertEqual(store.get("g/a"), enc(7))
        finally:
            store.close()

    def test_seeded_random_batches_repeat_keys(self):
        for seed in range(20):
            path = os.path.join(self.tmp.name, f"rand{seed}.db")
            rnd = random.Random(seed)
            model = {}
            store = NumericTruthStore(path)
            try:
                for _ in range(12):
                    ops = []
                    for _ in range(rnd.randint(1, 8)):
                        key = rnd.choice(GROUPS) + "/" + rnd.choice(["n1", "n2", "n3"])
                        if rnd.random() < 0.4:
                            ops.append(("delete", key))
                            model.pop(key, None)
                        else:
                            x = rnd.randint(-1000, 1000)
                            ops.append(("put", key, enc(x)))
                            model[key] = x
                    store.apply(ops)
                    self.check_all(store, model, path)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
