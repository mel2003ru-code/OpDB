"""Run a REAL Docker confinement observation on one reviewed synthetic probe.

NOT a general-purpose AI/untrusted-code sandbox: the test probe is committed
and pre-reviewed; image digest is resolved from the local image store after
pull by CI. No source code is mounted writable, no network from the container,
no Docker socket in the container, no GitHub write tokens or production access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

from .sandbox_policy import plan

_IMAGE = re.compile(r"python:3\.11-slim@sha256:([a-f0-9]{64})\Z")

def _deny(reason):
    return {
        "state": "BLOCKED",
        "reason": reason,
        "runtime_confinement_observed": False,
        "untrusted_model_code_allowed": False,
        "candidate_executed": False,
        "production_allowed": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
    }


def _run(argv, timeout):
    """Bounded client request. Docker daemon is deliberately NOT exposed to guest."""
    return subprocess.run(argv, check=False, capture_output=True,
                          text=True, timeout=timeout)


def smoke(image, fixture, *, budget_seconds=12):
    """Check exact locally available digest, then run fixed confinement probe."""
    policy = plan(image, fixture, budget_seconds, probe="confinement")
    if policy["state"] != "POLICY_PLAN_ONLY":
        return _deny("Policy rejected sandbox configuration: " + policy["reason"])
    match = _IMAGE.fullmatch(image)
    if match is None:
        return _deny("Image must be pinned with an allowed sha256 digest")
    root = Path(fixture)
    try:
        before = {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in ("calculator.py", "quality_probe.py", "sandbox_runtime_probe.py")
        }
        inspected = _run(
            ["docker", "image", "inspect", "--format={{json .RepoDigests}}",
             image],
            5,
        )
        if inspected.returncode != 0:
            return _deny("Pinned image is not present locally; refusing auto pull")
        digests = json.loads(inspected.stdout.strip())
        if (not isinstance(digests, list)
                or not any(
                    isinstance(ref, str)
                    and ref.endswith("@sha256:" + match.group(1))
                    for ref in digests
                )):
            return _deny("Local OCI image digest does not match pinned reference")
        started = time.monotonic()
        result = _run(policy["command_argv"], budget_seconds)
        if result.returncode != 0:
            return _deny("Fixed synthetic container probe FAILED, return code "
                         + str(result.returncode) + " (no candidate admitted)")
        report = json.loads(result.stdout.strip())
        checks = report.get("checked")
        if (type(report) is not dict
                or report.get("probe") != "synthetic-fixed-review-only"
                or report.get("passed") is not True
                or report.get("untrusted_code_executed") is not False
                or report.get("full_agent_sandbox_attested") is not False
                or not isinstance(checks, dict)
                or set(checks) != {
                    "non_root_uid", "root_filesystem_read_only",
                    "work_mount_read_only", "tmpfs_noexec", "network_only_loopback",
                    "outbound_tcp_denied", "cgroup_memory_128m", "cgroup_pids_32",
                    "cgroup_cpu_half", "no_new_privileges", "no_effective_caps"
                }
                or not all(value is True for value in checks.values())):
            return _deny("Synthetic in-container isolation proof incomplete")
        after = {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in before
        }
        if before != after:
            return _deny("Fixture changed during attempted sandbox execution")
        return {
            "state": "OBSERVED_FIXED_PROBE_PASS",
            "image_digest": match.group(1),
            "checks": checks,
            "runtime_seconds": round(time.monotonic() - started, 3),
            "runtime_confinement_observed": True,
            "untrusted_model_code_allowed": False,
            "candidate_executed": False,
            "production_allowed": False,
            "github_write_allowed": False,
            "automatic_merge_allowed": False,
            "launch_authorized": False,
            "limitation": (
                "Observed on a single Docker CI runner with one pre-reviewed fixture. "
                "Image digest is recorded from the CI-local store, not pre-approved "
                "for production; host daemon, kernel, hostile code containment and "
                "external Quality sign-off are NOT independently attested."
            ),
        }
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError,
            json.JSONDecodeError) as exc:
        return _deny("Synthetic sandbox evidence unavailable: " + type(exc).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="One REAL synthetic Docker probe, not a general agent runner"
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    report = smoke(args.image, args.fixture)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    print(encoded, end="")
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    return 0 if report["state"] == "OBSERVED_FIXED_PROBE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
