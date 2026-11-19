"""TASK-017: numeric Lens rebuild(). Oracles: a plain Python dict model and the
expected Lens tables derived from Source with a fresh SQL connection; neither
uses the code under test. _REBUILD_CHUNK is lowered in some cases so chunk
boundaries (empty, exact, partial) are exercised with small data."""
import os
import random
import sqlite3
import tempfile
import unittest
from unittest import mock

from opdb import NumericTruthStore
from opdb import numeric
from opdb.core import SourceIntegrityError
from opdb.numeric import LensOverflow

GROUPS = ["a", "b", "é", "日本", "", "g", "Z", "á"] + [f"grp{i}" for i in range(6)]
EDGE = [0, 1, -1, 5, 5, -5, 2**55, -2**55, 1000, -1000, -(2**40)]


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def con(path):
    c = sqlite3.connect(path)
    c.text_factory = str
    return c


def expected_tables(path):
    """Lens tables as they must be, from Source only (plain SQL + Python)."""
    c = con(path)
    try:
        vals = sorted((gof(k), int.from_bytes(v, "big", signed=True), k)
                      for k, v in c.execute("SELECT k,v FROM opdb_source_kv"))
        seq = c.execute("SELECT commit_seq FROM opdb_meta").fetchone()[0]
    finally:
        c.close()
    groups = {}
    for g, x, _k in vals:
        n, s = groups.get(g, (0, 0))
        groups[g] = (n + 1, s + x)
    return sorted((g, n, s) for g, (n, s) in groups.items()), vals, \
        [(1, 1, seq, "prefix", len(vals))]


def stored_tables(path):
    c = con(path)
    try:
        return (c.execute("SELECT g,n,s FROM opdb_nlens_group ORDER BY g,n,s").fetchall(),
                c.execute("SELECT g,x,k FROM opdb_nlens_val ORDER BY g,x,k").fetchall(),
                c.execute("SELECT * FROM opdb_nlens_meta").fetchall())
    finally:
        c.close()


