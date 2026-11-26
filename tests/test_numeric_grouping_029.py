"""TASK-029: caller-defined grouping for NumericTruthStore; groups appear and disappear inside batches; grouping name is honoured on reopen.

Oracles: a plain Python dict model built with the same grouping function; neither uses the code under test.
"""
import os
import random
import tempfile
import unittest

from opdb import NumericTruthStore


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def first2(key):
    return key[:2]


def prefix_before_slash(key):
    return key.split("/", 1)[0]


def model_stats(model, fn):
    out = {}
    for k, x in model.items():
        out.setdefault(fn(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


class NumericGrouping(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def check_group(self, store, model, group):
        want = model_stats(model, first2).get(group, (0, 0, None, None))
        st = store.numeric_stats(group)
        self.assertEqual(st.served_from, "LENS", group)
        self.assertEqual((st.count, st.total, st.minimum, st.maximum), want, group)
        ref = store.numeric_stats_source(group)
        self.assertEqual((ref.count, ref.total, ref.minimum, ref.maximum), want, group)

    def test_batch_creates_two_new_groups_at_once(self):
        p = self.path("two_groups.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab1", enc(1)), ("put", "cd7", enc(2)),
                         ("put", "ab2", enc(3))])
            model["ab1"] = 1; model["cd7"] = 2; model["ab2"] = 3
            self.check_group(store, model, "ab")
            self.check_group(store, model, "cd")
            self.check_group(store, model, "zz")
        finally:
            store.close()

    def test_group_disappears_and_another_appears_same_batch(self):
        p = self.path("disappear.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab1", enc(5)), ("put", "ab2", enc(6))])
            model["ab1"] = 5; model["ab2"] = 6
            self.check_group(store, model, "ab")
            self.check_group(store, model, "cd")
            store.apply([("delete", "ab1"), ("delete", "ab2"),
                         ("put", "cd7", enc(9))])
            model.pop("ab1", None); model.pop("ab2", None); model["cd7"] = 9
            self.check_group(store, model, "ab")
            self.check_group(store, model, "cd")
            self.check_group(store, model, "zz")
        finally:
            store.close()

    def test_overwrite_delete_add_same_group(self):
        p = self.path("mixed.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab1", enc(1)), ("put", "ab2", enc(2)),
                         ("put", "ab3", enc(3))])
            model["ab1"] = 1; model["ab2"] = 2; model["ab3"] = 3
            store.apply([("put", "ab2", enc(20)), ("delete", "ab3"),
                         ("put", "ab4", enc(4))])
            model["ab2"] = 20; model.pop("ab3", None); model["ab4"] = 4
            self.check_group(store, model, "ab")
            self.check_group(store, model, "zz")
        finally:
            store.close()

    def test_group_disappears_and_reappears(self):
        p = self.path("reappear.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab1", enc(1))])
            model["ab1"] = 1
            self.check_group(store, model, "ab")
            self.check_group(store, model, "zz")
            store.apply([("delete", "ab1")])
            model.pop("ab1", None)
            st = store.numeric_stats("ab")
            self.assertEqual((st.count, st.total, st.minimum, st.maximum),
                             (0, 0, None, None))
            self.check_group(store, model, "zz")
            store.apply([("put", "ab9", enc(9))])
            model["ab9"] = 9
            self.check_group(store, model, "ab")
            self.check_group(store, model, "zz")
        finally:
            store.close()

    def test_seeded_random_batches(self):
        for seed in range(20):
            p = self.path(f"seed{seed}.db")
            rnd = random.Random(seed)
            model = {}
            pool = ["ab1", "ab2", "cd3", "cd4", "é9x", "a", "bc5", "cd6"]
            store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
            try:
                for _ in range(10):
                    ops = []
                    for _ in range(rnd.randint(1, 50)):
                        key = rnd.choice(pool)
                        if rnd.random() < 0.35:
                            ops.append(("delete", key))
                            model.pop(key, None)
                        else:
                            x = rnd.randint(-100, 100)
                            ops.append(("put", key, enc(x)))
                            model[key] = x
                    store.apply(ops)
                    groups = {first2(k) for k in pool} | {"zz"}
                    for g in groups:
                        self.check_group(store, model, g)
            finally:
                store.close()

    def test_reopen_persisted_same_grouping(self):
        p = self.path("reopen_persisted.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab1", enc(1)), ("put", "cd7", enc(2)),
                         ("put", "ab2", enc(3)), ("delete", "cd7")])
            model["ab1"] = 1; model["ab2"] = 3
            self.check_group(store, model, "ab")
            self.check_group(store, model, "cd")
        finally:
            store.close()
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            self.assertEqual(store.open_mode, "PERSISTED", store.open_reason)
            self.check_group(store, model, "ab")
            self.check_group(store, model, "cd")
            self.check_group(store, model, "zz")
        finally:
            store.close()

    def test_reopen_default_grouping_rebuilt(self):
        p = self.path("reopen_rebuilt.db")
        model = {}
        store = NumericTruthStore(p, groupers={"first2": first2}, grouping="first2")
        try:
            store.apply([("put", "ab/1", enc(1)), ("put", "ab/2", enc(2)),
                         ("put", "cd/7", enc(3))])
            model["ab/1"] = 1; model["ab/2"] = 2; model["cd/7"] = 3
        finally:
            store.close()
        store = NumericTruthStore(p)
        try:
            self.assertEqual(store.open_mode, "REBUILT", store.open_reason)
            self.assertEqual(store.open_reason, "grouping function changed")
            for g, want in model_stats(model, prefix_before_slash).items():
                st = store.numeric_stats(g)
                self.assertEqual((st.count, st.total, st.minimum, st.maximum), want, g)
                self.assertEqual(st.served_from, "LENS", g)
            self.check_group(store, model, "zz")
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
