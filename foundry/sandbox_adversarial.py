"""Adversarial FIXED probe in Docker: deny writes, secrets, daemon, seccomp bypass.

Not an arbitrary AI-code runner. Runs only the checked-in, reviewed fixture
after positive source-only sandbox probe. Tests two synthetic negative controls
with FAKE env data and a temporarily relaxed seccomp setting. No GitHub secrets
or Docker socket are passed inside a guest. Host results do NOT independently
attest a hostile guest or the Docker daemon/kernel.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from .sandbox_policy import plan
from .sandbox_smoke import smoke, _run

FILES = ("calculator.py", "quality_probe.py", "sandbox_runtime_probe.py",
         "sandbox_adversarial_probe.py")
CHECKS = frozenset({
    "root_write_denied", "source_write_denied", "docker_socket_absent",
    "secret_names_absent", "seccomp_filter_active",
    "baseline_confinement_pass", "no_host_network_interface",
})
CANARY = "GITHUB_TOKEN=FAKE_CANARY_FOR_NEGATIVE_TEST_ONLY"


def _deny(reason):
    return {
        "state": "BLOCKED",
        "reason": reason,
        "observations": {},
        "negative_controls_verified": False,
        "model_patch_execution_authorized": False,
        "arbitrary_code_isolation_attested": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
    }


def _report(proc):
    """Require precise guest proof, not just an error code or a free-form log."""
    try:
        result = json.loads(proc.stdout.strip())
    except (ValueError, TypeError, AttributeError):
        return None
    if type(result) is not dict or result.get("probe") != "fixed-reviewed-denied-operations":
        return None
    checks = result.get("checked")
    if (type(checks) is not dict or set(checks) != CHECKS
            or any(type(x) is not bool for x in checks.values())
            or result.get("untrusted_model_code_executed") is not False
            or result.get("hostile_code_sandbox_attested") is not False):
        return None
    return result


def assess(image, fixture, *, seconds=12):
    """Run exact fixed pre-reviewed guest, plus fake-env and seccomp negative cases."""
    positive = smoke(image, fixture, budget_seconds=seconds)
    if positive["state"] != "OBSERVED_FIXED_PROBE_PASS":
        return _deny("Baseline confinement observation did not pass")
    policy = plan(image, fixture, seconds, probe="adversarial")
    if policy["state"] != "POLICY_PLAN_ONLY":
        return _deny("Fixed reviewed adversarial plan rejected")
    root = Path(fixture)
    try:
        old = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
               for name in FILES}
        argv = policy["command_argv"]
        ordinary = _run(argv, seconds)
        passed = _report(ordinary)
        if (ordinary.returncode != 0 or passed is None
                or passed.get("passed") is not True
                or not all(passed["checked"].values())):
            return _deny("Denied-operation fixed probe did not confirm all controls")
        # One fake canary only; no actual GitHub secret or token provided.
        image_index = argv.index(image)
        synthetic_env = (
            argv[:image_index] + ["--env=" + CANARY] + argv[image_index:]
        )
        env = _run(synthetic_env, seconds)
        env_report = _report(env)
        if (env.returncode == 0 or env_report is None
                or env_report.get("passed") is not False
                or env_report["checked"]["secret_names_absent"] is not False):
            return _deny("Fake canary injection was not detected")
        # Seccomp is relaxed only for a disposable, pre-reviewed synthetic
        # probe. All other safety flags remain intact.
        synthetic_seccomp = (
            argv[:image_index] + ["--security-opt=seccomp=unconfined"]
            + argv[image_index:]
        )
        unconfined = _run(synthetic_seccomp, seconds)
        seccomp_report = _report(unconfined)
        if (unconfined.returncode == 0 or seccomp_report is None
                or seccomp_report.get("passed") is not False
                or seccomp_report["checked"]["seccomp_filter_active"] is not False):
            return _deny("Relaxed seccomp was not detected by guest")
        new = {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
               for name in FILES}
        if old != new:
            return _deny("Reviewed fixture files changed during sandbox test")
        return {
            "state": "FIXED_DENIALS_OBSERVED",
            "image_digest": positive["image_digest"],
            "observations": passed["checked"],
            "negative_controls_verified": True,
            "synthetic_canary_detected": True,
            "synthetic_relaxed_seccomp_detected": True,
            "model_patch_execution_authorized": False,
            "arbitrary_code_isolation_attested": False,
            "github_write_allowed": False,
            "production_allowed": False,
            "launch_authorized": False,
            "scope": (
                "Only fixed, reviewed code on one ephemeral CI Docker runner. "
                "No LLM code, no actual secret value, no Docker socket, "
                "no independent host/guest adversarial isolation attestation."
            ),
        }
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
        return _deny("Cannot establish fixed denial evidence: " + type(exc).__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run reviewed denied-operation sandbox fixture only")
    parser.add_argument("--image", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = assess(args.image, args.fixture)
    output = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    print(output, end="")
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    return 0 if result["state"] == "FIXED_DENIALS_OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
