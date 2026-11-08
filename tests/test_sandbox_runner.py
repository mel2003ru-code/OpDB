"""Test the real Docker runner's fail-closed parsing and command controls.

These mocks test the controller; only GitHub Docker CI can observe actual
kernel restrictions. They MUST NOT be advertised as sandbox certification.
"""
import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from foundry.sandbox_runner import (
    ALLOWED_PROBES, DOCKER, PINNED_IMAGE, _docker_env, _run, main, run_probe,
)


def completed(code=0, stdout="", stderr=""):
    return subprocess.CompletedProcess([DOCKER], code, stdout, stderr)


def valid_observation(probe):
    expected = {
        "confinement": "synthetic-fixed-review-only",
        "adversarial": "fixed-reviewed-denied-operations",
    }[probe]
    return completed(stdout=json.dumps({
        "probe": expected,
        "passed": True,
        "checked": {f"restriction_{i}": True for i in range(12)},
        "untrusted_code_executed": False,
        "untrusted_model_code_executed": False,
        "full_agent_sandbox_attested": False,
        "hostile_code_sandbox_attested": False,
    }) + "\n")


def run_stub(probe, *, failure=None, observed=None):
    calls = []
    def runner(args, *, timeout):
        calls.append((tuple(args), timeout))
        if "inspect" in args:
            if failure == "missing_image":
                return completed(1)
            return completed(stdout="sha256:" + "a" * 64 + "\n")
        if "run" in args:
            if failure == "timeout":
                raise subprocess.TimeoutExpired(args, timeout)
            if failure == "exit":
                return completed(1)
            if failure == "bad_stdout":
                return completed(stdout="not json")
            return observed or valid_observation(probe)
        if "rm" in args:
            return completed()
        raise AssertionError("Unknown docker call: " + str(args))
    return runner, calls


