"""TASK-006: deterministic Source and independent dict oracles for opt-in Lens."""
import os
import random
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from opdb import TruthStore


def expected(model, group):
    values = [value for key, value in model.items()
              if key.split('/', 1)[0] == group]
    return len(values), sum(map(len, values))


class LensTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = str(Path(self.folder.name) / 'data.db')
        self.db = TruthStore(self.path, lens=True)

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def check(self, model, groups):
        for group in groups:
            wanted = expected(model, group)
            accelerated = self.db.group_stats(group)
            reference = self.db.group_stats_source(group)
            self.assertEqual((accelerated.row_count, accelerated.value_bytes), wanted)
            self.assertEqual((reference.row_count, reference.value_bytes), wanted)
            self.assertEqual(reference.served_from, 'SOURCE')
            self.assertEqual(accelerated.served_from, 'LENS')

    def test_new_api_empty_groups_and_overwrite(self):
        self.assertTrue(self.db.lens_enabled)
        self.check({}, {'', 'missing', 'no-slash'})
        self.db.apply([('put', '/root', b''), ('put', 'no-slash', b'abc'),
                       ('put', 'a/1', b'xx'), ('put', 'a/2', b'yyy')])
        model = {'/root': b'', 'no-slash': b'abc', 'a/1': b'xx', 'a/2': b'yyy'}
        self.check(model, {'', 'a', 'no-slash', 'a/1', 'missing'})
        self.db.put('a/1', b'longer-value')
        model['a/1'] = b'longer-value'
        self.check(model, {'a'})
        self.db.apply([('delete', 'a/1'), ('delete', 'a/2')])
        self.check({'/root': b'', 'no-slash': b'abc'}, {'a', '', 'no-slash'})

    def test_seeded_20_by_2000_independent_oracle(self):
        # 20 separate seeded streams x 2,000 batches/ops; every touched
        # group checked on every iteration against a fresh Python dict oracle.
        for seed in range(20):
            rng = random.Random(20261110 + seed)
            model = {}
            groups = set()
            for i in range(2000):
                batch = []
                for _ in range(1 + (rng.randrange(5) if i % 9 == 0 else 0)):
                    group = ('orders', 'logs', 'users', '', 'no-slash')[rng.randrange(5)]
                    key = 'no-slash' if group == 'no-slash' else f'{group}/{rng.randrange(30)}'
                    groups.add(group)
                    if rng.randrange(4) == 0:
                        batch.append(('delete', key))
                        model.pop(key, None)
                    else:
                        value = rng.randbytes(rng.randrange(48))
                        batch.append(('put', key, value))
                        model[key] = value
                self.db.apply(batch)
                self.check(model, groups)

    def test_validation_and_mid_transaction_abort_do_not_advance(self):
        self.db.put('ok/1', b'abc')
        before = self.db.group_stats('ok')
        with sqlite3.connect(self.path) as conn:
            seq = conn.execute('SELECT commit_seq FROM opdb_meta').fetchone()[0]
        with self.assertRaises(ValueError):
            self.db.apply([('put', 'ok/2', b'x'), ('put', 'bad/2', 'not bytes')])
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TRIGGER reject_bad BEFORE INSERT ON opdb_source_kv "
                         "WHEN NEW.k='bad/1' BEGIN SELECT RAISE(ABORT,'test'); END")
        # A DDL outside write invalidates; refresh and then test rollback.
        self.assertEqual(self.db.group_stats('ok').served_from, 'SOURCE')
        self.assertTrue(self.db.lens_enabled)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.apply([('put', 'ok/3', b'y'), ('put', 'bad/1', b'z')])
        self.assertEqual(self.db.group_stats('ok'), before)
        self.assertTrue(self.db.lens_enabled)
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute('SELECT commit_seq FROM opdb_meta').fetchone()[0], seq)

    def test_untracked_writer_falls_back_then_rebuilds(self):
        self.db.put('g/x', b'first')
        self.assertEqual(self.db.group_stats('g').served_from, 'LENS')
        with sqlite3.connect(self.path) as conn:
            conn.execute("UPDATE opdb_source_kv SET v=? WHERE k='g/x'", (b'second-longer',))
        fallback = self.db.group_stats('g')
        self.assertEqual((fallback.row_count, fallback.value_bytes, fallback.served_from),
                         (1, 13, 'SOURCE'))
        self.assertEqual(self.db.group_stats('g').served_from, 'LENS')
        self.check({'g/x': b'second-longer'}, {'g'})

    def test_batch_10000_repeated_key(self):
        operations = [('put', 'hot/key', b'x' * (i % 30)) for i in range(10000)]
        self.db.apply(operations)
        self.check({'hot/key': b'x' * 9}, {'hot'})
        self.db.delete('hot/key')
        self.check({}, {'hot'})

    def test_crash_before_and_after_commit_rebuilds_from_source(self):
        self.db.put('g/x', b'old')
        self.db.close()
        before = (
            'import os,sys; from opdb import TruthStore; '
            's=TruthStore(sys.argv[1],lens=True); '
            's._db.execute("BEGIN IMMEDIATE"); '
            's._db.execute("UPDATE opdb_source_kv SET v=? WHERE k=?", (b"bad", "g/x")); '
            'os._exit(41)'
        )
        after = (
            'import os,sys; from opdb import TruthStore; '
            's=TruthStore(sys.argv[1],lens=True); '
            's.put("g/x", b"committed"); os._exit(42)'
        )
        for code, exit_code, value in ((before, 41, b'old'),
                                        (after, 42, b'committed')):
            proc = subprocess.run([sys.executable, '-c', code, self.path],
                                  check=False, env=os.environ.copy())
            self.assertEqual(proc.returncode, exit_code)
            with TruthStore(self.path, lens=True) as reopened:
                result = reopened.group_stats('g')
                self.assertEqual(result.served_from, 'LENS')
                self.assertEqual((result.row_count, result.value_bytes), (1, len(value)))
                self.assertEqual(reopened.group_stats_source('g').value_bytes, len(value))
        self.db = TruthStore(self.path, lens=True)


if __name__ == '__main__':
    unittest.main()
