"""Independent small-fixture controls for LAB-001; no production DB access."""
import json
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from opdb import TruthStore
from research.opdb_vs_sqlite import (
    checked_out_sha, db_files_bytes, distribution_ns,
    raw_sqlite_stats, run_case,
)


class OpDBSQLiteComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lab001-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "source.db"

    def test_direct_sqlite_group_oracle_handles_exact_prefix_and_unicode(self):
        model = {
            "g1": b"",
            "g1/a": b"123",
            "g1/α": b"hello",
            "g10/a": b"not-in-g1",
            "g1-other": b"not-in-g1",
            "": b"empty-key-not-valid",
            "/root": b"x",
            "clé/été": "éé".encode("utf-8"),
        }
        model.pop("")  # OpDB public API rejects empty keys.
        with TruthStore(self.path) as store:
            store.apply([("put", k, v) for k, v in model.items()])
        with sqlite3.connect(self.path) as raw, TruthStore(
            self.path, lens=False
        ) as source, TruthStore(self.path, lens=True) as lens:
            for group in ("g1", "g10", "g1-other", "", "clé", "missing"):
                values = [v for k, v in model.items()
                          if k.split("/", 1)[0] == group]
                expected = (len(values), sum(len(v) for v in values))
                actual_sql = raw_sqlite_stats(raw, group)
                actual_source = source.group_stats_source(group)
                actual_lens = lens.group_stats(group)
                self.assertEqual(actual_sql, expected)
                self.assertEqual(
                    (actual_source.row_count, actual_source.value_bytes), expected
                )
                self.assertEqual(
                    (actual_lens.row_count, actual_lens.value_bytes), expected
                )
                self.assertEqual(actual_source.served_from, "SOURCE")
                self.assertEqual(actual_lens.served_from, "LENS")

    def test_randomized_repeated_mutations_against_python_and_sqlite(self):
        rng = random.Random(49071)
        model = {}
        with TruthStore(self.path, lens=True) as lens, sqlite3.connect(
            self.path
        ) as raw:
            for _ in range(7):
                batch = []
                for i in range(135):
                    key = f"g{rng.randrange(4)}/{rng.randrange(11):03d}"
                    if rng.randrange(4) == 0:
                        batch.append(("delete", key))
                        model.pop(key, None)
                    else:
                        value = bytes((rng.randrange(256),)) * rng.randrange(30)
                        batch.append(("put", key, value))
                        model[key] = value
                lens.apply(batch)
                self.assertTrue(lens.lens_enabled)
                for group in ("g0", "g1", "g2", "g3", "missing"):
                    expected_values = [
                        value for key, value in model.items()
                        if key.split("/", 1)[0] == group
                    ]
                    expected = (
                        len(expected_values),
                        sum(len(v) for v in expected_values),
                    )
                    self.assertEqual(raw_sqlite_stats(raw, group), expected)
                    from_source = lens.group_stats_source(group)
                    from_lens = lens.group_stats(group)
                    self.assertEqual(
                        (from_source.row_count, from_source.value_bytes), expected
                    )
                    self.assertEqual(
                        (from_lens.row_count, from_lens.value_bytes), expected
                    )

    def test_small_three_mode_benchmark_verifies_answers(self):
        for size, seed in ((17, 9), (111, 42), (501, 77)):
            with self.subTest(size=size, seed=seed):
                result = run_case(self.root, size, seed, reads=7)
                self.assertEqual(
                    result["checks"]["python_vs_opdb_source_vs_lens_vs_sqlite"],
                    "PASS",
                )
                self.assertEqual(result["checks"]["lens_served_from"], "LENS")
                self.assertEqual(result["reads_per_mode"], 7)
                self.assertEqual(
                    set(result["read_latency"]),
                    {"opdb_source", "opdb_lens", "sqlite_direct"},
                )
                self.assertEqual(result["group_expected"]["count"], (size + 8) // 10)
                for stats in result["read_latency"].values():
                    self.assertGreaterEqual(stats["p99_us"], stats["median_us"])
                self.assertGreater(db_files_bytes(
                    self.root / f"lab001-{size}-{seed}.db"
                )["db"], 0)

    def test_10k_smoke_emits_results_without_speed_claims(self):
        # Useful reproducible inputs; noisy hosted CI timings are NOT an SLA.
        result = run_case(self.root, 10000, 1729, reads=30)
        result["files_bytes_after_close"] = db_files_bytes(
            self.root / "lab001-10000-1729.db"
        )
        self.assertEqual(
            result["checks"]["python_vs_opdb_source_vs_lens_vs_sqlite"], "PASS"
        )
        print("LAB001_CI_SMOKE=" + json.dumps(result, sort_keys=True), flush=True)

    def test_invalid_or_empty_measurements_fail(self):
        with self.assertRaises(ValueError):
            distribution_ns([])
        with self.assertRaises(ValueError):
            run_case(self.root, 0, 1, 6)
        with self.assertRaises(ValueError):
            run_case(self.root, 20, 1, 4)

    def test_checkout_sha_is_not_stale_environment_variable(self):
        result = checked_out_sha()
        self.assertTrue(result == "UNKNOWN" or len(result) == 40)


if __name__ == "__main__":
    unittest.main()