class DockerRuntimeSmokePolicyTests(unittest.TestCase):
    def assert_blocked(self, result):
        self.assertNotEqual(result["state"], "REVIEWED_PROBE_PASS")
        for key in (
            "candidate_executed", "untrusted_model_code_executed",
            "agent_sandbox_attested", "model_invoked", "github_write_allowed",
            "automatic_merge_allowed", "production_allowed", "launch_authorized",
        ):
            self.assertFalse(result[key], key)

    def test_only_two_fixed_probes_allowed(self):
        self.assertEqual(set(ALLOWED_PROBES), {"confinement", "adversarial"})
        for probe in (None, True, "", "quality", "python", "evil", []):
            with self.subTest(probe=probe), patch(
                "foundry.sandbox_runner._docker_available",
                side_effect=AssertionError("must deny before Docker")
            ):
                self.assert_blocked(run_probe(probe))

    def test_missing_docker_fails_closed(self):
        with patch("foundry.sandbox_runner._docker_available", return_value=False):
            result = run_probe("confinement")
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.assert_blocked(result)

    def test_image_digest_is_literal_not_from_user_task(self):
        self.assertTrue(PINNED_IMAGE.startswith("python:3.11-slim@sha256:"))
        self.assertEqual(len(PINNED_IMAGE.rsplit(":", 1)[1]), 64)

    def test_host_docker_environment_has_no_github_or_model_secret(self):
        environment = _docker_env()
        for item in ("GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY",
                     "YANDEX_API_KEY", "AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(item, environment)
        self.assertEqual(environment["DOCKER_HOST"], "unix:///var/run/docker.sock")

    def test_real_subprocess_wrapper_has_no_shell_or_global_env(self):
        with patch("foundry.sandbox_runner.subprocess.run") as fake:
            _run([DOCKER, "version"], timeout=3)
        kwargs = fake.call_args.kwargs
        self.assertEqual(kwargs["executable"], DOCKER)
        self.assertFalse(kwargs.get("shell", False))
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["timeout"], 3)
        self.assertEqual(kwargs["env"], _docker_env())

    def test_confinement_success_remains_review_only(self):
        stub, calls = run_stub("confinement")
        with (patch("foundry.sandbox_runner._docker_available", return_value=True),
              patch("foundry.sandbox_runner._run", side_effect=stub)):
            result = run_probe("confinement")
        self.assertEqual(result["state"], "REVIEWED_PROBE_PASS", result)
        self.assertIsNotNone(result["observed"])
        self.assertFalse(result["candidate_executed"])
        self.assertFalse(result["agent_sandbox_attested"])
        self.assertEqual(len(calls), 3)
        cmd = calls[1][0]
        self.assertEqual(cmd[0], DOCKER)
        self.assertIn("--network=none", cmd)
        self.assertIn("--cap-drop=ALL", cmd)
        self.assertIn("--security-opt=no-new-privileges", cmd)
        self.assertIn("--pids-limit=32", cmd)
        self.assertIn("--memory=128m", cmd)
        self.assertIn("--cpus=0.5", cmd)
        self.assertIn("--read-only", cmd)
        self.assertIn("--pull=never", cmd)
        self.assertTrue(any(x.startswith("--cidfile=") for x in cmd))
        self.assertIn(PINNED_IMAGE, cmd)
        self.assertEqual(cmd[-1], "/work/sandbox_runtime_probe.py")
        self.assertEqual(calls[-1][0][1:3], ("rm", "-f"))

    def test_adversarial_probe_must_pass_observation(self):
        stub, calls = run_stub("adversarial")
        with (patch("foundry.sandbox_runner._docker_available", return_value=True),
              patch("foundry.sandbox_runner._run", side_effect=stub)):
            result = run_probe("adversarial")
        self.assertEqual(result["state"], "REVIEWED_PROBE_PASS")
        self.assertEqual(calls[1][0][-1], "/work/sandbox_adversarial_probe.py")
        self.assertEqual(len(calls), 3)
        self.assertFalse(result["launch_authorized"])

    def test_never_implicitly_pulls_missing_image(self):
        stub, calls = run_stub("confinement", failure="missing_image")
        with (patch("foundry.sandbox_runner._docker_available", return_value=True),
              patch("foundry.sandbox_runner._run", side_effect=stub)):
            result = run_probe("confinement")
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("pull", str(calls))
        self.assert_blocked(result)

    def test_observed_failure_blocks_even_if_docker_exit_zero(self):
        fake = valid_observation("confinement")
        details = json.loads(fake.stdout)
        details["checked"]["restriction_2"] = False
        stub, _ = run_stub(
            "confinement", observed=completed(stdout=json.dumps(details) + "\n")
        )
        with (patch("foundry.sandbox_runner._docker_available", return_value=True),
              patch("foundry.sandbox_runner._run", side_effect=stub)):
            result = run_probe("confinement")
        self.assertEqual(result["state"], "BLOCKED")
        self.assert_blocked(result)

    def test_unparseable_or_spoofed_probe_fails_closed(self):
        for obs in (
            completed(stdout="{}"),
            completed(stdout='{"probe":"wrong","passed":true,"checked":{}}\n'),
            completed(stdout='garbage\n'),
            completed(stdout='{}\n{}\n'),
            completed(stdout='{"probe":"synthetic-fixed-review-only","passed":false,"checked":{}}\n'),
        ):
            stub, _ = run_stub("confinement", observed=obs)
            with (patch("foundry.sandbox_runner._docker_available", return_value=True),
                  patch("foundry.sandbox_runner._run", side_effect=stub)):
                self.assert_blocked(run_probe("confinement"))

    def test_failure_and_timeout_attempt_container_cleanup(self):
        for failure in ("exit", "timeout", "bad_stdout"):
            stub, calls = run_stub("confinement", failure=failure)
            with (patch("foundry.sandbox_runner._docker_available", return_value=True),
                  patch("foundry.sandbox_runner._run", side_effect=stub)):
                result = run_probe("confinement")
            self.assertEqual(result["state"], "BLOCKED")
            self.assertTrue(any(c[0][1:3] == ("rm", "-f") for c in calls),
                            "Container cleanup must run on failure")
            self.assert_blocked(result)

    def test_main_blocks_unavailable_runtime_without_running_docker(self):
        with patch("foundry.sandbox_runner._docker_available", return_value=False):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                rc = main(["--probe", "confinement"])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["state"], "NOT_CONFIGURED")

    def test_main_emits_report_when_probe_success_is_mocked(self):
        stub, _ = run_stub("confinement")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "report.json"
            with (patch("foundry.sandbox_runner._docker_available", return_value=True),
                  patch("foundry.sandbox_runner._run", side_effect=stub)):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    rc = main(["--probe", "confinement", "--output", str(target)])
            self.assertEqual(rc, 0)
            d = json.loads(out.getvalue())
            self.assertEqual(d["state"], "REVIEWED_PROBE_PASS")
            self.assertEqual(d, json.loads(target.read_text()))
            self.assertFalse(d["agent_sandbox_attested"])


if __name__ == "__main__":
    unittest.main()
