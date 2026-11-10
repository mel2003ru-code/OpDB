"""TASK-007: seeded independent dict/Source oracles and batched lookup limits."""
import random
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import SourceIntegrityError, TruthStore


def model_stats(model, group):
    values = [value for key, value in model.items()
              if key.split('/', 1)[0] == group]
    return len(values), sum(len(value) for value in values)


class BatchLensTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'source.db'

    def tearDown(self):
        self.temp.cleanup()

    def verify(self, store, model, groups):
        for group in groups:
            reference = store.group_stats_source(group)
            accelerated = store.group_stats(group)
            want = model_stats(model, group)
            self.assertEqual((reference.row_count, reference.value_bytes), want)
            self.assertEqual((accelerated.row_count, accelerated.value_bytes), want)
            self.assertEqual(reference.served_from, 'SOURCE')
            self.assertEqual(accelerated.served_from, 'LENS')

    def test_seeded_repeated_batches_against_both_oracles(self):
        # 20 independent seeds, 1-2000 actions per batch. Same key is
        # frequently deleted and reinserted, including zero-byte values.
        for seed in range(20):
            rng = random.Random(7007 + seed)
            model = {}
            with TruthStore(self.path, lens=True) as store:
                for size in (1, 51, 727, 2000):
                    actions = []
                    for i in range(size):
                        group = ('g', 'other', '', 'no-slash')[rng.randrange(4)]
                        key = 'no-slash' if group == 'no-slash' else f'{group}/{rng.randrange(18)}'
                        # Deliberately couple a delete with a later put.
                        if i % 7 == 0 or rng.randrange(3) == 0:
                            actions.append(('delete', key))
                            model.pop(key, None)
                        else:
                            value = rng.randbytes(rng.randrange(50))
                            actions.append(('put', key, value))
                            model[key] = value
                    store.apply(actions)
                    self.assertTrue(store.lens_enabled)
                    self.verify(store, model, ('g', 'other', '', 'no-slash', 'absent'))
            self.path.unlink()

    def test_more_than_two_lookup_chunks_and_existing_new_keys(self):
        model = {f'g/{i:04d}': b'x' * (i % 9)
                 for i in range(600)}
        with TruthStore(self.path, lens=True) as store:
            store.apply([('put', key, value) for key, value in model.items()])
            actions = []
            for i in range(1101):
                key = f'g/{i:04d}'
                if i % 4 == 0:
                    actions.append(('delete', key))
                    model.pop(key, None)
                else:
                    value = bytes([i % 256]) * (i % 21)
                    actions.append(('put', key, value))
                    model[key] = value
            # A repeated key must not produce another SQL read.
            actions.extend([('delete', 'g/0001'), ('put', 'g/0001', b'!')])
            model['g/0001'] = b'!'
            read_queries = []
            store._db.set_trace_callback(lambda sql: read_queries.append(sql)
                                         if 'SELECT k,typeof(v),length(v) FROM opdb_source_kv WHERE k IN'
                                         in sql else None)
            try:
                store.apply(actions)
            finally:
                store._db.set_trace_callback(None)
            self.assertEqual(len(read_queries), 3)  # 500 + 500 + 101
            self.verify(store, model, ('g', 'absent'))

    def test_damaged_source_disables_lens_without_masking_bad_reads(self):
        with TruthStore(self.path, lens=False) as store:
            store.put('ok/1', b'abc')
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('INSERT INTO opdb_source_kv VALUES (?,?)',
                               ('broken/1', 21))
        with TruthStore(self.path, lens=True) as store:
            self.assertFalse(store.lens_enabled)
            self.assertEqual(store.group_stats('ok').served_from, 'SOURCE')
            self.assertEqual((store.group_stats('ok').row_count,
                              store.group_stats('ok').value_bytes), (1, 3))
            self.assertEqual(store.get('ok/1'), b'abc')
            with self.assertRaises(SourceIntegrityError):
                store.get('broken/1')
            with self.assertRaises(SourceIntegrityError):
                store.group_stats('broken')
            with self.assertRaises(SourceIntegrityError):
                store.scan()

    def test_oversized_blob_disables_lens(self):
        with TruthStore(self.path, lens=False):
            pass
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute('INSERT INTO opdb_source_kv VALUES (?,?)',
                               ('broken/huge', b'x' * (1024 * 1024 + 1)))
        with TruthStore(self.path, lens=True) as store:
            self.assertFalse(store.lens_enabled)
            self.assertEqual(store.group_stats('ok').served_from, 'SOURCE')
            with self.assertRaises(SourceIntegrityError):
                store.get('broken/huge')


if __name__ == '__main__':
    unittest.main()
