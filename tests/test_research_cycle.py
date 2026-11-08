import unittest
from research.cycle import TRACKS, PROBES, run_cycle


class ResearchCycleTests(unittest.TestCase):
    def test_all_thirteen_workstreams_enumerated(self):
        self.assertEqual(len(TRACKS), 13)
        self.assertEqual(len({t for t, _ in TRACKS}), 13)

    def test_probes_are_explicitly_scoped(self):
        self.assertEqual(set(PROBES), {"R03", "R07", "R10"})

    def test_smoke_probes_pass_under_fixed_seed(self):
        report = run_cycle(20261108)
        self.assertEqual(len(report["results"]), 13)
        by_track = {r["track"]: r for r in report["results"]}
        for name in PROBES:
            self.assertEqual(by_track[name]["status"], "SQLITE_SMOKE_PASS", by_track[name])
            self.assertGreater(by_track[name]["assertions"], 0)
        for name in ("TASK-001", "TASK-002", "TASK-003", "R01"):
            self.assertEqual(by_track[name]["status"], "NOT_CONFIGURED", by_track[name])

    def test_seeds_are_reproducible(self):
        a, b = run_cycle(77), run_cycle(77)
        for ta, tb in zip(a["results"], b["results"]):
            self.assertEqual(ta["track"], tb["track"])
            self.assertEqual(ta.get("seed"), tb.get("seed"))
            self.assertEqual(ta["status"], tb["status"])


if __name__ == "__main__":
    unittest.main()