def model_stats(model):
    out = {}
    for k, x in model.items():
        out.setdefault(gof(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = os.path.join(self.dir.name, "n.db")

    def open(self, path=None):
        st = NumericTruthStore(path or self.path)
        self.addCleanup(st.close)
        return st

    def check(self, st, model, path=None):
        """Answers first (a store rebuilds lazily after a foreign commit), then tables."""
        path = path or self.path
        want = model_stats(model)
        for g in set(GROUPS) | set(want):
            s = st.numeric_stats(g)
            self.assertEqual(s.served_from, "LENS", g)
            self.assertEqual((s.count, s.total, s.minimum, s.maximum),
                             want.get(g, (0, 0, None, None)), g)
        self.assertEqual(stored_tables(path), expected_tables(path))


class RebuildOracleTest(Base):
    def test_twenty_seeds_against_model_and_source(self):
        for seed in range(24):
            chunk = (1, 2, 3, 7, 65536)[seed % 5]
            with self.subTest(seed=seed, chunk=chunk), \
                    mock.patch.object(numeric, "_REBUILD_CHUNK", chunk):
                path = os.path.join(self.dir.name, f"s{seed}.db")
                rng = random.Random(1700 + seed)
                st = self.open(path)
                model = {}
                for _ in range(rng.randrange(3, 10)):
                    ops = []
                    for _ in range(rng.randrange(1, 50)):
                        k = f"{rng.choice(GROUPS)}/{rng.randrange(30)}"
                        r = rng.random()
                        if r < 0.55:
                            x = rng.choice(EDGE + [rng.randrange(-10**12, 10**12)])
                            ops.append(("put", k, enc(x))); model[k] = x
                        elif r < 0.85:
                            ops.append(("delete", k)); model.pop(k, None)
                        else:
                            x = rng.choice(EDGE)
                            ops += [("delete", k), ("put", k, enc(x)), ("put", k, enc(x))]
                            model[k] = x
                    st.apply(ops)
                st.rebuild()
                self.check(st, model, path)
                st.close()
                st2 = self.open(path)          # persisted copy is the rebuilt one
                self.assertEqual(st2.open_mode, "PERSISTED")
                self.check(st2, model, path)

    def test_rebuild_twice_is_identical(self):
        st = self.open()
        st.apply([("put", f"{g}/{i}", enc(i * (-1) ** i)) for g in GROUPS for i in range(9)])
        st.rebuild()
        first = stored_tables(self.path)
        st.rebuild()
        self.assertEqual(stored_tables(self.path), first)
        self.assertEqual(first, expected_tables(self.path))

    def test_one_group_with_every_row_and_ties(self):
        with mock.patch.object(numeric, "_REBUILD_CHUNK", 4):
            st = self.open()
            model = {f"only/{i}": (i % 3) - 1 for i in range(50)}    # many ties
            st.apply([("put", k, enc(x)) for k, x in model.items()])
            st.rebuild()
            self.check(st, model)

    def test_many_groups_one_row_each(self):
        with mock.patch.object(numeric, "_REBUILD_CHUNK", 3):
            st = self.open()
            model = {f"g{i:03d}é/{i}": -i for i in range(200)}
            st.apply([("put", k, enc(x)) for k, x in model.items()])
            st.rebuild()
            self.check(st, model)

    def test_empty_source_and_empty_value_rejected(self):
        st = self.open()
        st.rebuild()
        self.assertEqual(stored_tables(self.path), expected_tables(self.path))
        with self.assertRaises(ValueError):
            st.apply([("put", "a/1", b"")])
        self.check(st, {})


class _FailingConnection:
    """Wraps the store's connection; fails the Nth bulk insert into the value index."""

    def __init__(self, db, fail_at):
        self._db, self._left = db, fail_at

    def executemany(self, sql, rows):
        if sql.startswith("INSERT INTO opdb_nlens_val"):
            self._left -= 1
            if self._left == 0:
                rows = list(rows)
                raise sqlite3.OperationalError("injected failure half way through insert")
        return self._db.executemany(sql, rows)

    def __getattr__(self, name):
        return getattr(self._db, name)


class RebuildFailureTest(Base):
    def seeded(self):
        st = self.open()
        model = {f"{g}/{i}": i - 4 for g in GROUPS for i in range(9)}
        st.apply([("put", k, enc(x)) for k, x in model.items()])
        return st, model

    def test_wrong_width_outside_write_leaves_lens_untouched(self):
        st, _model = self.seeded()
        before = stored_tables(self.path)
        c = con(self.path)
        c.execute("UPDATE opdb_source_kv SET v=x'0102' WHERE k='a/3'")
        c.commit(); c.close()
        with self.assertRaises(SourceIntegrityError):
            st.rebuild()
        self.assertEqual(stored_tables(self.path), before)
        self.assertFalse(st._trusted)
        with self.assertRaises(SourceIntegrityError):
            st.numeric_stats("a")

    def test_injected_error_mid_insert_rolls_back(self):
        st, model = self.seeded()
        real = st._db
        st.apply([("put", "b/new", enc(77))]); model["b/new"] = 77
        before = stored_tables(self.path)
        with mock.patch.object(numeric, "_REBUILD_CHUNK", 10):
            st._db = _FailingConnection(real, fail_at=3)
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    st.rebuild()
            finally:
                st._db = real
            self.assertFalse(st._trusted)
            # Previous Lens tables are exactly as committed by the last apply.
            self.assertEqual(stored_tables(self.path), before)
            st.rebuild()
        self.check(st, model)

    def test_overflow_still_falls_back_to_source(self):
        st = self.open()
        st.apply([("put", "big/1", enc(2**62)), ("put", "big/2", enc(2**62 - 1))])
        st.apply([("put", "big/3", enc(1))])          # sum reaches 2**63: overflow
        with self.assertRaises(LensOverflow):
            st.rebuild()
        s = st.numeric_stats("big")
        self.assertEqual(s.served_from, "SOURCE")
        self.assertEqual((s.count, s.total, s.minimum, s.maximum),
                         (3, 2**63, 1, 2**62))
        st.apply([("delete", "big/3")])
        st.rebuild()
        self.check(st, {"big/1": 2**62, "big/2": 2**62 - 1})


class SecondStoreTest(Base):
    def test_commit_by_one_store_rebuilds_the_other(self):
        a, b = self.open(), self.open()
        model = {}
        rng = random.Random(17)
        for _ in range(6):
            ops = []
            for _ in range(30):
                k = f"{rng.choice(GROUPS)}/{rng.randrange(20)}"
                x = rng.randrange(-10**6, 10**6)
                ops.append(("put", k, enc(x))); model[k] = x
            (a if rng.random() < 0.5 else b).apply(ops)
            for st in (a, b):
                self.check(st, model)


if __name__ == "__main__":
    unittest.main()
