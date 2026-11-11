"""TASK-011: batches by kind checked against a plain dict and raw SQLite."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import TruthStore
from experiments.lens_batch_hotspots import SCENARIOS, make_batch, VALUE, existing_key

GROUPS = ['a', 'b', 'ключ', '日本', 'é', '']


def model_stats(model, group):
    sizes = [len(v) for k, v in model.items() if k.split('/', 1)[0] == group]
    return len(sizes), sum(sizes)


def sqlite_rows(path):
    conn = sqlite3.connect(path)
    try:
        return dict(conn.execute('SELECT k, v FROM opdb_source_kv'))
    finally:
        conn.close()


def apply_model(model, ops):
    for op in ops:
        if op[0] == 'put':
            model[op[1]] = op[2]
        else:
            model.pop(op[1], None)


class HotspotBatchTests(unittest.TestCase):
    def check(self, path, stores, model, groups):
        self.assertEqual(sqlite_rows(path), model)
        for store in stores:
            for g in groups:
                want = model_stats(model, g)
                for got in (store.group_stats(g), store.group_stats_source(g)):
                    self.assertEqual((got.row_count, got.value_bytes), want, g)

    def test_scenarios_with_seeds_and_second_store(self):
        size = 2000
        base = {existing_key(i): VALUE for i in range(size)}
        groups = [f'g{i}' for i in range(10)]
        for kind in SCENARIOS:
            for seed in (1, 7, 99):
                with tempfile.TemporaryDirectory() as temp:
                    path = Path(temp) / 'kv.db'
                    with TruthStore(path) as seed_store:
                        seed_store.apply([('put', k, v) for k, v in base.items()])
                    model = dict(base)
                    with TruthStore(path, lens=True) as lens, TruthStore(path) as plain:
                        for batch in range(3):
                            ops, restore = make_batch(kind, size, seed, batch)
                            self.assertEqual(len(ops), 1000)
                            self.assertEqual((ops, restore),
                                             make_batch(kind, size, seed, batch))
                            writer = plain if batch == 1 else lens
                            writer.apply(ops)
                            apply_model(model, ops)
                            self.check(path, [lens, plain], model, groups)
                            lens.apply(restore)
                            apply_model(model, restore)
                            self.assertEqual(model, base, (kind, seed, batch))
                            self.check(path, [lens, plain], model, groups)

    def test_edge_batch_matches_model(self):
        for seed in range(6):
            rng = random.Random(seed)
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'kv.db'
                model = {}
                with TruthStore(path, lens=True) as store:
                    for _ in range(8):
                        ops = []
                        for _ in range(rng.randrange(1, 300)):
                            key = f'{rng.choice(GROUPS)}/{rng.randrange(25)}'
                            r = rng.random()
                            if r < 0.5:
                                ops.append(('put', key, bytes([rng.randrange(256)]) * rng.choice([0, 1, 50])))
                            elif r < 0.8:
                                ops.append(('delete', key))  # often absent
                            else:  # delete-then-put on the same key
                                ops += [('delete', key), ('put', key, b'')]
                        store.apply(ops)
                        apply_model(model, ops)
                        self.check(path, [store], model, GROUPS)

    def test_failed_batch_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'kv.db'
            with TruthStore(path, lens=True) as store:
                store.apply([('put', 'a/1', b'xyz')])
                with self.assertRaises(ValueError):
                    store.apply([('delete', 'a/1'), ('put', 'a/2', b'q'), ('put', 'a/3', 'bad')])
                self.check(path, [store], {'a/1': b'xyz'}, GROUPS)


if __name__ == '__main__':
    unittest.main()
