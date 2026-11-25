"""TASK-024: NumericTruthStore sums at signed 64-bit limits and on overflow.

Oracles: (a) numeric_stats_source(g) scanning Source with plain Python ints
and (b) a plain Python dict model. Neither uses the code under test.
"""
import os
import tempfile
import unittest

from opdb import NumericTruthStore

INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def model_stats(model, fn=gof):
    out = {}
    for k, x in model.items():
        out.setdefault(fn(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


def source_stats(store, group):
    ref = store.numeric_stats_source(group)
    return (ref.count, ref.total, ref.minimum, ref.maximum)


class NumericSumLimits(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name + ".db")

    def check_all(self, store, model, path):
        exp = model_stats(model)
        for g in set(exp) | {"zzz", "g", "h", "o", "p", "n"}:
            got = store.numeric_stats(g)
            want = exp.get(g, (0, 0, None, None))
            nums = (got.count, got.total, got.minimum, got.maximum)
            self.assertEqual(nums, want, (g, got.served_from))
            self.assertEqual(source_stats(store, g), want, (g, "source"))
            src = {k: int.from_bytes(v, "big", signed=True)
                   for k, v in store._db.execute("SELECT k,v FROM opdb_source_kv")}
            self.assertEqual(src, model)

    def test_sum_exactly_int64_max_and_min(self):
        path = self.path("exact")
        model = {
            "g/max": INT64_MAX,
            "h/min": INT64_MIN,
        }
        s = NumericTruthStore(path)
        s.apply([("put", "g/max", enc(INT64_MAX)), ("put", "h/min", enc(INT64_MIN))])
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()

    def test_single_values_int64_limits(self):
        path = self.path("single")
        model = {
            "g/max": INT64_MAX,
            "h/min": INT64_MIN,
        }
        s = NumericTruthStore(path)
        s.apply([("put", "g/max", enc(INT64_MAX)), ("put", "h/min", enc(INT64_MIN))])
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()

    def test_batch_pushes_sum_past_int64_max(self):
        path = self.path("over_max")
        model = {
            "o/1": INT64_MAX - 1,
            "o/2": 1,
        }
        s = NumericTruthStore(path)
        s.apply([("put", "o/1", enc(INT64_MAX - 1)), ("put", "o/2", enc(1))])
        self.check_all(s, model, path)
        s.put("o/2", enc(2))  # sum becomes INT64_MAX + 1
        model["o/2"] = 2
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()

    def test_batch_pushes_sum_past_int64_min(self):
        path = self.path("over_min")
        model = {
            "n/1": INT64_MIN + 1,
            "n/2": -1,
        }
        s = NumericTruthStore(path)
        s.apply([("put", "n/1", enc(INT64_MIN + 1)), ("put", "n/2", enc(-1))])
        self.check_all(s, model, path)
        s.put("n/2", enc(-2))  # sum becomes INT64_MIN - 1
        model["n/2"] = -2
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()

    def test_overflow_one_group_while_other_stays_in_range(self):
        path = self.path("mixed")
        model = {
            "o/1": INT64_MAX - 1,
            "o/2": 1,
            "p/1": 7,
        }
        s = NumericTruthStore(path)
        s.apply([
            ("put", "o/1", enc(INT64_MAX - 1)),
            ("put", "o/2", enc(1)),
            ("put", "p/1", enc(7)),
        ])
        self.check_all(s, model, path)
        s.put("o/2", enc(2))  # o overflows; p stays in range
        model["o/2"] = 2
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()

    def test_later_batch_brings_overflowed_group_back_in_range(self):
        path = self.path("recover")
        model = {
            "o/1": INT64_MAX - 1,
            "o/2": 1,
        }
        s = NumericTruthStore(path)
        s.apply([
            ("put", "o/1", enc(INT64_MAX - 1)),
            ("put", "o/2", enc(1)),
        ])
        self.check_all(s, model, path)
        s.put("o/2", enc(2))  # overflow: INT64_MAX + 1
        model["o/2"] = 2
        self.check_all(s, model, path)
        s.put("o/3", enc(-2))  # back in range: INT64_MAX - 1
        model["o/3"] = -2
        self.check_all(s, model, path)
        s.close()
        s = NumericTruthStore(path)
        self.check_all(s, model, path)
        s.close()


if __name__ == "__main__":
    unittest.main()
