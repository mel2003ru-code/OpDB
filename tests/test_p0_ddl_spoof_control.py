"""Independent negative control only; the real Proof Gate is NOT VERIFIED."""
import unittest

from research.p0_ddl_spoof_control import probe_p0_ddl_spoof


class P0DDLSpoofTests(unittest.TestCase):
    def test_privileged_ddl_can_bypass_trigger_and_schema_cookie(self):
        for seed in (203, 901, 20261108):
            with self.subTest(seed=seed):
                evidence = probe_p0_ddl_spoof(seed)
                self.assertEqual(evidence["status"], "EXPECTED_COUNTEREXAMPLE")
                self.assertEqual(evidence["seed"], seed)
                self.assertEqual(evidence["assertions"], 7)
                self.assertEqual(set(evidence["checks"].values()), {True})


if __name__ == "__main__":
    unittest.main()
