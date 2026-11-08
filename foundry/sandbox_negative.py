"""Independent NEGATIVE Docker configuration controls on a fixed reviewed fixture.

Disables exactly one control per run and demands the in-container probe detect
it. Even a complete success does NOT authorize untrusted code execution or a
production release. Docker is only invoked in an ephemeral CI job on known code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .sandbox_policy import plan
from .sandbox_smoke import smoke, _run

# Never accept user-supplied flags, image commands, files, or test bodies.
CONTROLS = (
    ("network", "--network=none", "network_only_loopback"),
    ("non_root", "--user=65534:65534", "non_root_uid"),
    ("memory", "--memory=128m", "cgroup_memory_128m"),
)
PROBES = ("calculator.py", "quality_probe.py", "sandbox_runtime_probe.py")
EXPECTED = frozenset({
    "non_root_uid", "root_filesystem_read_only", "work_mount_read_only",
    "tmpfs_noexec", "network_only_loopback", "outbound_tcp_denied",
    "cgroup_memory_128m", "cgroup_pids_32", "cgroup_cpu_half",
    "no_new_privileges", "no_effective_caps",
})


def _deny(reason, controls=None):
    return {
        "state": "BLOCKED",
        "reason": reason,
        "negative_controls": controls or {},
        "expected_failures_observed": False,
        "untrusted_model_code_allowed": False,
        "candidate_executed": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
    }


def verify_negative_controls(image, fixture, *, budget_seconds=12):
    """Three real Docker runs with exactly one deliberately removed guard each.

    A *positive* control MUST pass first. This is deliberately a narrow
    experiment on the reviewed fixture, not an arbitrary executor.
    """
    baseline = smoke(image, fixture, budget_seconds=budget_seconds)
    if baseline["state"] != "OBSERVED_FIXED_PROBE_PASS":
        return _deny("Baseline confinement probe did not pass")
    policy = plan(image, fixture, budget_seconds, probe="confinement")
    if policy["state"] != "POLICY_PLAN_ONLY":
        return _deny("No approved immutable probe plan")
    try:
        root = Path(fixture)
        old = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
               for p in PROBES}
        report = {}
        for name, flag, expected_false in CONTROLS:
            argv = policy["command_argv"]
            if argv.count(flag) != 1:
                return _deny("Expected guard missing from baseline plan", report)
            unsafe_argv = [arg for arg in argv if arg != flag]
            if len(unsafe_argv) != len(argv) - 1:
                return _deny("Negative mutation did not remove exactly one guard", report)
            proc = _run(unsafe_argv, budget_seconds)
            if proc.returncode == 0:
                return _deny(name + ": removal not detected by exit status", report)
            try:
                guest = json.loads(proc.stdout.strip())
            except (ValueError, TypeError):
                return _deny(
                    name + ": guest report absent/malformed, docker exit "
                    + str(proc.returncode) + "; cannot claim observed isolation",
                    report,
                )
            if type(guest) is not dict:
                return _deny(name + ": malformed guest report", report)
            checks = guest.get("checked")
            if (guest.get("probe") != "synthetic-fixed-review-only"
                    or guest.get("passed") is not False
                    or guest.get("untrusted_code_executed") is not False
                    or guest.get("full_agent_sandbox_attested") is not False
                    or not isinstance(checks, dict)
                    or set(checks) != EXPECTED
                    or any(type(v) is not bool for v in checks.values())
                    or checks[expected_false] is not False):
                return _deny(name + ": expected negative flag not observed", report)
            # We never claim other checks are authoritative, but require that
            # the *specific* intentionally disabled guard is reported unsafe.
            report[name] = {
                "removed_guard": flag,
                "detected_check": expected_false,
                "detected_unsafe": True,
                "guest_exit_nonzero": True,
            }
        new = {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
               for p in PROBES}
        if new != old:
            return _deny("Checked-out reviewed fixtures were modified", report)
        return {
            "state": "EXPECTED_FAILURES_OBSERVED",
            "image_digest": baseline["image_digest"],
            "negative_controls": report,
            "expected_failures_observed": True,
            "untrusted_model_code_allowed": False,
            "candidate_executed": False,
            "github_write_allowed": False,
            "production_allowed": False,
            "automatic_merge_allowed": False,
            "launch_authorized": False,
            "scope": (
                "One fixed, reviewed probe on one CI host. This does NOT "
                "establish host isolation or authorize arbitrary generated code."
            ),
        }
    except (subprocess.TimeoutExpired, OSError, ValueError, TypeError) as exc:
        return _deny("Negative control evidence unavailable: " + type(exc).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deliberately fail fixed Docker guards; no model/production access"
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    outcome = verify_negative_controls(args.image, args.fixture)
    output = json.dumps(outcome, ensure_ascii=False, indent=2) + "\n"
    print(output, end="")
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    return 0 if outcome["state"] == "EXPECTED_FAILURES_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
