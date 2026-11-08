"""Synthetic unit falsification of the real Docker smoke orchestration.

These tests MOCK Docker. Only the GitHub runner's dedicated container job can
supply actual observations; a mock PASS is not proof of OS isolation.
"""
import contextlib
import io
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from foundry.agent_executor import _FIXTURE
from foundry.sandbox_policy import plan
from foundry.sandbox_smoke import smoke


DIGEST = "a" * 64
IMAGE = "python:3.11-slim@sha256:" + DIGEST
CHECKS = (
    "non_root_uid", "root_filesystem_read_only", "work_mount_read_only",
    "tmpfs_noexec", "network_only_loopback", "outbound_tcp_denied",
    "cgroup_memory_128m", "cgroup_pids_32", "cgroup_cpu_half",
    "no_new_privileges", "no_effective_caps",
)


def ok_docker_call(argv, timeout):
    if argv[:3] == ["docker", "image", "inspect"]:
        return SimpleNamespace(returncode=0, stdout=json.dumps(
            ["python@sha256:" + DIGEST]
        ), stderr="")
    if argv[:2] == ["docker", "run"]:
        return SimpleNamespace(returncode=0, stdout=json.dumps({
            "probe": "synthetic-fixed-review-only",
            "passed": True,
            "checked": {k: True for k in CHECKS},
            "untrusted_code_executed": False,
            "full_agent_sandbox_attested": False,
        }), stderr="")
    raise AssertionError("Unexpected host command")


class SyntheticSandboxOrchestrationTests(unittest.TestCase):
    def safe(self, result):
        for key in ("untrusted_model_code_allowed", "candidate_executed",
                    "production_allowed", "github_write_allowed",
                    "automatic_merge_allowed", "launch_authorized"):
            self.assertFalse(result[key])

    def test_confinement_probe_is_fixed_and_read_only(self):
        candidate = plan(IMAGE, _FIXTURE, probe="confinement")
        self.assertEqual(candidate["state"], "POLICY_PLAN_ONLY")
        self.assertEqual(candidate["command_argv"][-1], "/work/sandbox_runtime_probe.py")
        self.assertIn("--network=none", candidate["command_argv"])
        self.assertIn("--read-only", candidate["command_argv"])
        self.assertFalse(candidate["candidate_executed"])

    def test_unknown_probe_is_blocked(self):
        for probe in ("bash", "/bin/sh", None, [], True):
            with self.subTest(probe=probe):
                self.assertEqual(plan(IMAGE, _FIXTURE, probe=probe)["state"],
                                 "BLOCKED")

    def test_fake_image_metadata_does_not_prove_runtime(self):
        with patch("foundry.sandbox_smoke._run", side_effect=ok_docker_call):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "OBSERVED_FIXED_PROBE_PASS")
        self.assertTrue(result["runtime_confinement_observed"])
        self.safe(result)  # mocked evidence still cannot authorize LLM.

    def test_mismatched_local_digest_denies(self):
        def bad_inspect(argv, timeout):
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                ["python@sha256:" + "b" * 64]
            ))
        with patch("foundry.sandbox_smoke._run", side_effect=bad_inspect):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)

    def test_missing_local_image_fails_without_guest(self):
        with patch("foundry.sandbox_smoke._run",
                   return_value=SimpleNamespace(returncode=1, stdout="",
                                                stderr="not found")) as mocked:
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(mocked.call_count, 1)
        self.safe(result)

    def test_missing_guest_check_fails_closed(self):
        def truncated(argv, timeout):
            if argv[:3] == ["docker", "image", "inspect"]:
                return ok_docker_call(argv, timeout)
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "probe": "synthetic-fixed-review-only",
                "passed": True,
                "checked": {"non_root_uid": True},
                "untrusted_code_executed": False,
                "full_agent_sandbox_attested": False,
            }))
        with patch("foundry.sandbox_smoke._run", side_effect=truncated):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)

    def test_false_guest_network_check_fails_closed(self):
        def denied_network(argv, timeout):
            if argv[:3] == ["docker", "image", "inspect"]:
                return ok_docker_call(argv, timeout)
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "probe": "synthetic-fixed-review-only",
                "passed": True,
                "checked": {x: x != "outbound_tcp_denied" for x in CHECKS},
                "untrusted_code_executed": False,
                "full_agent_sandbox_attested": False,
            }))
        with patch("foundry.sandbox_smoke._run", side_effect=denied_network):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)

    def test_guest_failure_nonzero_rejected(self):
        def fails(argv, timeout):
            if argv[:3] == ["docker", "image", "inspect"]:
                return ok_docker_call(argv, timeout)
            return SimpleNamespace(returncode=17, stdout="{}", stderr="")
        with patch("foundry.sandbox_smoke._run", side_effect=fails):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")

    def test_guest_not_json_denied(self):
        def invalid(argv, timeout):
            if argv[:3] == ["docker", "image", "inspect"]:
                return ok_docker_call(argv, timeout)
            return SimpleNamespace(returncode=0, stdout="not json", stderr="")
        with patch("foundry.sandbox_smoke._run", side_effect=invalid):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")

    def test_docker_timeout_denied(self):
        with patch("foundry.sandbox_smoke._run",
                   side_effect=subprocess.TimeoutExpired("docker", 1)):
            result = smoke(IMAGE, _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)

    def test_unpinned_image_never_calls_docker(self):
        with patch("foundry.sandbox_smoke._run",
                   side_effect=AssertionError("Docker invoked")):
            result = smoke("python:latest", _FIXTURE)
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)

    def test_missing_fixture_never_calls_docker(self):
        with patch("foundry.sandbox_smoke._run",
                   side_effect=AssertionError("Docker invoked")):
            result = smoke(IMAGE, "/nonexistent/opdb-sandbox-probe-dir")
        self.assertEqual(result["state"], "BLOCKED")
        self.safe(result)


if __name__ == "__main__":
    unittest.main()
