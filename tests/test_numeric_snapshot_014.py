"""Independent interleavings: every numeric answer belongs to one Source state."""
import os
import tempfile
import unittest
from unittest.mock import patch

from opdb import NumericTruthStore, TruthStore


def enc(value):
    return value.to_bytes(8, "big", signed=True)


def values(stats):
    return stats.count, stats.total, stats.minimum, stats.maximum


class NumericSnapshotTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "numeric.db")

    def test_answer_does_not_mix_generations_during_extreme_lookup(self):
        with NumericTruthStore(self.path) as reader:
            reader.put("g/1", enc(1))
            with NumericTruthStore(self.path) as writer:
                original = reader._extreme
                fired = False

                def interleave(group, order):
                    nonlocal fired
                    if not fired:
                        fired = True
                        writer.put("g/2", enc(100))
                    return original(group, order)

                with patch.object(reader, "_extreme", interleave):
                    answer = values(reader.numeric_stats("g"))
                self.assertTrue(fired)
                self.assertIn(answer, [(1, 1, 1, 1), (2, 101, 1, 100)])
                self.assertEqual(values(reader.numeric_stats("g")), (2, 101, 1, 100))

    def test_commit_after_rebuild_cannot_become_trusted_baseline(self):
        with NumericTruthStore(self.path) as reader, TruthStore(self.path) as writer:
            reader.apply([("put", "g/1", enc(1)), ("put", "g/5", enc(5))])
            real = reader._db

            class AfterCommit:
                fired = False

                def execute(self, sql, *args):
                    result = real.execute(sql, *args)
                    if sql == "COMMIT" and not self.fired:
                        self.fired = True
                        writer.put("g/3", enc(3))
                    return result

                def __getattr__(self, name):
                    return getattr(real, name)

            proxy = AfterCommit()
            with patch.object(reader, "_db", proxy):
                reader.rebuild()
            self.assertTrue(proxy.fired)
            for _ in range(2):
                self.assertEqual(values(reader.numeric_stats("g")), (3, 9, 1, 5))

    def test_commit_after_open_validation_is_observed(self):
        with NumericTruthStore(self.path) as initial:
            initial.apply([("put", "g/1", enc(1)), ("put", "g/5", enc(5))])
        with TruthStore(self.path) as writer:
            original = NumericTruthStore._validate

            def interleave(store):
                result = original(store)
                writer.put("g/3", enc(3))
                return result

            with patch.object(NumericTruthStore, "_validate", interleave):
                reader = NumericTruthStore(self.path)
            with reader:
                self.assertEqual(values(reader.numeric_stats("g")), (3, 9, 1, 5))


if __name__ == "__main__":
    unittest.main()
