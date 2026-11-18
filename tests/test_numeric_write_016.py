"""TASK-016: numeric Lens write path. Oracles: a plain Python dict model and a
fresh SQL connection over Source; neither uses the code under test."""
import os
import random
import sqlite3
import tempfile
import unittest

from opdb import NumericTruthStore

GROUPS = ["a", "b", "é", "日本", "", "g"] + [f"grp{i}" for i in range(6)]
EDGE = [0, 1, -1, 5, 5, -5, 2**62, -2**62, 1000, -1000]


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def model_stats(model):
    out = {}
    for k, x in model.items():
        out.setdefault(gof(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


def sql_rows(path):
    con = sqlite3.connect(path)
    try:
        return {k: int.from_bytes(v, "big", signed=True)
                for k, v in con.execute("SELECT k,v FROM opdb_source_kv")}
    finally:
        con.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "n.db")

    def check(self, st, model, served="LENS"):
        want = model_stats(model)
        self.assertEqual(sql_rows(self.path), model)
        for g in set(GROUPS) | set(want):
            s = st.numeric_stats(g)
            w = want.get(g)
            self.assertEqual((s.count, s.total, s.minimum, s.maximum),
                             w if w else (0, 0, None, None), g)
            src = st.numeric_stats_source(g)
            self.assertEqual((s.count, s.total, s.minimum, s.maximum),
                             (src.count, src.total, src.minimum, src.maximum))


class OracleTest(Base):
    def test_seeded_batches_and_reopen(self):
        for seed in range(20):
            path = os.path.join(self.dir.name, f"s{seed}.db")
            self.path = path
            rng = random.Random(seed)
            st = NumericTruthStore(path)
            model = {}
            for _ in range(8):
                ops = []
                for _ in range(rng.randrange(1, 40)):
                    g = rng.choice(GROUPS)
                    k = f"{g}/{rng.randrange(25)}"
                    r = rng.random()
                    if r < 0.5:
                        x = rng.choice(EDGE + [rng.randrange(-10**9, 10**9)])
                        ops.append(("put", k, enc(x))); model[k] = x
                    elif r < 0.85:
                        ops.append(("delete", k)); model.pop(k, None)
                    else:   # delete then put, and a duplicate put of the same key
                        x = rng.choice(EDGE)
                        ops += [("delete", k), ("put", k, enc(x)), ("put", k, enc(x + 1))]
                        model[k] = x + 1
                st.apply(ops)
                self.check(st, model)
            st.close()
            st = NumericTruthStore(path)
            over = any(not -2**63 <= v[1] < 2**63 for v in model_stats(model).values())
            if over:    # documented: an overflowing group cannot be stored, Source answers
                self.assertEqual(st.open_mode, "SOURCE_FALLBACK")
            else:
                self.assertIn(st.open_mode, ("PERSISTED", "REBUILT"))
            self.check(st, model)
            st.close()

    def test_move_group_and_remove_extremes_and_group(self):
        st = NumericTruthStore(self.path)
        model = {"a/1": 5, "a/2": 9, "a/3": -4, "b/1": 7}
        st.apply([("put", k, enc(x)) for k, x in model.items()])
        self.check(st, model)
        st.apply([("delete", "a/3"), ("delete", "a/2")]); del model["a/3"], model["a/2"]
        self.check(st, model)                       # only min and max removed
        st.apply([("delete", "a/1"), ("delete", "zzz/absent")]); del model["a/1"]
        self.check(st, model)                       # whole group gone, absent key ignored
        st.apply([("delete", "b/1"), ("put", "a/b/1", enc(3))]); del model["b/1"]
        model["a/b/1"] = 3
        self.check(st, model)
        st.close()

    def test_bad_value_leaves_everything_unchanged(self):
        st = NumericTruthStore(self.path)
        st.apply([("put", "a/1", enc(1))])
        with self.assertRaises(ValueError):
            st.apply([("put", "a/2", enc(2)), ("put", "a/3", b"")])
        self.check(st, {"a/1": 1})
        st.close()


class FailureTest(Base):
    def test_injected_error_rolls_back_source_and_lens(self):
        st = NumericTruthStore(self.path)
        st.apply([("put", f"a/{i}", enc(i)) for i in range(5)])
        model = {f"a/{i}": i for i in range(5)}
        real = st._db

        class Boom:
            def __getattr__(self, n):
                return getattr(real, n)

            def execute(self, sql, *a):
                if sql.startswith("INSERT INTO opdb_nlens_val"):
                    raise sqlite3.OperationalError("injected")
                return real.execute(sql, *a)

        st._db = Boom()
        with self.assertRaises(sqlite3.OperationalError):
            st.apply([("put", "a/9", enc(99)), ("delete", "a/0")])
        st._db = real
        self.assertEqual(sql_rows(self.path), model)
        self.check(st, model, served="LENS")     # untrusted state re-verifies, answers stay true
        st.close()

    def test_overflow_falls_back_to_source(self):
        st = NumericTruthStore(self.path)
        st.apply([("put", "a/1", enc(2**63 - 1)), ("put", "a/2", enc(2**63 - 1))])
        s = st.numeric_stats("a")
        self.assertEqual((s.count, s.total), (2, 2 * (2**63 - 1)))
        self.assertEqual(s.served_from, "SOURCE")
        st.close()

    def test_second_store_write_is_never_served_stale(self):
        st = NumericTruthStore(self.path)
        other = NumericTruthStore(self.path)
        model = {}
        for i in range(6):
            st.apply([("put", f"a/{i}", enc(i))]); model[f"a/{i}"] = i
        other.apply([("put", "a/100", enc(1000)), ("delete", "a/0")])
        model["a/100"] = 1000; del model["a/0"]
        self.check(st, model)
        st.apply([("put", "a/7", enc(-7))]); model["a/7"] = -7
        self.check(st, model)
        raw = sqlite3.connect(self.path)            # outside write, bypassing OpDB
        raw.execute("UPDATE opdb_source_kv SET v=? WHERE k='a/1'", (enc(555),))
        raw.commit(); raw.close()
        model["a/1"] = 555
        self.check(st, model, served="")
        st.close(); other.close()


if __name__ == "__main__":
    unittest.main()
