"""No-network container execution *policy*, not a verified OS sandbox.

Creates a fully specified Docker argv for a single fixed reviewed test probe.
It NEVER executes a container, calls Docker, pulls an image or grants authority.
A future separately reviewed runner may consume the plan only after it verifies
the local pinned image, container runtime and actual kernel confinement.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

_IMAGE = re.compile(r"python:3\.11-slim@sha256:[a-f0-9]{64}\Z")
_TEST = "/work/quality_probe.py"
_MAX_SECONDS = 15
# Canonical reviewed-fixture root. An arbitrary caller-supplied directory with
# lookalike filenames can contain executable Python; NEVER mount it as trusted.
_REVIEWED_FIXTURE = Path(__file__).resolve().parent / "fixtures"
# Fixed SHA-256 of reviewed synthetic fixtures. Any source change requires
# updating these values in a separately reviewed PR; filename/path alone is
# NOT sufficient to authorize Python execution.
_REVIEWED_CONTENT_SHA256 = {
    "calculator.py": "97ecad52211a40a7ebf00716cc9ee9c2f76a9b4a5eda731afe2921221f3e7452",
    "quality_probe.py": "3f636ed87e607ec2f5869492336449cc313b5deaf3ccb4a9338f9e31c79347a2",
    "sandbox_runtime_probe.py": "a0f56d4e067186e1a7f0c5babca9539f635739e3b5250948bf95bd08afd3268a",
    "sandbox_adversarial_probe.py": "928d8d75bf9dd62ff9f27f9579edbb6fddf3a3b558d05d8b43db23206c2078ba",
    "handoff_worker.py": "e44d1af3bb9fa6e1b20be4789bbdc3b4a3d6e147ed57c5bf4bde273929ac350a",
}
_MAX_REVIEWED_BYTES = 16 * 1024


def plan(image, fixture_path, time_seconds=10, probe="quality"):
    locked = {
        "state": "NOT_CONFIGURED",
        "image": None,
        "command_argv": None,
        "runtime_verified": False,
        "network_isolation_verified": False,
        "candidate_executed": False,
        "container_started": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
        "reason": "Pinned local image and independent OS isolation not attested",
    }
    if not isinstance(image, str) or not _IMAGE.fullmatch(image):
        return dict(locked, state="BLOCKED", reason="Exact allowlisted image digest required")
    if type(time_seconds) is not int or not 1 <= time_seconds <= _MAX_SECONDS:
        return dict(locked, state="BLOCKED", reason="Invalid bounded time budget")
    if type(probe) is not str or probe not in ("quality", "confinement", "adversarial", "handoff"):
        return dict(locked, state="BLOCKED", reason="Only reviewed synthetic probes permitted")
    if not isinstance(fixture_path, (str, Path)):
        return dict(locked, state="BLOCKED", reason="Reviewed fixture path required")
    root = Path(fixture_path)
    # Validate BEFORE any filesystem access or external subprocess. Use exact
    # lexical path identity, not .resolve() here: resolve() would follow links
    # supplied by an attacker and let a symlink alias pass this comparison.
    if root != _REVIEWED_FIXTURE:
        return dict(locked, state="BLOCKED",
                    reason="Unreviewed fixture directory: only bundled fixture allowed")
    try:
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            return dict(locked, state="BLOCKED", reason="Absolute nonsymlink work directory required")
        checks = ("calculator.py", "quality_probe.py")
        if probe in ("confinement", "adversarial", "handoff"):
            checks += ("sandbox_runtime_probe.py",)
        if probe in ("adversarial", "handoff"):
            checks += ("sandbox_adversarial_probe.py",)
        if probe == "handoff":
            checks += ("handoff_worker.py",)
        if any(not (root / x).is_file() or (root / x).is_symlink()
               for x in checks):
            return dict(locked, state="BLOCKED", reason="Missing reviewed fixture files")
        for name in checks:
            with (root / name).open("rb") as handle:
                raw = handle.read(_MAX_REVIEWED_BYTES + 1)
            if (len(raw) > _MAX_REVIEWED_BYTES
                    or hashlib.sha256(raw).hexdigest()
                    != _REVIEWED_CONTENT_SHA256[name]):
                return dict(locked, state="BLOCKED",
                            reason="Reviewed synthetic fixture content hash mismatch")
        # Check if any ancestor is a symlink; bind-mount must not follow an
        # attacker-controlled symlink on the host.
        if any(p.is_symlink() for p in (root, *root.parents)):
            return dict(locked, state="BLOCKED", reason="Symlinked parent in fixture path")
    except OSError:
        return dict(locked, state="BLOCKED", reason="Unreadable fixture")
    # A PLAN, not permission to run. docker --pull=never prevents hidden
    # outbound registry access on a missing pinned image. The image must
    # already be local and independently verified by a future runtime.
    argv = [
        "docker", "run", "--rm", "--pull=never",
        "--network=none", "--read-only", "--log-driver=none",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--memory-swap=128m",
        "--cpus=0.5", "--user=65534:65534", "--shm-size=8m",
        "--workdir=/work", "--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
        "--mount=type=bind,src=" + str(root) + ",dst=/work,readonly",
        image, "python", "-I", "-B",
        (_TEST if probe == "quality" else
         "/work/sandbox_runtime_probe.py" if probe == "confinement" else
         "/work/sandbox_adversarial_probe.py" if probe == "adversarial" else
         "/work/handoff_worker.py"),
    ]
    return dict(
        locked, state="POLICY_PLAN_ONLY", image=image, command_argv=argv,
        reason="Policy flags assembled; not executed nor attested",
    )


def main(argv=None):
    p = argparse.ArgumentParser(description="Inspect a safe, non-executing Docker policy")
    p.add_argument("--image", help="Previously verified local python:3.11-slim@sha256:<digest>")
    p.add_argument("--fixture", help="Absolute path of an isolated reviewed fixture")
    p.add_argument("--budget-seconds", type=int, default=10)
    p.add_argument("--probe", choices=("quality", "confinement", "adversarial", "handoff"), default="quality")
    args = p.parse_args(argv)
    result = plan(args.image, args.fixture, args.budget_seconds, args.probe)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"] == "POLICY_PLAN_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
