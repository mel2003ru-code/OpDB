"""TASK-009 benchmark scenario smoke test."""
import tempfile
import unittest
from pathlib import Path

from experiments.lens_bench import run


class LensBenchScenarioTests(unittest.TestCase):
    def test_three_scenarios_on_two_thousand_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            result = run(2000, Path(temp), reads=2, puts=2, batches=3)
            self.assertEqual(set(result['batch_scenarios']),
                             {'overwrite', 'delete', 'mixed'})
            for scenario in result['batch_scenarios'].values():
                self.assertEqual(scenario['batches'], 3)
                self.assertGreater(scenario['source_median_batch_ms'], 0)
                self.assertGreater(scenario['lens_median_batch_ms'], 0)
                self.assertIsInstance(scenario['lens_overhead_percent'], float)
            # Existing benchmark output keys remain present and unchanged.
            for key in ('rows', 'value_bytes', 'reads', 'batches', 'source',
                        'lens', 'lens_rebuild_ms', 'lens_peak_tracemalloc_bytes',
                        'write_rates', 'write_overhead_percent',
                        'lens_read_faster', 'write_overhead_over_20pct'):
                self.assertIn(key, result)


if __name__ == '__main__':
    unittest.main()
