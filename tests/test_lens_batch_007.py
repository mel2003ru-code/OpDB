"""TASK-007: independent Python-dict and raw-SQLite Source oracles."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import SourceIntegrityError, TruthStore


def group_of(key):
    return key.split("/", 1)[0]


class BatchLensOracleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def path(self, name):
        return str(Path(self.temp.name) / name)

    def assert_matches(self, path, store, model):
        # This reference is computed without calling Lens or Source APIs.
        with sqlite3.connect(path) as raw:
            rows = raw.execute(
                "SELECT k, v, typeof(v) FROM opdb_source_kv ORDER BY k"
            ).fetchall()
        self.assertTrue(all(storage == "blob" for _, _, storage in rows))
        source = {key: value for key, value, _ in rows}
        self.assertEqual(source, model)
        groups = {group_of(k) for k in source} | {"", "missing", "hot", "clé"}
        for group in groups:
            values = [v for k, v in model.items() if group_of(k) == group]
            expected = (len(values), sum(len(v) for v in values))
            from_source = store.group_stats_source(group)
            from_lens = store.group_stats(group)
            self.assertEqual((from_source.row_count, from_source.value_bytes), expected)
            self.assertEqual((from_lens.row_count, from_lens.value_bytes), expected)
            self.assertEqual(from_source.served_from, "SOURCE")
            self.assertEqual(from_lens.served_from, "LENS")
        self.assertTrue(store.lens_enabled)

    def test_20_seeds_repeated_keys_and_mixed_mutations(self):
        # Six batches per seed, from 1 through 2,000 operations. The key
        # population is deliberately tiny relative to the operation count.
        sizes = (1, 7, 51, 501, 1001, 2000)
        for seed in range(20):
            with self.subTest(seed=seed):
                rng = random.Random(77000 + seed)
                path = self.path(f"seed-{seed}.db")
                model = {}
                with TruthStore(path, lens=True) as store:
                    for size in sizes:
                        actions = []
                        for _ in range(size):
                            group = rng.choice(("hot", "", "clé", "x", "literal"))
                            key = ("literal" if group == "literal"
                                   else f"{group}/{rng.randrange(20)}")
                            if rng.randrange(4) == 0:
                                actions.append(("delete", key))
                                model.pop(key, None)
                            else:
                                value = rng.randbytes(rng.randrange(80))
                                actions.append(("put", key, value))
                                model[key] = value
                        store.apply(actions)
                        self.assert_matches(path, store, model)

    def test_more_than_one_lookup_chunk_existing_and_new(self):
        path = self.path("chunks.db")
        model = {}
        with TruthStore(path, lens=True) as store:
            initial = []
            for i in range(620):
                key = f"hot/{i:04d}"
                value = bytes((i % 256,)) * (i % 19)
                initial.append(("put", key, value))
                model[key] = value
            store.apply(initial)
            actions = []
            for i in range(1250):
                key = f"hot/{i:04d}"
                if i % 7 == 0:
                    actions.append(("delete", key))
                    model.pop(key, None)
                else:
                    value = b"x" * (i % 33)
                    actions.append(("put", key, value))
                    model[key] = value
            # A deleted key is reinserted, overwritten, and deleted again.
            for key in ("hot/0000", "hot/0620", "hot/0999"):
                actions.extend([("delete", key), ("put", key, b"reinsert"),
                                ("put", key, b""), ("delete", key)])
                model.pop(key, None)
            store.apply(actions)
            self.assert_matches(path, store, model)

    def test_damaged_row_opens_source_only_and_reads_stay_strict(self):
        path = self.path("damaged.db")
        with TruthStore(path) as writer:
            writer.put("bad/row", b"valid")
            writer.put("fine/row", b"ok")
        with sqlite3.connect(path) as raw:
            raw.execute("UPDATE opdb_source_kv SET v=123 WHERE k='bad/row'")
        with TruthStore(path, lens=True) as store:
            self.assertFalse(store.lens_enabled)
            good = store.group_stats("fine")
            self.assertEqual((good.row_count, good.value_bytes, good.served_from),
                             (1, 2, "SOURCE"))
            with self.assertRaises(SourceIntegrityError):
                store.get("bad/row")
            with self.assertRaises(SourceIntegrityError):
                store.group_stats("bad")
            store.put("fine/new", b"hello")
            self.assertEqual(store.group_stats("fine").served_from, "SOURCE")
