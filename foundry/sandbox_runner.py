"""Bounded runtime smoke-check of *reviewed* Docker sandbox probes ONLY.

This is deliberately not a code-generating agent and NOT a runner for model-
produced Python. The exact Docker image digest and probes are fixed in source.
No pull occurs here; a separate CI setup step fetches the pinned image.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from .sandbox_policy import _REVIEWED_FIXTURE, plan

# Index digest of Docker Official Image python:3.11-slim, recorded on 2026-11-08.
# Updating it MUST involve a code review and a new runtime evidence run.
PINNED_IMAGE = (
    "python:3.11-slim@sha256:"
    "07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535"
)
DOCKER = "/usr/bin/docker"
ALLOWED_PROBES = ("confinement", "adversarial")
PROBE_NAMES = {
    "confinement": "synthetic-fixed-review-only",
    "adversarial": "fixed-reviewed-denied-operations",
}
EXPECTED_KEYS = {
    "confinement": frozenset((
        "non_root_uid", "root_filesystem_read_only", "work_mount_read_only",
        "tmpfs_noexec", "network_only_loopback", "outbound_tcp_denied",
        "cgroup_memory_128m", "cgroup_pids_32", "cgroup_cpu_half",
        "no_new_privileges", "no_effective_caps",
    )),
    "adversarial": frozenset((
        "root_write_denied", "source_write_denied", "docker_socket_absent",
        "secret_names_absent", "seccomp_filter_active",
        "baseline_confinement_pass", "no_host_network_interface",
    )),
}
MAX_EXECUTION_SECONDS = 25


def _response(state, reason, probe=None, observed=None, image_id=None):
    return {
        "schema_version": 1,
        "state": state,
        "reason": reason,
        "probe": probe,
        "pinned_image": PINNED_IMAGE,
        "image_id": image_id,
        "observed": observed,
        "candidate_executed": False,
        "untrusted_model_code_executed": False,
        "agent_sandbox_attested": False,
        "model_invoked": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
    }


def _docker_env():
    """Explicitly omit all GitHub/auth/model environment variables."""
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": "/nonexistent",
        "DOCKER_CONFIG": "/nonexistent",
        "DOCKER_HOST": "unix:///var/run/docker.sock",
    }


def _run(args, *, timeout):
    return subprocess.run(
        args,
        executable=DOCKER,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=_docker_env(),
    )


def _docker_available():
    return Path(DOCKER).is_file() and os.access(DOCKER, os.X_OK)


def run_probe(probe):
    """Run a single reviewed probe in a no-network, read-only Docker guest.

    Host has Docker access ONLY in this smoke-runner job, no GH write token.
    This makes no claim of resisting a kernel escape or hostile OCI image.
    """
    if type(probe) is not str or probe not in ALLOWED_PROBES:
        return _response("BLOCKED", "Unknown probe; executable input forbidden")
    if not _docker_available():
        return _response("NOT_CONFIGURED", "Docker executable missing on runner", probe)
    policy = plan(PINNED_IMAGE, _REVIEWED_FIXTURE, time_seconds=12, probe=probe)
    if policy["state"] != "POLICY_PLAN_ONLY":
        return _response("BLOCKED", "Reviewable sandbox policy not satisfied", probe)
    try:
        # MUST be previously pulled, by immutable digest, without accessing a
        # registry during an execution. Never call docker pull or build here.
        check = _run(
            [DOCKER, "image", "inspect", "--format", "{{.Id}}", PINNED_IMAGE],
            timeout=8,
        )
        if check.returncode != 0 or not check.stdout.startswith("sha256:"):
            return _response(
                "NOT_CONFIGURED",
                "Pinned image is unavailable locally; no implicit pull",
                probe,
            )
        image_id = check.stdout.strip().splitlines()[0]
        with tempfile.TemporaryDirectory(prefix="opdb-container-smoke-") as folder:
            cidfile = Path(folder) / "cid"
            # Use a stable per-job name; the runner is a disposable job and
            # probes execute sequentially. A fixed name supports cleanup when
            # the process times out before writing --cidfile.
            name = "opdb-synthetic-smoke"
            argv = list(policy["command_argv"])
            if (not argv or argv[0] != "docker"
                    or argv.count(PINNED_IMAGE) != 1):
                return _response("BLOCKED", "Policy argv changed unexpectedly", probe)
            position = argv.index(PINNED_IMAGE)
            argv[0] = DOCKER
            argv[position:position] = [
                "--name=" + name, "--cidfile=" + str(cidfile)
            ]
            try:
                result = _run(argv, timeout=MAX_EXECUTION_SECONDS)
            except subprocess.TimeoutExpired:
                return _response("BLOCKED", "Container exceeded wall-clock budget",
                                 probe, image_id=image_id)
            finally:
                # Separate Docker cleanup; no shell, no Docker socket exposure
                # to the container. Never leave a timed-out guest running.
                try:
                    _run([DOCKER, "rm", "-f", name], timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
            if result.returncode != 0:
                return _response(
                    "BLOCKED", "Reviewed runtime probe failed or was denied",
                    probe, image_id=image_id,
                )
            # The ONLY accepted stdout is the reviewed probe's one JSON line.
            try:
                lines = result.stdout.strip().splitlines()
                observed = json.loads(lines[-1]) if len(lines) == 1 else None
            except (ValueError, TypeError):
                observed = None
            if (type(observed) is not dict
                    or observed.get("probe") != PROBE_NAMES[probe]
                    or observed.get("passed") is not True
                    or type(observed.get("checked")) is not dict
                    or set(observed["checked"]) != EXPECTED_KEYS[probe]
                    or not all(type(v) is bool and v for v in observed["checked"].values())
                    or (probe == "confinement" and (
                        observed.get("untrusted_code_executed") is not False
                        or observed.get("full_agent_sandbox_attested") is not False
                    ))
                    or (probe == "adversarial" and (
                        observed.get("untrusted_model_code_executed") is not False
                        or observed.get("hostile_code_sandbox_attested") is not False
                    ))):
                return _response(
                    "BLOCKED", "Runtime observations failed closed",
                    probe, image_id=image_id,
                )
            return _response(
                "REVIEWED_PROBE_PASS",
                "Fixed synthetic container probe observed configured restrictions",
                probe, observed=observed["checked"], image_id=image_id,
            )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return _response("BLOCKED", "Container runtime check failed", probe)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Execute fixed reviewed Docker probes; no model code"
    )
    parser.add_argument("--probe", required=True)
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    result = run_probe(args.probe)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(payload, end="")
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    return 0 if result["state"] == "REVIEWED_PROBE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
