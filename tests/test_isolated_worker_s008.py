"""S-008 falsification: fixed offline worker must cross a Docker boundary.

These are host-side tests with a stubbed Docker CLI, not OS attestation.
Real Docker must be checked separately in Actions.
"""
import hashlib
import json
import re
import subprocess
import unittest
from unittest.mock import patch

from foundry.sandbox_policy import plan, _REVIEWED_FIXTURE
from foundry.sandbox_runner import DOCKER, PINNED_IMAGE
from foundry.worker_contract import _request_for, mock_reply, _CONTROLLER_CHECKOUT
from foundry.isolated_worker import run_isolated_handoff, _OBSERVED

SHA = "a" * 40


def completed(code=0, stdout=""):
    return subprocess.CompletedProcess([DOCKER], code, stdout, "")


def stub_docker(*, exit_code=0, bad_json=False, leaked=False, simulate_timeout=False,
                bad_check=False, fake_launch=False, duplicate_json=False,
                replayed_nonce=False, forged_digest=False, omit_nonce=False):
    reply, error = mock_reply(_request_for(SHA), SHA, _CONTROLLER_CHECKOUT)
    assert error is None, error
    report = {
        "probe": "fixed-data-only-handoff-s008",
        "passed": True,
        "checked": {key: True for key in _OBSERVED},
        "reply": reply,
        "model_invoked": False,
        "arbitrary_model_code_executed": False,
        "github_write_allowed": False,
        "trusted_controller_attested": False,
        "launch_authorized": False,
    }
    if bad_check:
        report["checked"]["shm_8m"] = False
    if fake_launch:
        report["launch_authorized"] = True
    calls = []
    def invoke(argv, *, timeout):
        calls.append(tuple(argv))
        if argv[1:3] == [ "image", "inspect" ]:
            return completed(stdout="sha256:" + "b" * 64 + "\n")
        if argv[1] == "run":
            envvals = {item.split("=", 2)[1].split("=", 1)[0]:
                       item.split("=", 2)[2]
                       for item in argv if item.startswith("--env=")}
            report["session_nonce"] = (
                "0" * 32 if replayed_nonce else envvals.get("OPDB_SESSION_NONCE"))
            report["request_sha256"] = (
                "f" * 64 if forged_digest else envvals.get("OPDB_REQUEST_SHA256"))
            if omit_nonce:
                report.pop("session_nonce")
            if simulate_timeout:
                raise subprocess.TimeoutExpired(argv, 3)
            return completed(exit_code, "{garbage" if bad_json else
                '{"probe":"fake","probe":"fixed-data-only-handoff-s008"}' if duplicate_json else
                json.dumps(report)+"\n")
        if argv[1:3] == ["rm", "-f"]:
            return completed()
        if argv[1:3] == ["ps", "-a"]:
            return completed(stdout="opdb-unremoved\n" if leaked else "")
        raise AssertionError(str(argv))
    return invoke, calls


