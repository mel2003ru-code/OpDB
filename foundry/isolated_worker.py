"""S-008: observed OS-separated OFFLINE data handoff with explicit trust refusal.

The Docker *host* still runs PR-controlled Python. That is NOT a trusted
controller. Only the fixed SHA-pinned synthetic handoff fixture can execute.
Arbitrary worker/LLM code, source checkout mutation, PR publishing and launch
remain forbidden. This module is not a production security boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import secrets
import subprocess
import tempfile

from .sandbox_policy import _REVIEWED_FIXTURE, plan
from .sandbox_runner import (
    DOCKER, PINNED_IMAGE, EXPECTED_KEYS, MAX_EXECUTION_SECONDS,
    _docker_available, _run,
)
from .worker_contract import _authoritative_checkout, _load, _valid_request, review

_OBSERVED = EXPECTED_KEYS["confinement"] | EXPECTED_KEYS["adversarial"] | {
    "shm_8m", "tmp_8m"
}
_REPORT_KEYS = frozenset({
    "probe", "passed", "checked", "reply", "model_invoked",
    "arbitrary_model_code_executed", "github_write_allowed",
    "trusted_controller_attested", "launch_authorized",
    "session_nonce", "request_sha256",
})


def _denied(state, reason):
    return {
        "state": state, "reason": reason, "review": None,
        "os_worker_restrictions_observed": False,
        "trusted_controller_attested": False,
        "arbitrary_model_code_executed": False,
        "model_invoked": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
    }


def _parse_report(stdout, expected_nonce, expected_request_sha256):
    def no_duplicates(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate guest JSON key")
            out[key] = value
        return out
    lines = stdout.strip().splitlines()
    if len(lines) != 1:
        return None
    obj = json.loads(lines[0], object_pairs_hook=no_duplicates)
    if type(obj) is not dict or set(obj) != _REPORT_KEYS:
        return None
    if (obj["probe"] != "fixed-data-only-handoff-s008"
            or type(obj["session_nonce"]) is not str
            or obj["session_nonce"] != expected_nonce
            or type(obj["request_sha256"]) is not str
            or obj["request_sha256"] != expected_request_sha256
            or obj["passed"] is not True
            or type(obj["checked"]) is not dict
            or set(obj["checked"]) != _OBSERVED
            or any(type(v) is not bool or not v for v in obj["checked"].values())
            or any(obj[key] is not False for key in (
                "model_invoked", "arbitrary_model_code_executed",
                "github_write_allowed", "trusted_controller_attested",
                "launch_authorized"
            ))):
        return None
    return obj["reply"]


def run_isolated_handoff(request, checkout_sha, checkout_root):
    """Run *fixed reviewed* worker in Docker, quarantine one data-only reply."""
    if not _valid_request(request, checkout_sha):
        return _denied("BLOCKED", "Unapproved or modified fixed handoff request")
    if not _authoritative_checkout(checkout_root):
        return _denied("BLOCKED", "Checkout identity is not controller-owned")
    if not _docker_available():
        return _denied("NOT_CONFIGURED", "Docker executable not available")
    # This is session freshness and request integrity, NOT an authenticated
    # trust root: a PR-controlled host could still mint or forge both values.
    nonce = secrets.token_hex(16)
    request_sha256 = hashlib.sha256(json.dumps(
        request, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")).hexdigest()
    policy = plan(PINNED_IMAGE, _REVIEWED_FIXTURE, time_seconds=12, probe="handoff")
    if policy["state"] != "POLICY_PLAN_ONLY":
        return _denied("BLOCKED", "Pinned reviewed handoff fixture not admitted")
    try:
        check = _run([DOCKER, "image", "inspect", "--format", "{{.Id}}",
                      PINNED_IMAGE], timeout=8)
        image_id = check.stdout.strip()
        if (check.returncode != 0 or len(image_id) != 71
                or not image_id.startswith("sha256:")
                or any(x not in "0123456789abcdef" for x in image_id[7:])):
            return _denied("NOT_CONFIGURED", "Pinned Docker image unavailable")
        with tempfile.TemporaryDirectory(prefix="opdb-s008-cid-") as directory:
            name = "opdb-s008-" + secrets.token_hex(8)
            cidfile = Path(directory) / "cid"
            argv = list(policy["command_argv"])
            if (not argv or argv[0] != "docker"
                    or argv.count(PINNED_IMAGE) != 1
                    or argv[-1] != "/work/handoff_worker.py"):
                return _denied("BLOCKED", "Worker argv violates reviewed policy")
            position = argv.index(PINNED_IMAGE)
            argv[0] = DOCKER
            argv[position:position] = [
                "--name=" + name, "--cidfile=" + str(cidfile),
                "--env=OPDB_SOURCE_SHA=" + checkout_sha,
                "--env=OPDB_SESSION_NONCE=" + nonce,
                "--env=OPDB_REQUEST_SHA256=" + request_sha256,
            ]
            result = None
            failure = None
            cleanup = False
            try:
                result = _run(argv, timeout=MAX_EXECUTION_SECONDS)
            except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
                failure = type(exc).__name__
            finally:
                # This is a Docker-host operation, never granted to the guest.
                try:
                    _run([DOCKER, "rm", "-f", name], timeout=5)
                except (OSError, subprocess.TimeoutExpired, RuntimeError):
                    pass
                try:
                    check = _run([
                        DOCKER, "ps", "-a", "--format", "{{.Names}}",
                        "--filter", "name=^/" + name + "$",
                    ], timeout=5)
                    cleanup = check.returncode == 0 and not check.stdout.strip()
                except (OSError, subprocess.TimeoutExpired, RuntimeError):
                    cleanup = False
            if not cleanup:
                return _denied("BLOCKED", "Container cleanup not verified")
            if failure is not None or result is None or result.returncode != 0:
                return _denied("BLOCKED", "Fixed worker failed: " + (failure or "guest exit"))
            try:
                reply = _parse_report(result.stdout, nonce, request_sha256)
            except (ValueError, TypeError, UnicodeError):
                reply = None
            if reply is None:
                return _denied("BLOCKED", "Fixed worker report invalid or duplicated")
            verdict = review(request, reply, checkout_sha, checkout_root)
            if verdict["state"] != "REVIEW_ONLY_PATCH":
                return _denied("BLOCKED", "Worker data rejected by quarantine policy")
            return {
                **_denied("ISOLATED_REVIEW_ONLY",
                          "One fixed guest produced data; independent controller absent"),
                "review": verdict,
                "os_worker_restrictions_observed": True,
            }
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
        return _denied("BLOCKED", "Container runtime or bounded output failed")


def main(argv=None):
    parser = argparse.ArgumentParser(description="S-008 fixed container data handoff only")
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--checkout", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        request = _load(args.request_file)
        report = run_isolated_handoff(request, args.expected_sha, args.checkout)
    except (OSError, ValueError, TypeError, UnicodeError):
        report = _denied("BLOCKED", "Invalid bounded handoff request")
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["state"] == "ISOLATED_REVIEW_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
