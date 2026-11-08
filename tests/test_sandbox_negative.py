"""Unit falsification for real Docker negative-control controller.

Only the dedicated CI workflow can supply actual container evidence.
All subprocess and baseline results below are deliberately mocked.
"""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foundry.agent_executor import _FIXTURE
from foundry.sandbox_negative import (
    CONTROLS, EXPECTED, verify_negative_controls,
)


DIGEST = "a" * 64
IMAGE = "python:3.11-slim@sha256:" + DIGEST

def baseline(image, fixture, *, budget_seconds=12):
    return {"state": "OBSERVED_FIXED_PROBE_PASS", "image_digest": DIGEST}

def negatives(argv, timeout):
    removed = [(name, guard, check) for name, guard, check in CONTROLS
               if guard not in argv]
    if len(removed) != 1:
        raise AssertionError("Exactly one guard must be removed")
    checks = {name: True for name in EXPECTED}
    checks[removed[0][2]] = False
    return SimpleNamespace(returncode=1, stdout=json.dumps({
        "probe": "synthetic-fixed-review-only",
        "passed": False,
        "untrusted_code_executed": False,
        "full_agent_sandbox_attested": False,
        "checked": checks,
    }), stderr="")

class NegativeSandboxPolicyTests(unittest.TestCase):
    def readonly(self, report):
        for key in ("untrusted_model_code_allowed", "candidate_executed",
                    "github_write_allowed", "production_allowed",
                    "automatic_merge_allowed", "launch_authorized"):
            self.assertIs(report[key], False)

    def test_all_three_separate_controls_observed(self):
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=negatives) as runner):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "EXPECTED_FAILURES_OBSERVED", outcome)
        self.assertIs(outcome["expected_failures_observed"], True)
        self.assertEqual(set(outcome["negative_controls"]),
                         {"network", "non_root", "memory"})
        self.assertEqual(runner.call_count, 3)
        self.readonly(outcome)

    def test_bad_baseline_never_runs_negatives(self):
        with (patch("foundry.sandbox_negative.smoke",
                    return_value={"state": "BLOCKED"}),
              patch("foundry.sandbox_negative._run",
                    side_effect=AssertionError("must never run"))):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")
        self.readonly(outcome)

    def test_missing_pinned_image_denied(self):
        with patch("foundry.sandbox_negative._run",
                   side_effect=AssertionError("must never run")):
            outcome = verify_negative_controls("python:latest", _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_zero_exit_fails_negative_proof(self):
        def always_green(argv, timeout):
            result = negatives(argv, timeout)
            result.returncode = 0
            return result
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=always_green)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")
        self.assertFalse(outcome["expected_failures_observed"])

    def test_wrong_failed_check_is_not_accepted(self):
        def wrong_check(argv, timeout):
            p = negatives(argv, timeout)
            report = json.loads(p.stdout)
            report["checked"] = {name: True for name in EXPECTED}
            report["checked"]["no_effective_caps"] = False
            p.stdout = json.dumps(report)
            return p
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=wrong_check)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_missing_guest_checks_fail_closed(self):
        def partial(argv, timeout):
            p = negatives(argv, timeout)
            report = json.loads(p.stdout)
            report["checked"].pop("cgroup_cpu_half")
            p.stdout = json.dumps(report)
            return p
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=partial)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_guest_json_list_must_not_crash_into_success(self):
        def corrupt(argv, timeout):
            return SimpleNamespace(returncode=1, stdout='["not", "a", "report"]',
                                   stderr="")
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=corrupt)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_guest_json_invalid_denied(self):
        def corrupt(argv, timeout):
            return SimpleNamespace(returncode=1, stdout="not json", stderr="")
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=corrupt)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_guest_timeout_denied(self):
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run",
                    side_effect=subprocess.TimeoutExpired("docker", 1))):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.assertEqual(outcome["state"], "BLOCKED")

    def test_even_pass_never_authorizes_first_launch(self):
        with (patch("foundry.sandbox_negative.smoke", side_effect=baseline),
              patch("foundry.sandbox_negative._run", side_effect=negatives)):
            outcome = verify_negative_controls(IMAGE, _FIXTURE)
        self.readonly(outcome)
        self.assertEqual(outcome["image_digest"], DIGEST)

if __name__ == "__main__":
    unittest.main()
