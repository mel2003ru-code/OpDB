"""TASK-009 seeded overwrite/delete oracle tests."""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import TruthStore


def _group(key):
    return key.split('/', 1)[0]


def _raw_source(path):
    db = sqlite3.connect(path)
    try:
        rows = db.execute(
            'SELECT k, v, typeof(v) FROM opdb_source_kv ORDER BY k'
        ).fetchall()
    finally:
        db.close()
    if any(storage != 'blob' or type(value) is not bytes
           for _, value, storage in rows):
        raise AssertionError('Source contains a non-BLOB value')
    return {key: value for key, value, _ in rows}


class OverwriteLensOracleTests(unittest.TestCase):
    def assert_state(self, path, store, model):
        self.assertEqual(_raw_source(path), model)
        groups = {_group(key) for key in model} | {'', 'missing', 'plain'}
        for group in groups:
            values = [value for key, value in model.items()
                      if _group(key) == group]
            expected = (len(values), sum(map(len, values)))
            source = store.group_stats_source(group)
            lens = store.group_stats(group)
            self.assertEqual((source.row_count, source.value_bytes), expected)
            self.assertEqual((lens.row_count, lens.value_bytes), expected)
            self.assertEqual(source.served_from, 'SOURCE')
            self.assertEqual(lens.served_from, 'LENS')
        self.assertTrue(store.lens_enabled)

    def test_twenty_seeds_overwrite_lengths_delete_and_reinsert(self):
        for seed in range(20):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'source.db'
                rng = random.Random(9009 + seed)
                model = {
                    (f'g{index % 4}/{index:04d}' if index % 5 else
                     (f'clé/{index:04d}' if index % 10 else f'plain{index}')):
                    bytes([index % 251]) * 8
                    for index in range(40)
                }
                with TruthStore(path, lens=True) as store:
                    store.apply([('put', key, value)
                                 for key, value in model.items()])
                    self.assert_state(path, store, model)

                    for batch_size in (1, 51, 727, 2000):
                        actions = []
                        if batch_size >= 6:
                            # Explicit 0, shorter, equal and longer overwrites.
                            existing = rng.sample(list(model), 5)
                            for key, length in zip(existing[:4], (0, 3, 8, 13)):
                                actions.append(('put', key,
                                                rng.randbytes(length)))
                            # A delete followed by a reinsert of the same key.
                            key = existing[4]
                            actions.extend([('delete', key),
                                             ('put', key, rng.randbytes(
                                                 rng.choice((0, 3, 8, 13))))])
                        while len(actions) < batch_size:
                            key = rng.choice(list(model) +
                                             [f'new{seed}/{rng.randrange(50):03d}'])
                            choice = rng.randrange(5)
                            if choice == 0:
                                actions.append(('delete', key))
                            else:
                                length = rng.choice((0, 3, 8, 13))
                                actions.append(('put', key,
                                                rng.randbytes(length)))
                        for action in actions:
                            if action[0] == 'delete':
                                model.pop(action[1], None)
                            else:
                                model[action[1]] = action[2]
                        store.apply(actions)
                        self.assert_state(path, store, model)


    def test_repeated_key_operations_preserve_order(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'source.db'
            model = {'g/repeated': b'start', 'g/other': b'other'}
            with TruthStore(path, lens=True) as store:
                store.apply([('put', key, value) for key, value in model.items()])
                operations = [
                    ('put', 'g/repeated', b'first'),
                    ('delete', 'g/repeated'),
                    ('put', 'g/repeated', b'final'),
                    ('delete', 'g/other'),
                    ('put', 'g/other', b'restored'),
                ]
                for action in operations:
                    if action[0] == 'delete':
                        model.pop(action[1], None)
                    else:
                        model[action[1]] = action[2]
                store.apply(operations)
                self.assert_state(path, store, model)


if __name__ == '__main__':
    unittest.main()
