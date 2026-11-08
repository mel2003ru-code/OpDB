"""Tests that deliberately unsafe derived-index designs remain falsifiable."""
import unittest
from research.p0_negative_control import probe_p0_negative_control


class P0NegativeControlTests(unittest.TestCase):
    def test_stale_and_forged_journal_counterexamples(self):
        for seed in (20261108, 203, 901):
            evidence=probe_p0_negative_control(seed)
            self.assertEqual(evidence["status"],"EXPECTED_COUNTEREXAMPLE")
            self.assertTrue(evidence["external_untracked_stale"])
            self.assertTrue(evidence["forged_journal_mismatch"])
            self.assertEqual(evidence["source_integrity"],"ok")


if __name__=="__main__":
    unittest.main()
