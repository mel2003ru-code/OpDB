import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_handoff import validate

ROOT = Path(__file__).resolve().parents[1]

class HandoffValidationTests(unittest.TestCase):
    def check(self, obj):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"handoff.json"
            p.write_text(json.dumps(obj),encoding="utf-8")
            return validate(p)

    def sample(self):
        return json.loads((ROOT/"workstreams"/"HANDOFF_TEMPLATE.json").read_text(encoding="utf-8"))

    def test_template_is_valid_metadata(self):
        self.assertEqual(self.check(self.sample()),[])

    def test_missing_field(self):
        o=self.sample(); o.pop("task_id")
        self.assertTrue(self.check(o))

    def test_mismatched_stream(self):
        o=self.sample(); o["workstream"]="Core"
        self.assertIn("task/workstream mismatch",self.check(o))

    def test_pass_requires_reproduction(self):
        o=self.sample(); o["status"]="PASS"
        self.assertTrue(any("PASS requires" in e for e in self.check(o)))

    def test_pass_with_failed_tests(self):
        o=self.sample(); o.update(status="PASS", tested_environment="Linux", reproduce_commands=["python -m unittest"],tests_failed=["a"])
        self.assertTrue(any("failing tests" in e for e in self.check(o)))

    def test_bad_date_type(self):
        o=self.sample(); o["date_utc"]=123
        self.assertTrue(self.check(o))

    def test_impossible_date(self):
        o=self.sample(); o["date_utc"]="2026-02-30T00:00:00Z"
        self.assertTrue(any("calendar date" in e for e in self.check(o)))

if __name__=="__main__":
    unittest.main()
