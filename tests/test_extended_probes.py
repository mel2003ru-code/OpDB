"""Regression tests for the standalone SQLite/model research expansion."""
import unittest

from research.probes_extended import (
    probe_r01,probe_r02,probe_r04,probe_r05,probe_r06,probe_r08,probe_r09,
    probe_p0_negative_control
)


class ExtendedResearchTests(unittest.TestCase):
    def test_r01(self):
        self.assertGreater(probe_r01(101)["assertions"], 300)

    def test_r02(self):
        self.assertGreater(probe_r02(102)["sqlite_wal_bytes"], 0)

    def test_r04(self):
        self.assertEqual(probe_r04(103)["assertions"], 1800)

    def test_r05(self):
        self.assertEqual(probe_r05(104)["assertions"], 5)

    def test_r06(self):
        self.assertEqual(probe_r06(105)["assertions"], 5)

    def test_r08(self):
        r=probe_r08(106)
        self.assertEqual(r["count"],160)
        self.assertLessEqual(r["p95_us"],r["max_us"])

    def test_r09(self):
        self.assertEqual(probe_r09(107)["assertions"],7)

    def test_p0_expected_negative_control(self):
        self.assertEqual(probe_p0_negative_control(108)["outcome"],
                         "EXPECTED_STALE_LENS_DETECTED")


if __name__ == "__main__":
    unittest.main()
