import importlib.util
from pathlib import Path
import unittest

_spec = importlib.util.spec_from_file_location(
    "check_protected_paths",
    Path(__file__).resolve().parents[1] / "scripts" / "check_protected_paths.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


class ProtectedPathsTests(unittest.TestCase):
    def test_new_tests_and_engine_code_are_allowed(self):
        diff = "A\ttests/test_new.py\nM\topdb/core.py\nA\tworkstreams/TASK-008.md\nM\tworkstreams/BACKLOG.md"
        self.assertEqual(guard.violations(diff), [])

    def test_modifying_or_deleting_existing_tests_is_refused(self):
        self.assertEqual(len(guard.violations("M\ttests/test_lens_0_1.py")), 1)
        self.assertEqual(len(guard.violations("D\ttests/test_core_source_only.py")), 1)

    def test_renaming_an_existing_test_away_is_refused(self):
        found = guard.violations("R100\ttests/test_a.py\told/test_a.py")
        self.assertEqual(found, ["R100\ttests/test_a.py"])

    def test_workflows_rules_and_license_are_refused(self):
        diff = ("A\t.github/workflows/x.yml\nM\tAGENTS.md\nM\tROADMAP.md\n"
                "M\tLICENSE\nA\tdocs/adr/ADR-007.md\nM\tscripts/check_protected_paths.py")
        self.assertEqual(len(guard.violations(diff)), 6)


if __name__ == "__main__":
    unittest.main()
