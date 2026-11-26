import json
import os
import tempfile
import unittest

from experiments.bench import data, run, workloads
from experiments.bench.opdb_contenders import OpdbNumericContender, OpdbSourceContender
from experiments.bench.sqlite_contender import SqliteContender


class WorkloadTests(unittest.TestCase):
    def test_pick_groups(self):
        a = workloads.pick_groups(3)
        self.assertEqual(a, workloads.pick_groups(3))
        self.assertEqual(len(set(a)), 50)
        self.assertTrue(all(0 <= g < 1000 for g in a))
        self.assertNotEqual(a, workloads.pick_groups(4))

    def test_model_answers_on_a_small_set(self):
        rows = [("grp1/1", b"\x00"), ("grp1/2", b"\xff"), ("grp10/1", b"\x01"), ("grp2/1", b"\x7f")]
        self.assertEqual(workloads.expected_range_count(rows, 1), 2)
        self.assertEqual(workloads.expected_range_count(rows, 10), 1)
        self.assertEqual(workloads.expected_filter_count(rows, 1), 1)
        self.assertEqual(workloads.expected_filter_count(rows, 2), 1)
        self.assertEqual(workloads.expected_filter_count(rows, 7), 0)


class ContenderReadTests(unittest.TestCase):
    def test_range_and_filter_match_the_model(self):
        rows = data.make_rows(3000, 6, 8, numeric=True)  # 3 rows per group; 8-byte ints fit every contender
        groups = [0, 1, 10, 100, 999, 5]
        with tempfile.TemporaryDirectory() as tmp:
            contenders = [SqliteContender(os.path.join(tmp, "a.db")),
                          OpdbSourceContender(os.path.join(tmp, "b.db")),
                          OpdbNumericContender(os.path.join(tmp, "c.db"))]
            try:
                for c in contenders:
                    c.bulk_insert(rows)
                    for g in groups:
                        self.assertEqual(c.range_count(g), workloads.expected_range_count(rows, g), c.name)
                self.assertEqual(
                    [contenders[0].filter_count(g) for g in groups],
                    [workloads.expected_filter_count(rows, g) for g in groups])
                self.assertFalse(hasattr(contenders[1], "filter_count"))
                self.assertFalse(hasattr(contenders[2], "filter_count"))
            finally:
                for c in contenders:
                    c.close()


class RunTests(unittest.TestCase):
    def test_read_workloads_in_the_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            run.main(["--sizes", "3000", "--runs", "2", "--seed", "5", "--value-bytes", "8",
                      "--contenders", "all", "--workloads", "range_scan,filter", "--json", path])
            with open(path, encoding="utf-8") as f:
                rep = json.load(f)
        rows = {(r["contender"], r["workload"]): r for r in rep["results"]}
        for name in ("sqlite", "opdb_source", "opdb_numeric_lens"):
            self.assertTrue(rows[(name, "range_scan")]["verified"], name)
            self.assertEqual(len(rows[(name, "range_scan")]["runs"]), 2)
        self.assertTrue(rows[("sqlite", "filter")]["verified"])
        for name in ("opdb_source", "opdb_numeric_lens"):
            self.assertEqual(rows[(name, "filter")], {"contender": name, "size": 3000, "workload": "filter",
                                                      "status": "NOT_IMPLEMENTED"})

    def test_unknown_workload_is_rejected(self):
        with self.assertRaises(SystemExit):
            run.main(["--workloads", "nope"])


if __name__ == "__main__":
    unittest.main()
