import json
import os
import tempfile
import unittest

from experiments.bench import data, run, timing
from experiments.bench.sqlite_contender import SqliteContender


class DataTests(unittest.TestCase):
    def test_deterministic_and_seeded(self):
        a, b = data.make_rows(5000, 7, 16), data.make_rows(5000, 7, 16)
        self.assertEqual(a, b)
        self.assertEqual(data.digest(a), data.digest(b))
        self.assertNotEqual(data.digest(a), data.digest(data.make_rows(5000, 8, 16)))
        self.assertEqual(len({k.split("/")[0] for k, _ in a}), 1000)
        self.assertEqual(len({k for k, _ in a}), 5000)
        self.assertTrue(all(len(v) == 16 for _, v in a))


class TimingTests(unittest.TestCase):
    def test_summarize_odd_and_even(self):
        s = timing.summarize([3.0, 1.0, 2.0])
        self.assertEqual((s["median_ms"], s["min_ms"], s["max_ms"]), (2.0, 1.0, 3.0))
        s = timing.summarize([4.0, 1.0, 2.0, 3.0])
        self.assertEqual((s["median_ms"], s["min_ms"], s["max_ms"]), (2.5, 1.0, 4.0))
        self.assertEqual(s["runs"], [4.0, 1.0, 2.0, 3.0])

    def test_measure_with_fake_timer(self):
        ticks = iter([0, 2_000_000, 10_000_000, 15_000_000])
        self.assertEqual(timing.measure(lambda: None, 2, timer=lambda: next(ticks)), [2.0, 5.0])

    def test_machine_info(self):
        self.assertEqual(set(timing.machine_info()), {"python", "sqlite", "platform", "cpu_count"})


class SqliteContenderTests(unittest.TestCase):
    def test_roundtrip_and_pragmas(self):
        rows = data.make_rows(2000, 3, 16)
        with tempfile.TemporaryDirectory() as tmp:
            c = SqliteContender(os.path.join(tmp, "t.db"))
            try:
                c.bulk_insert(rows)
                self.assertEqual(c.count(), 2000)
                for k, v in rows:
                    self.assertEqual(c.get(k), v)
                self.assertIsNone(c.get("missing"))
                self.assertEqual(c.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
                self.assertEqual(c.db.execute("PRAGMA synchronous").fetchone()[0], 2)  # FULL
            finally:
                c.close()

    def test_synchronous_is_configurable(self):
        with tempfile.TemporaryDirectory() as tmp:
            c = SqliteContender(os.path.join(tmp, "t.db"), synchronous="NORMAL")
            try:
                self.assertEqual(c.db.execute("PRAGMA synchronous").fetchone()[0], 1)
            finally:
                c.close()


class RunTests(unittest.TestCase):
    def _run(self, tmp, name):
        path = os.path.join(tmp, name)
        run.main(["--sizes", "500", "--runs", "2", "--seed", "3", "--json", path])
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_report_shape_and_determinism(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = self._run(tmp, "a.json"), self._run(tmp, "b.json")
        self.assertEqual(a["schema"], 1)
        self.assertEqual(a["data_digest"], b["data_digest"])
        self.assertIn("500", a["data_digest"])
        self.assertEqual({r["workload"] for r in a["results"]}, {"bulk_insert", "point_read"})
        for r in a["results"]:
            self.assertTrue(r["verified"])
            self.assertEqual(len(r["runs"]), 2)
            self.assertEqual(r["contender"], "sqlite")


if __name__ == "__main__":
    unittest.main()
