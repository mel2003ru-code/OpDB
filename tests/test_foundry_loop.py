"""Independent small regression matrix for safe Foundry research-cycle routing."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from foundry.loop import TRACK_ISSUES, plan, main


SHA = "a" * 40


def report():
    results = []
    for track, issue in TRACK_ISSUES.items():
        if track.startswith("TASK"):
            status = "NOT_CONFIGURED"
        elif track in ("R04", "R05", "R09"):
            status = "MODEL_SMOKE_PASS"
        else:
            status = "SQLITE_SMOKE_PASS"
        results.append({"track": track, "issue": issue, "status": status})
    return {
        "repository_sha": SHA,
        "seed": 203,
        "start_utc": "2026-11-08T12:00:00+00:00",
        "python": "3.11.9",
        "sqlite": "3.46.1",
        "platform": "Linux-synthetic",
        "results": results,
        "negative_controls": [{
            "status": "EXPECTED_COUNTEREXAMPLE",
            "external_untracked_stale": True,
            "forged_journal_mismatch": True,
            "source_integrity": "ok",
        }],
    }


class SafeLoopTests(unittest.TestCase):
    def verdict(self, x, expected, sha=SHA):
        v = plan(x, sha)
        self.assertEqual(v["state"], expected, v)
        self.assertFalse(v["automatic_merge_allowed"])
        self.assertFalse(v["staging_deploy_allowed"])
        self.assertFalse(v["production_deploy_allowed"])
        self.assertFalse(v["automated_code_change_allowed"])
        self.assertFalse(v["pause_for_superiority_confirmed"])
        self.assertTrue(v["source_only_required"])
        self.assertEqual(v["safety_blocker_issue"], 21)
        return v

    def test_current_matrix_requests_real_adapter(self):
        v = self.verdict(report(), "REQUEST_EXECUTABLE_ADAPTER")
        self.assertEqual(v["next_issue"], 3)

    def test_mismatched_source_sha_holds(self):
        self.verdict(report(), "HOLD_EVIDENCE", "b" * 40)

    def test_invalid_or_absent_expected_sha_holds(self):
        for sha in (None, "", "bad"):
            with self.subTest(sha=sha):
                self.verdict(report(), "HOLD_EVIDENCE", sha)

    def test_unknown_or_duplicate_track_holds(self):
        for change in ("unknown", "duplicate"):
            with self.subTest(change=change):
                r = report()
                r["results"][0]["track"] = "R99" if change == "unknown" else "R02"
                self.verdict(r, "HOLD_EVIDENCE")

    def test_missing_track_holds(self):
        r = report(); r["results"].pop()
        self.verdict(r, "HOLD_EVIDENCE")

    def test_wrong_issue_holds(self):
        r = report(); r["results"][0]["issue"] = 21
        self.verdict(r, "HOLD_EVIDENCE")

    def test_wrong_model_label_holds(self):
        r = report(); r["results"][3]["status"] = "SQLITE_SMOKE_PASS"
        self.verdict(r, "HOLD_EVIDENCE")

    def test_unsupported_production_pass_label_holds(self):
        r = report(); r["results"][10]["status"] = "PASS"
        self.verdict(r, "HOLD_EVIDENCE")

    def test_safety_failing_critical_probe_escalates(self):
        r = report()
        r["negative_controls"][0]["forged_journal_mismatch"] = False
        v = self.verdict(r, "ESCALATE_SAFETY")
        self.assertEqual(v["next_issue"], 21)

    def test_missing_negative_control_holds(self):
        r = report(); r["negative_controls"] = []
        self.verdict(r, "HOLD_EVIDENCE")

    def test_untrusted_negative_control_true_string_escalates(self):
        r = report()
        r["negative_controls"][0]["external_untracked_stale"] = "True"
        self.verdict(r, "ESCALATE_SAFETY")

    def test_failed_research_probe_prioritized(self):
        r = report()
        for row in r["results"]:
            if row["track"] in ("R07", "R04"):
                row["status"] = "FAIL"
                row["error"] = "oracle mismatch in synthetic data"
        v = self.verdict(r, "INVESTIGATE_FAILED_TRACK")
        self.assertEqual(v["next_issue"], 13)

    def test_failed_critical_task_prioritized(self):
        r = report()
        r["results"][10]["status"] = "FAIL"
        r["results"][10]["error"] = "assertion failure"
        v = self.verdict(r, "INVESTIGATE_FAILED_TRACK")
        self.assertEqual(v["next_issue"], 2)

    def test_failure_without_description_holds(self):
        r = report(); r["results"][0]["status"] = "FAIL"
        self.verdict(r, "HOLD_EVIDENCE")

    def test_all_runnable_tasks_require_quality_even_after_smoke(self):
        r = report()
        for row in r["results"]:
            if row["track"].startswith("TASK"):
                row["status"] = "IMPLEMENTATION_SMOKE_PASS"
        v = self.verdict(r, "AWAIT_INDEPENDENT_QUALITY")
        self.assertEqual(v["next_issue"], 4)

    def test_bad_timestamp_is_rejected(self):
        for timestamp in ("2026-11-08T12:00:00", "yesterday", "2026-11-08T12:00:00+03:00"):
            with self.subTest(timestamp=timestamp):
                r = report(); r["start_utc"] = timestamp
                self.verdict(r, "HOLD_EVIDENCE")

    def test_malformed_seed_is_rejected(self):
        for seed in (True, "203", -1, None):
            with self.subTest(seed=seed):
                r = report(); r["seed"] = seed
                self.verdict(r, "HOLD_EVIDENCE")

    def test_non_finite_nested_value_prevents_digest(self):
        r = report()
        r["metadata"] = float("nan")
        self.verdict(r, "HOLD_EVIDENCE")

    def test_deterministic_when_report_is_identical(self):
        r = report()
        self.assertEqual(plan(r, SHA), plan(copy.deepcopy(r), SHA))

    def test_cli_is_read_only_and_json_machine_parsable(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "research.json"
            out = Path(tmp) / "decision.json"
            p.write_text(json.dumps(report()), encoding="utf-8")
            self.assertEqual(main(["--research", str(p), "--expected-sha", SHA,
                                   "--output", str(out)]), 0)
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(data["state"], "REQUEST_EXECUTABLE_ADAPTER")
            self.assertFalse(data["production_deploy_allowed"])

    def test_missing_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            result = Path(tmp) / "result.json"
            self.assertEqual(main(["--research", str(missing), "--expected-sha", SHA,
                                   "--output", str(result)]), 2)
            self.assertEqual(json.loads(result.read_text(encoding="utf-8"))["state"],
                             "HOLD_EVIDENCE")


if __name__ == "__main__":
    unittest.main()
