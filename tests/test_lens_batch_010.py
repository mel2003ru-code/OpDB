"""TASK-010: batch writes checked against a plain dict model and raw SQLite."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import TruthStore
from experiments.m2_batch_check import make_batch

GROUPS = ['a', 'b', 'ключ', '日本', 'é', '']


def model_stats(model, group):
    sizes = [len(v) for k, v in model.items() if k.split('/', 1)[0] == group]
    return len(sizes), sum(sizes)


def sqlite_rows(path):
    conn = sqlite3.connect(path)
    try:
        return dict(conn.execute('SELECT k, v FROM opdb_source_kv'))
    finally:
        conn.close()


def random_batch(rng):
    ops = []
    for _ in range(rng.randrange(1, 400)):
        key = f'{rng.choice(GROUPS)}/{rng.randrange(60)}'
        if rng.random() < 0.7:
            ops.append(('put', key, bytes([rng.randrange(256)]) * rng.choice([0, 1, 7, 100])))
        else:
            ops.append(('delete', key))
    return ops


def apply_model(model, ops):
    for op in ops:
        if op[0] == 'put':
            model[op[1]] = op[2]
        else:
            model.pop(op[1], None)


class BatchModelTests(unittest.TestCase):
    def check(self, path, stores, model):
        self.assertEqual(sqlite_rows(path), model)
        for store in stores:
            for g in GROUPS:
                expected = model_stats(model, g)
                for got in (store.group_stats(g), store.group_stats_source(g)):
                    self.assertEqual((got.row_count, got.value_bytes), expected, g)

    def test_seeded_batches_with_second_store(self):
        for seed in range(8):
            rng = random.Random(seed)
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'kv.db'
                model = {}
                with TruthStore(path, lens=True) as lens, TruthStore(path) as plain:
                    self.assertTrue(lens.lens_enabled)
                    for _ in range(12):
                        ops = random_batch(rng)
                        lens.apply(ops)
                        apply_model(model, ops)
                        self.check(path, [lens], model)
                with TruthStore(path, lens=True) as reopened:
                    self.check(path, [reopened], model)

    def test_failed_batch_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'kv.db'
            with TruthStore(path, lens=True) as store:
                store.apply([('put', 'a/1', b'xyz'), ('put', 'b/1', b'')])
                model = {'a/1': b'xyz', 'b/1': b''}
                bad = [('put', 'a/1', b'new'), ('delete', 'b/1'),
                       ('put', 'a/2', b'q'), ('put', 'a/3', 'not bytes')]
                with self.assertRaises(ValueError):
                    store.apply(bad)
                self.check(path, [store], model)
                store.apply([('delete', 'a/1')])
                del model['a/1']
                self.check(path, [store], model)

    def test_benchmark_batch_generator_matches_model(self):
        size = 3000
        base = {f'g{i % 10}/{i:09d}': b'X' * 100 for i in range(size)}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'kv.db'
            with TruthStore(path) as seed_store:
                seed_store.apply([('put', k, v) for k, v in base.items()])
            model = dict(base)
            with TruthStore(path, lens=True) as store:
                for batch in range(4):
                    ops, restore = make_batch(size, 10, batch)
                    self.assertEqual(len(ops), 1000)
                    self.assertEqual((ops, restore), make_batch(size, 10, batch))
                    store.apply(ops)
                    apply_model(model, ops)
                    for g in range(10):
                        got = store.group_stats(f'g{g}')
                        self.assertEqual((got.row_count, got.value_bytes),
                                         model_stats(model, f'g{g}'))
                    store.apply(restore)
                    apply_model(model, restore)
                    self.assertEqual(model, base)
                    self.assertEqual(sqlite_rows(path), base)


if __name__ == '__main__':
    unittest.main()
