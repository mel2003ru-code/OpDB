"""TASK-032: NumericTruthStore answers are stable across rebuilds and reopens.

Independent reference: a plain Python dict model. No engine changes.
"""
import os
import random
import tempfile
import unittest

from opdb import NumericTruthStore


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def model_stats(model):
    out = {}
    for k, x in model.items():
        out.setdefault(gof(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


def check_stats(tc, store, model):
    exp = model_stats(model)
    for g in set(exp) | {"g0", "g9", "zzz"}:
        want = exp.get(g, (0, 0, None, None))
        got = store.numeric_stats(g)
        ref = store.numeric_stats_source(g)
        tc.assertEqual((got.count, got.total, got.minimum, got.maximum), want, g)
        tc.assertEqual((ref.count, ref.total, ref.minimum, ref.maximum), want, g)
        tc.assertEqual(got.served_from, "LENS", g)
        tc.assertEqual(ref.served_from, "SOURCE", g)


class NumericRebuildReopen(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path_for(self, seed):
        return os.path.join(self.tmp.name, f"s{seed}.db")

    def test_seeded_rebuild_reopen(self):
        for seed in range(20):
            path = self.path_for(seed)
            rnd = random.Random(seed)
            model = {}
            store = NumericTruthStore(path)
            # First open of a brand-new file is not checked for open_mode.
            for batch in range(30):
                ops = []
                for _ in range(rnd.randint(1, 6)):
                    key = f"g{rnd.randint(0, 3)}/k{rnd.randint(0, 9)}"
                    if rnd.random() < 0.45:
                        ops.append(("delete", key))
                        model.pop(key, None)
                    else:
                        x = rnd.randint(-50, 50)
                        ops.append(("put", key, enc(x)))
                        model[key] = x
                store.apply(ops)
                check_stats(self, store, model)
                if batch % 10 == 9:
                    if batch % 20 == 9:
                        store.close()
                        store = NumericTruthStore(path)
                        self.assertEqual(store.open_mode, "PERSISTED", (seed, batch))
                        self.assertEqual(store.open_reason, "", (seed, batch))
                    else:
                        store.rebuild()
                    check_stats(self, store, model)
            # rebuild() twice in a row changes nothing
            store.rebuild()
            store.rebuild()
            check_stats(self, store, model)
            store.close()
            # a rebuilt file reopens as PERSISTED
            store = NumericTruthStore(path)
            self.assertEqual(store.open_mode, "PERSISTED", seed)
            self.assertEqual(store.open_reason, "", seed)
            check_stats(self, store, model)
            store.close()

    def test_rebuild_twice_no_change(self):
        path = self.path_for(999)
        model = {}
        store = NumericTruthStore(path)
        store.apply([("put", "g1/k1", enc(10)), ("put", "g2/k2", enc(-20)),
                     ("delete", "g1/k1")])
        model = {"g2/k2": -20}
        check_stats(self, store, model)
        store.rebuild()
        store.rebuild()
        check_stats(self, store, model)
        store.close()
        store = NumericTruthStore(path)
        self.assertEqual(store.open_mode, "PERSISTED")
        check_stats(self, store, model)
        store.close()

    def test_rebuilt_file_reopens_persisted(self):
        path = self.path_for(998)
        model = {}
        store = NumericTruthStore(path)
        store.apply([("put", "a/k1", enc(5)), ("put", "a/k2", enc(7))])
        model = {"a/k1": 5, "a/k2": 7}
        store.rebuild()
        check_stats(self, store, model)
        store.close()
        store = NumericTruthStore(path)
        self.assertEqual(store.open_mode, "PERSISTED")
        self.assertEqual(store.open_reason, "")
        check_stats(self, store, model)
        store.close()


if __name__ == "__main__":
    unittest.main()
