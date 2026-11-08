import unittest

from research.cycle import TRACKS, PROBES, run_cycle
from research.probes_extended import MODEL_TRACKS


class ResearchCycleTests(unittest.TestCase):
    def test_all_thirteen_workstreams_enumerated(self):
        self.assertEqual(len(TRACKS), 13)
        self.assertEqual(len({t for t, _ in TRACKS}), 13)

    def test_all_ten_research_tracks_have_explicit_probes(self):
        self.assertEqual(set(PROBES), {f"R{i:02d}" for i in range(1, 11)})

    def test_model_checks_are_not_mislabeled_as_sqlite(self):
        self.assertEqual(MODEL_TRACKS, {"R04", "R05", "R09"})

    def test_smoke_probes_pass_under_fixed_seed(self):
        report = run_cycle(20261108)
        self.assertEqual(len(report["results"]), 13)
        by_track = {r["track"]: r for r in report["results"]}
        for name in PROBES:
            expected = "MODEL_SMOKE_PASS" if name in MODEL_TRACKS else "SQLITE_SMOKE_PASS"
            self.assertEqual(by_track[name]["status"], expected, by_track[name])
            self.assertGreater(by_track[name]["assertions"], 0)
            self.assertTrue(by_track[name].get("scope"))
        for name in ("TASK-001", "TASK-002", "TASK-003"):
            self.assertEqual(by_track[name]["status"], "NOT_CONFIGURED", by_track[name])

    def test_seeds_are_reproducible(self):
        a, b = run_cycle(77), run_cycle(77)
        for ta, tb in zip(a["results"], b["results"]):
            self.assertEqual(ta["track"], tb["track"])
            self.assertEqual(ta.get("seed"), tb.get("seed"))
            self.assertEqual(ta["status"], tb["status"])

    def test_cost_and_tails_report_measurements_without_claiming_sla(self):
        by_track = {r["track"]: r for r in run_cycle(203)["results"]}
        self.assertLessEqual(by_track["R02"]["without_index_file_bytes"],
                             by_track["R02"]["with_index_file_bytes"])
        tail = by_track["R08"]
        self.assertLessEqual(tail["p50_us"], tail["p95_us"])
        self.assertLessEqual(tail["p95_us"], tail["p99_us"])
        self.assertLessEqual(tail["p99_us"], tail["max_us"])

    def test_p0_negative_controls_are_expected_not_safety_pass(self):
        report = run_cycle(20261108)
        self.assertEqual(len(report["negative_controls"]), 1)
        control = report["negative_controls"][0]
        self.assertEqual(control["status"], "EXPECTED_COUNTEREXAMPLE")
        self.assertTrue(control["external_untracked_stale"])
        self.assertTrue(control["forged_journal_mismatch"])

    def test_failed_tracks_never_count_as_pass(self):
        by_track = {r["track"]: r for r in run_cycle(5)["results"]}
        self.assertEqual(sum(r["status"].endswith("_PASS") for r in by_track.values()), 10)
        self.assertEqual(sum(r["status"] == "NOT_CONFIGURED" for r in by_track.values()), 3)


if __name__ == "__main__":
    unittest.main()
