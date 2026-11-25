"""TASK-025: a failed mixed batch leaves Source and the Lens unchanged.

The failure is injected inside the transaction with a SQLite trigger that aborts
every DELETE on the value-index table (created through a separate connection
while the store is closed). Oracles: a copy of Source taken through an
independent sqlite3 connection and a plain Python dict model; neither uses the
code under test.
"""
import os
import random
import sqlite3
import tempfile
import unittest

from opdb import NumericTruthStore

GROUPS = ["a", "b", "é", "日本", "grp0", "grp1", "grp2"]
# Small values only: a group sum outside the signed 64-bit range makes the Lens
# untrusted, and then apply() does not touch the value index at all.
VALUES = [0, 1, -1, 5, 5, -5, 10**6, -10**6, 2**20, -2**20]


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def group_of(key):
    return key.split("/", 1)[0]


def model_stats(model, groups):
    out = {}
    for g in groups:
        v = [x for k, x in model.items() if group_of(k) == g]
        out[g] = (len(v), sum(v), min(v) if v else None, max(v) if v else None)
    return out


def source_copy(path):
    """Independent read of Source: no OpDB code involved."""
    con = sqlite3.connect(path)
    try:
        return con.execute("SELECT k, v FROM opdb_source_kv ORDER BY k").fetchall()
    finally:
        con.close()


def add_trigger(path):
    con = sqlite3.connect(path)
    try:
        con.execute("CREATE TRIGGER boom BEFORE DELETE ON opdb_nlens_val "
                    "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        con.commit()
    finally:
        con.close()


def answers(store, groups):
    """(count, total, minimum, maximum) per group from the Lens and from Source."""
    lens, source = {}, {}
    for g in groups:
        a, b = store.numeric_stats(g), store.numeric_stats_source(g)
        lens[g] = (a.count, a.total, a.minimum, a.maximum)
        source[g] = (b.count, b.total, b.minimum, b.maximum)
    return lens, source


class MixedBatchRollback(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_seed(self, seed):
        rnd = random.Random(seed)
        path = os.path.join(self.tmp.name, f"r{seed}.db")
        model = {}
        for i in range(rnd.randint(100, 140)):
            model[f"{rnd.choice(GROUPS)}/k{i}"] = rnd.choice(VALUES) + rnd.randint(-3, 3)
        store = NumericTruthStore(path)
        store.apply([("put", k, enc(x)) for k, x in model.items()])
        store.close()
        add_trigger(path)

        groups = sorted(set(GROUPS) | {"zzz"})
        victim_delete, victim_overwrite = rnd.sample(sorted(model), 2)
        new_keys = [f"{rnd.choice(GROUPS)}/new{seed}_{j}" for j in range(3)]
        before = source_copy(path)
        want = model_stats(model, groups)

        store = NumericTruthStore(path)
        self.addCleanup(store.close)
        batch = ([("put", k, enc(rnd.choice(VALUES))) for k in new_keys]
                 + [("put", victim_overwrite, enc(model[victim_overwrite] + 1)),
                    ("delete", victim_delete)])
        rnd.shuffle(batch)
        with self.assertRaises(sqlite3.IntegrityError, msg=seed):
            store.apply(batch)

        after = source_copy(path)
        self.assertEqual(before, after, seed)
        self.assertFalse({k for k, _ in after} & set(new_keys), seed)
        lens, source = answers(store, groups)
        self.assertEqual(want, lens, seed)
        self.assertEqual(want, source, seed)
        # After a failure the engine re-verifies on the next read, so either
        # "LENS" or "SOURCE" may serve; only the numbers matter here.

        # A second store object on the same file sees the same state.
        other = NumericTruthStore(path)
        try:
            lens2, source2 = answers(other, groups)
            self.assertEqual(want, lens2, seed)
            self.assertEqual(want, source2, seed)
        finally:
            other.close()

        # Reopening after the failure gives the same answers and the same Source.
        store.close()
        again = NumericTruthStore(path)
        try:
            lens3, source3 = answers(again, groups)
            self.assertEqual(want, lens3, seed)
            self.assertEqual(want, source3, seed)
            # The stored Lens was rolled back with the data: it is trusted again.
            for g in groups:
                self.assertEqual(again.numeric_stats(g).served_from, "LENS", (seed, g))
        finally:
            again.close()
        self.assertEqual(before, source_copy(path), seed)

    def test_failed_mixed_batch_rolls_back_for_ten_seeds(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                self.run_seed(seed)


if __name__ == "__main__":
    unittest.main()