class IsolatedWorkerS008Tests(unittest.TestCase):
    def blocked(self, report):
        self.assertNotEqual(report["state"], "ISOLATED_REVIEW_ONLY")
        self.assertFalse(report["trusted_controller_attested"])
        self.assertFalse(report["arbitrary_model_code_executed"])
        self.assertFalse(report["github_write_allowed"])
        self.assertFalse(report["launch_authorized"])

    def test_unknown_or_forged_request_never_reaches_docker(self):
        for request in ({}, None, dict(_request_for(SHA), shell_allowed=True),
                        dict(_request_for(SHA), max_model_requests=1),
                        dict(_request_for(SHA), execution_allowed=True)):
            with self.subTest(request=request), patch(
                "foundry.isolated_worker._docker_available",
                side_effect=AssertionError("Docker must not be touched")
            ):
                self.blocked(run_isolated_handoff(request, SHA, _CONTROLLER_CHECKOUT))

    def test_no_docker_fails_closed(self):
        with patch("foundry.isolated_worker._docker_available", return_value=False):
            result=run_isolated_handoff(_request_for(SHA), SHA, _CONTROLLER_CHECKOUT)
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.blocked(result)

    def test_protected_docker_plan_caps_network_cpu_memory_disk_and_pids(self):
        cfg=plan(PINNED_IMAGE, _REVIEWED_FIXTURE, 12, probe="handoff")
        self.assertEqual(cfg["state"], "POLICY_PLAN_ONLY", cfg)
        cmd=cfg["command_argv"]
        for flag in ("--network=none", "--read-only", "--log-driver=none", "--cap-drop=ALL",
                     "--security-opt=no-new-privileges", "--pids-limit=32",
                     "--memory=128m", "--memory-swap=128m", "--cpus=0.5",
                     "--shm-size=8m", "--pull=never", "--user=65534:65534"):
            self.assertIn(flag, cmd)
        self.assertTrue(any(v.startswith("--tmpfs=/tmp:") and "size=8m" in v for v in cmd))
        self.assertFalse(any("docker.sock" in v or "--privileged" in v for v in cmd))
        self.assertEqual(cmd[-1], "/work/handoff_worker.py")

    def test_real_cli_stub_accepts_only_review_quarantine_not_authorization(self):
        fn,calls=stub_docker()
        with (patch("foundry.isolated_worker._docker_available", return_value=True),
              patch("foundry.isolated_worker._run", side_effect=fn)):
            r=run_isolated_handoff(_request_for(SHA), SHA, _CONTROLLER_CHECKOUT)
        self.assertEqual(r["state"], "ISOLATED_REVIEW_ONLY",r)
        self.assertEqual(r["review"]["state"], "REVIEW_ONLY_PATCH")
        self.assertTrue(r["review"]["human_review_required"])
        self.assertFalse(r["trusted_controller_attested"])
        self.assertFalse(r["arbitrary_model_code_executed"])
        self.assertFalse(r["launch_authorized"])
        run=[x for x in calls if len(x)>1 and x[1]=="run"][0]
        self.assertIn("--env=OPDB_SOURCE_SHA="+SHA,run)
        self.assertTrue(any(x.startswith("--name=") for x in run))
        self.assertTrue(any(x.startswith("--cidfile=") for x in run))
        self.assertTrue(any(x[1:3]==("rm","-f") for x in calls))
        self.assertTrue(any(x[1:3]==("ps","-a") for x in calls))

    def test_failed_guest_or_malformed_stdout_does_not_pass(self):
        for kwargs in ({"exit_code":1},{"bad_json":True},{"simulate_timeout":True},
                       {"bad_check":True},{"fake_launch":True},{"duplicate_json":True}):
            fn,calls=stub_docker(**kwargs)
            with (self.subTest(kwargs=kwargs),
                  patch("foundry.isolated_worker._docker_available", return_value=True),
                  patch("foundry.isolated_worker._run", side_effect=fn)):
                self.blocked(run_isolated_handoff(_request_for(SHA),SHA,_CONTROLLER_CHECKOUT))
            self.assertTrue(any(x[1:3]==("rm","-f") for x in calls))

    def test_undischarged_container_never_counts_as_success(self):
        fn,_=stub_docker(leaked=True)
        with (patch("foundry.isolated_worker._docker_available", return_value=True),
              patch("foundry.isolated_worker._run", side_effect=fn)):
            self.blocked(run_isolated_handoff(_request_for(SHA),SHA,_CONTROLLER_CHECKOUT))

    def test_invalid_sha_and_checkout_must_not_start_guest(self):
        for sha,root in (("invalid",_CONTROLLER_CHECKOUT),(SHA,"/tmp")):
            with patch("foundry.isolated_worker._docker_available",
                       side_effect=AssertionError("must reject before Docker")):
                self.blocked(run_isolated_handoff(_request_for(SHA),sha,root))

    def test_fresh_session_nonce_and_request_digest_bound_to_guest(self):
        fn,calls = stub_docker()
        with (patch("foundry.isolated_worker._docker_available", return_value=True),
              patch("foundry.isolated_worker._run", side_effect=fn)):
            result = run_isolated_handoff(_request_for(SHA), SHA, _CONTROLLER_CHECKOUT)
        self.assertEqual(result["state"], "ISOLATED_REVIEW_ONLY", result)
        cmd = next(x for x in calls if len(x)>1 and x[1]=="run")
        nonce = next(x[len("--env=OPDB_SESSION_NONCE="):]
                     for x in cmd if x.startswith("--env=OPDB_SESSION_NONCE="))
        digest = next(x[len("--env=OPDB_REQUEST_SHA256="):]
                      for x in cmd if x.startswith("--env=OPDB_REQUEST_SHA256="))
        self.assertRegex(nonce, r"\\A[0-9a-f]{32}\\Z")
        expected = hashlib.sha256(json.dumps(
            _request_for(SHA), sort_keys=True, separators=(",", ":")
        ).encode("ascii")).hexdigest()
        self.assertEqual(digest, expected)

    def test_old_nonce_forged_request_digest_and_missing_field_fail_closed(self):
        for kwargs in ({"replayed_nonce":True}, {"forged_digest":True},
                       {"omit_nonce":True}):
            fn,_ = stub_docker(**kwargs)
            with (self.subTest(kwargs=kwargs),
                  patch("foundry.isolated_worker._docker_available",return_value=True),
                  patch("foundry.isolated_worker._run",side_effect=fn)):
                self.blocked(run_isolated_handoff(
                    _request_for(SHA), SHA, _CONTROLLER_CHECKOUT))

    def test_same_request_gets_distinct_one_use_nonces(self):
        issued=[]
        for _ in range(2):
            fn,calls = stub_docker()
            with (patch("foundry.isolated_worker._docker_available",return_value=True),
                  patch("foundry.isolated_worker._run",side_effect=fn)):
                result=run_isolated_handoff(_request_for(SHA),SHA,_CONTROLLER_CHECKOUT)
            self.assertEqual(result["state"],"ISOLATED_REVIEW_ONLY",result)
            cmd=next(x for x in calls if len(x)>1 and x[1]=="run")
            issued.append(next(x for x in cmd if x.startswith("--env=OPDB_SESSION_NONCE=")))
        self.assertNotEqual(issued[0],issued[1])


if __name__ == "__main__":
    unittest.main()
