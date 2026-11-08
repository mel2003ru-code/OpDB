"""Unit negative controls for reviewed adversarial Docker probe.

Mocks are NOT evidence of host isolation; real GitHub Actions runs Docker.
"""
import json
from types import SimpleNamespace
import subprocess
import unittest
from unittest.mock import patch

from foundry.agent_executor import _FIXTURE
from foundry.sandbox_adversarial import CHECKS, assess
from foundry.sandbox_policy import plan

IMAGE = "python:3.11-slim@sha256:" + "a" * 64


def _baseline(image, fixture, *, budget_seconds=12):
    return {"state": "OBSERVED_FIXED_PROBE_PASS", "image_digest": "a" * 64}


def _guest(argv, timeout):
    if argv[:2] != ["docker", "run"]:
        raise AssertionError("not an approved container operation")
    checks = {key: True for key in CHECKS}
    if any(s.startswith("--env=GITHUB_TOKEN=FAKE_CANARY_") for s in argv):
        checks["secret_names_absent"] = False
    if "--security-opt=seccomp=unconfined" in argv:
        checks["seccomp_filter_active"] = False
    passed = all(checks.values())
    return SimpleNamespace(
        returncode=0 if passed else 1,
        stdout=json.dumps({
            "probe": "fixed-reviewed-denied-operations",
            "checked": checks, "passed": passed,
            "untrusted_model_code_executed": False,
            "hostile_code_sandbox_attested": False,
        }),
        stderr="",
    )


class AdversarialSandboxTests(unittest.TestCase):
    def denied(self, outcome):
        for key in ("model_patch_execution_authorized",
                    "arbitrary_code_isolation_attested",
                    "github_write_allowed", "production_allowed",
                    "launch_authorized"):
            self.assertIs(outcome[key], False)

    def test_only_fixed_reviewed_probe_is_mounted(self):
        config = plan(IMAGE, _FIXTURE, probe="adversarial")
        self.assertEqual(config["state"], "POLICY_PLAN_ONLY")
        argv = config["command_argv"]
        self.assertEqual(argv[-1], "/work/sandbox_adversarial_probe.py")
        self.assertIn("--network=none", argv)
        self.assertIn("--read-only", argv)
        self.assertIn("--cap-drop=ALL", argv)
        self.assertIn("--user=65534:65534", argv)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--env", argv)
        self.assertNotIn("/var/run/docker.sock", " ".join(argv))
        self.assertEqual(argv.count("--network=none"), 1)

    def test_three_fixed_probe_runs_and_refused_authorization(self):
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run", side_effect=_guest) as run):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "FIXED_DENIALS_OBSERVED", result)
        self.assertEqual(len(result["observations"]), 7)
        self.assertTrue(all(result["observations"].values()))
        self.assertTrue(result["negative_controls_verified"])
        self.assertTrue(result["synthetic_canary_detected"])
        self.assertTrue(result["synthetic_relaxed_seccomp_detected"])
        self.assertEqual(run.call_count, 3)
        self.denied(result)

    def test_missing_verified_baseline_never_starts_adversarial_guest(self):
        with (patch("foundry.sandbox_adversarial.smoke",
                    return_value={"state": "BLOCKED"}),
              patch("foundry.sandbox_adversarial._run",
                    side_effect=AssertionError("guest must not run"))):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_no_unpinned_image_admitted(self):
        with patch("foundry.sandbox_adversarial._run",
                   side_effect=AssertionError("unsafe run")):
            result = assess("python:latest", _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_fake_canary_control_must_show_unsafe(self):
        def guest_ignores_canary(argv, timeout):
            clean = [x for x in argv if not x.startswith("--env=")]
            return _guest(clean, timeout)
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run", side_effect=guest_ignores_canary)):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_relaxed_seccomp_must_show_unsafe(self):
        def guest_ignores_seccomp(argv, timeout):
            clean = [x for x in argv if x != "--security-opt=seccomp=unconfined"]
            return _guest(clean, timeout)
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run", side_effect=guest_ignores_seccomp)):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_missing_required_guest_observation_is_refused(self):
        def truncated(argv, timeout):
            x = _guest(argv, timeout)
            report = json.loads(x.stdout)
            report["checked"].pop("docker_socket_absent")
            x.stdout = json.dumps(report)
            return x
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run", side_effect=truncated)):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")

    def test_no_guest_report_refused(self):
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run",
                    return_value=SimpleNamespace(returncode=125,stdout="",stderr="docker error"))):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_timeout_refused(self):
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run",
                    side_effect=subprocess.TimeoutExpired(["docker", "run"], 1))):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)

    def test_report_must_disclaim_untrusted_code(self):
        def claims_untrusted_run(argv, timeout):
            x = _guest(argv,timeout)
            report = json.loads(x.stdout)
            report["untrusted_model_code_executed"] = True
            x.stdout = json.dumps(report)
            return x
        with (patch("foundry.sandbox_adversarial.smoke", side_effect=_baseline),
              patch("foundry.sandbox_adversarial._run",
                    side_effect=claims_untrusted_run)):
            result = assess(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.denied(result)


if __name__ == "__main__":
    unittest.main()
