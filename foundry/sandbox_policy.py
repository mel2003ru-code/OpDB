"""No-network container execution *policy*, not a verified OS sandbox.

Creates a fully specified Docker argv for a single fixed reviewed test probe.
It NEVER executes a container, calls Docker, pulls an image or grants authority.
A future separately reviewed runner may consume the plan only after it verifies
the local pinned image, container runtime and actual kernel confinement.
"""
import argparse
import json
from pathlib import Path
import re

_IMAGE = re.compile(r"python:3\.11-slim@sha256:[a-f0-9]{64}\Z")
_TEST = "/work/quality_probe.py"
_MAX_SECONDS = 15


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
    if type(probe) is not str or probe not in ("quality", "confinement", "adversarial"):
        return dict(locked, state="BLOCKED", reason="Only reviewed synthetic probes permitted")
    root = Path(fixture_path)
    try:
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            return dict(locked, state="BLOCKED", reason="Absolute nonsymlink work directory required")
        checks = ("calculator.py", "quality_probe.py")
        if probe in ("confinement", "adversarial"):
            checks += ("sandbox_runtime_probe.py",)
        if probe == "adversarial":
            checks += ("sandbox_adversarial_probe.py",)
        if any(not (root / x).is_file() or (root / x).is_symlink()
               for x in checks):
            return dict(locked, state="BLOCKED", reason="Missing reviewed fixture files")
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
        "--network=none", "--read-only",
        "--cap-drop=ALL", "--security-opt=no-new-privileges",
        "--pids-limit=32", "--memory=128m", "--memory-swap=128m",
        "--cpus=0.5", "--user=65534:65534",
        "--workdir=/work", "--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
        "--mount=type=bind,src=" + str(root) + ",dst=/work,readonly",
        image, "python", "-I", "-B",
        (_TEST if probe == "quality" else
         "/work/sandbox_runtime_probe.py" if probe == "confinement" else
         "/work/sandbox_adversarial_probe.py"),
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
    p.add_argument("--probe", choices=("quality", "confinement", "adversarial"), default="quality")
    args = p.parse_args(argv)
    result = plan(args.image, args.fixture, args.budget_seconds, args.probe)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["state"] == "POLICY_PLAN_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
