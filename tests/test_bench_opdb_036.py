import json
import os
import tempfile
import unittest

from experiments.bench import data, run
from experiments.bench.opdb_contenders import OpdbNumericContender, OpdbSourceContender


class ContenderTests(unittest.TestCase):
    def _roundtrip(self, cls, rows):
        with tempfile.TemporaryDirectory() as tmp:
            c = cls(os.path.join(tmp, "t.db"))
            try:
                c.bulk_insert(rows)
                self.assertEqual(c.count(), len(rows))
                for k, v in rows:
                    self.assertEqual(c.get(k), v)
                self.assertIsNone(c.get("missing"))
            finally:
                c.close()

    def test_source_roundtrip(self):
        self._roundtrip(OpdbSourceContender, data.make_rows(2000, 5, 16))

    def test_numeric_roundtrip(self):
        self._roundtrip(OpdbNumericContender, data.make_rows(2000, 5, 8, numeric=True))

    def test_applicability(self):
        self.assertTrue(OpdbSourceContender.applicable(16))
        self.assertTrue(OpdbSourceContender.applicable(8))
        self.assertFalse(OpdbNumericContender.applicable(16))
        self.assertTrue(OpdbNumericContender.applicable(8))


class NumericDataTests(unittest.TestCase):
    def test_numeric_values_are_bounded_and_deterministic(self):
        a = data.make_rows(500, 9, 8, numeric=True)
        self.assertEqual(a, data.make_rows(500, 9, 8, numeric=True))
        self.assertNotEqual(a, data.make_rows(500, 10, 8, numeric=True))
        for _, v in a:
            self.assertEqual(len(v), 8)
            self.assertLessEqual(abs(int.from_bytes(v, "big", signed=True)), 2 ** 40)
        self.assertNotEqual(a, data.make_rows(500, 9, 8, numeric=False))


class RunTests(unittest.TestCase):
    def _report(self, value_bytes):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            run.main(["--sizes", "500", "--runs", "2", "--seed", "4", "--value-bytes", str(value_bytes), "--contenders", "all", "--json", path])
            with open(path, encoding="utf-8") as f:
                return json.load(f)

    def test_value_16_marks_numeric_not_applicable(self):
        rep = self._report(16)
        by = {}
        for r in rep["results"]:
            by.setdefault(r["contender"], []).append(r)
        self.assertEqual(by["opdb_numeric_lens"], [{"contender": "opdb_numeric_lens", "size": 500,
                                                    "status": "NOT_APPLICABLE",
                                                    "reason": "needs 8-byte values, got 16"}])
        for name in ("sqlite", "opdb_source"):
            self.assertEqual(len(by[name]), 2)
            self.assertTrue(all(r["verified"] for r in by[name]))
        self.assertFalse(rep["numeric_values"])

    def test_value_8_runs_all_three(self):
        rep = self._report(8)
        timed = {r["contender"] for r in rep["results"] if r.get("verified")}
        self.assertEqual(timed, {"sqlite", "opdb_source", "opdb_numeric_lens"})
        self.assertTrue(rep["numeric_values"])

    def test_unknown_contender_is_rejected(self):
        with self.assertRaises(SystemExit):
            run.main(["--contenders", "nope"])


if __name__ == "__main__":
    unittest.main()
