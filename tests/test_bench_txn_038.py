import json
import os
import tempfile
import unittest

from experiments.bench import data, run, transactions
from experiments.bench.opdb_contenders import OpdbNumericContender, OpdbSourceContender
from experiments.bench.sqlite_contender import SqliteContender


class TransactionTests(unittest.TestCase):
    def test_commit_many(self):
        rows = data.make_rows(1000, 2, 16)
        with tempfile.TemporaryDirectory() as tmp:
            for cls in (SqliteContender, OpdbSourceContender):
                c = cls(os.path.join(tmp, cls.__name__ + ".db"))
                try:
                    self.assertEqual(transactions.commit_many(c, rows), 10)
                    self.assertEqual(c.count(), 1000)
                    for k, v in rows:
                        self.assertEqual(c.get(k), v)
                finally:
                    c.close()

    def test_rollback_leaves_no_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            for cls, numeric in ((SqliteContender, False), (OpdbSourceContender, False),
                                 (OpdbNumericContender, True)):
                rows = data.make_rows(400, 3, 8, numeric=numeric)
                c = cls(os.path.join(tmp, cls.__name__ + ".db"))
                try:
                    self.assertEqual(transactions.rollback_check(c, rows), [], cls.__name__)
                    self.assertEqual(c.count(), 200)
                    for k, v in rows[:200]:
                        self.assertEqual(c.get(k), v)
                finally:
                    c.close()

    def test_crash_check_sqlite(self):
        rows = data.make_rows(400, 4, 16)
        with tempfile.TemporaryDirectory() as tmp:
            keys, integrity = transactions.crash_check(os.path.join(tmp, "crash.db"), rows)
        self.assertEqual(keys, {k for k, _ in rows[:200]})
        self.assertEqual(integrity, "ok")


class RunTests(unittest.TestCase):
    def test_report_has_timings_verdicts_and_gaps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            run.main(["--sizes", "500", "--runs", "2", "--seed", "5", "--value-bytes", "8", "--contenders", "all",
                      "--workloads", "txn_commit,txn_rollback,txn_crash", "--json", path])
            with open(path, encoding="utf-8") as f:
                rep = json.load(f)
        rows = {(r["contender"], r["workload"]): r for r in rep["results"]}
        for name in ("sqlite", "opdb_source", "opdb_numeric_lens"):
            self.assertTrue(rows[(name, "txn_commit")]["verified"], name)
            self.assertEqual(len(rows[(name, "txn_commit")]["runs"]), 2)
            self.assertEqual(rows[(name, "txn_commit")]["commits"], 5)
            self.assertEqual(rows[(name, "txn_rollback")]["status"], "PASS")
        self.assertEqual(rows[("sqlite", "txn_crash")]["status"], "PASS")
        for name in ("opdb_source", "opdb_numeric_lens"):
            self.assertEqual(rows[(name, "txn_crash")]["status"], "NOT_IMPLEMENTED")

    def test_small_size_is_rejected(self):
        with self.assertRaises(SystemExit):
            run.main(["--sizes", "100", "--workloads", "txn_commit"])


if __name__ == "__main__":
    unittest.main()
