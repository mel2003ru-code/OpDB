"""Launch Gate regression tests: green button stays disarmed until real attestation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from foundry.launch_gate import (
    REQUIRED_CHECKS, evaluate, format_confirmed_start_time, main,
)

SHA = "a" * 40


def fixture():
    return {
        "schema_version": 1,
        "candidate_sha": SHA,
        "checks": {
            name: {
                "status": "PASS",
                "target_sha": SHA,
                "sha256": "b" * 64,
                "run_url": "https://github.com/mel2003ru-code/OpDB/actions/runs/123",
                "checked_at_utc": "2026-11-08T11:45:00Z",
            }
            for name in REQUIRED_CHECKS
        },
    }


class LaunchGateTests(unittest.TestCase):
    def verdict(self, document, expected):
        decision = evaluate(document)
        self.assertEqual(decision["state"], expected, decision)
        self.assertFalse(decision["button_enabled"])
        self.assertEqual(decision["button_label"], "Запустить")
        self.assertFalse(decision["launch_authorized"])
        self.assertFalse(decision["launched"])
        self.assertIsNone(decision["launched_at_utc"])
        self.assertIsNone(decision["launch_request_at_utc"])
        return decision

    def test_no_engine_has_no_launch(self):
        self.verdict(None, "NOT_READY")

    def test_empty_document_is_blocked(self):
        self.verdict({}, "BLOCKED")

    def test_wrong_schema_is_blocked(self):
        x = fixture(); x["schema_version"] = 2
        self.verdict(x, "BLOCKED")

    def test_boolean_version_is_invalid(self):
        x = fixture(); x["schema_version"] = True
        self.verdict(x, "BLOCKED")

    def test_missing_or_bogus_candidate_commit(self):
        for candidate in ("", "abc", None, True, "g" * 40):
            with self.subTest(candidate=candidate):
                x = fixture(); x["candidate_sha"] = candidate
                self.verdict(x, "BLOCKED")

    def test_empty_checks_not_ready(self):
        x = fixture(); x["checks"] = {}
        d = self.verdict(x, "NOT_READY")
        self.assertEqual(len(d["failures"]), len(REQUIRED_CHECKS))

    def test_unknown_check_is_blocked(self):
        x = fixture(); x["checks"]["ignore_important_safety"] = x["checks"]["actual_core_adapter"]
        self.verdict(x, "BLOCKED")

    def test_missing_each_critical_evidence_blocks_activation(self):
        for check in REQUIRED_CHECKS:
            with self.subTest(check=check):
                x = fixture(); del x["checks"][check]
                self.verdict(x, "NOT_READY")

    def test_explicit_failure_halts_launch(self):
        x = fixture(); x["checks"]["trusted_change_capture"]["status"] = "FAIL"
        d = self.verdict(x, "BLOCKED")
        self.assertIn("trusted_change_capture", "\n".join(d["failures"]))

    def test_quality_unknown_denies(self):
        x = fixture(); x["checks"]["independent_quality"]["status"] = "NOT_VERIFIED"
        self.verdict(x, "NOT_READY")

    def test_self_reported_fully_green_still_requires_owner(self):
        d = self.verdict(fixture(), "OWNER_REVIEW_REQUIRED")
        self.assertEqual(d["verified_metadata_entries"], len(REQUIRED_CHECKS))
        self.assertIn("UNAUTHENTICATED", " ".join(d["failures"]))

    def test_metadata_pass_does_not_authorize_release(self):
        x = fixture()
        x["owner_approved"] = True
        x["production_allowed"] = True
        x["launch_button_enabled"] = True
        self.verdict(x, "OWNER_REVIEW_REQUIRED")

    def test_mismatched_commit_not_ready(self):
        x = fixture(); x["checks"]["staging_deployment_rehearsal"]["target_sha"] = "c" * 40
        self.verdict(x, "NOT_READY")

    def test_no_fake_checks_without_evidence_hash(self):
        x = fixture(); x["checks"]["rollback_and_restore_rehearsal"]["sha256"] = ""
        self.verdict(x, "NOT_READY")

    def test_random_external_url_rejected(self):
        x = fixture(); x["checks"]["agent_execution_isolation"]["run_url"] = "https://bad.example/run/1"
        self.verdict(x, "NOT_READY")

    def test_bogus_time_rejected(self):
        for timestamp in ("2026-02-30T13:00:00Z", "2026-11-08T11:45:00+03:00", None, ""):
            with self.subTest(timestamp=timestamp):
                x = fixture()
                x["checks"]["agent_budget_and_rate_limits"]["checked_at_utc"] = timestamp
                self.verdict(x, "NOT_READY")

    def test_missing_runtime_policy_denies(self):
        for check in ("agent_budget_and_rate_limits", "least_privilege_and_secrets",
                      "superiority_pause_watcher", "observability_and_emergency_stop"):
            with self.subTest(check=check):
                x = fixture(); del x["checks"][check]
                self.verdict(x, "NOT_READY")

    def test_same_evidence_yields_same_result(self):
        x = fixture()
        self.assertEqual(evaluate(x), evaluate(copy.deepcopy(x)))

    def test_timestamp_winter_paris_and_moscow(self):
        actual = format_confirmed_start_time("2026-11-08T11:00:00Z")
        self.assertEqual(actual["utc"], "2026-11-08T11:00:00Z")
        self.assertEqual(actual["paris"], "2026-11-08T12:00:00+01:00")
        self.assertEqual(actual["moscow"], "2026-11-08T14:00:00+03:00")

    def test_timestamp_summer_dst_paris(self):
        actual = format_confirmed_start_time("2026-07-08T11:00:00Z")
        self.assertEqual(actual["paris"], "2026-07-08T13:00:00+02:00")
        self.assertEqual(actual["moscow"], "2026-07-08T14:00:00+03:00")

    def test_timestamp_requires_canonical_utc(self):
        for timestamp in ("2026-11-08T12:00:00+01:00", "not-a-time", "", None):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    format_confirmed_start_time(timestamp)

    def test_cli_default_does_not_register_start(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "decision.json"
            self.assertEqual(main(["--output", str(p)]), 0)
            response = json.loads(p.read_text(encoding="utf-8"))
            self.assertEqual(response["state"], "NOT_READY")
            self.assertFalse(response["button_enabled"])
            self.assertIsNone(response["launched_at_utc"])

    def test_cli_syntactically_complete_does_not_register_start(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / "evidence.json"
            decision = Path(folder) / "decision.json"
            evidence.write_text(json.dumps(fixture()), encoding="utf-8")
            self.assertEqual(main(["--manifest", str(evidence), "--output", str(decision)]), 0)
            self.assertEqual(
                json.loads(decision.read_text(encoding="utf-8"))["state"],
                "OWNER_REVIEW_REQUIRED",
            )

    def test_cli_missing_json_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "decision.json"
            rc = main(["--manifest", str(Path(folder) / "absent.json"),
                       "--output", str(target)])
            self.assertEqual(rc, 2)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
