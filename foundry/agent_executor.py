"""OpDB Agent Executor 0.1 — bounded, offline, READ-ONLY repository demo.

This is a deterministic patch executor, NOT an LLM and NOT an autonomous GitHub
PR author. It applies one *hard-coded, allowlisted* synthetic task in an
ephemeral temporary directory. No user-supplied commands, paths, patches, URLs
or code are executed. Successful output is a reviewable DIFF, never a merge.
"""
import argparse
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

_COMMIT = re.compile(r"[0-9a-fA-F]{40}\Z")
_TASK = "demo-add-v1"
_ISSUE = 31
_MAX_SECONDS = 12
_FIXTURE = Path(__file__).resolve().parent / "fixtures"
_FROM = "    return left - right\n"
_TO = "    return left + right\n"


def _decision(state, sha=None, details=None, diff=None, before=None, after=None):
    return {
        "schema_version": 1,
        "state": state,
        "task_key": _TASK,
        "issue_number": _ISSUE,
        "source_sha": sha,
        "details": details or [],
        "negative_control_failed_as_expected": before is False,
        "candidate_tests_passed": after is True,
        "candidate_diff": diff,
        "candidate_diff_sha256": (
            hashlib.sha256(diff.encode("utf-8")).hexdigest()
            if isinstance(diff, str) else None
        ),
        "sandbox_executed": before is not None,
        "repository_modified": False,
        "github_branch_created": False,
        "pull_request_created": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
        "model_invoked": False,
        "human_review_required": True,
        "scope": "Fixed offline fixture only; no LLM, real code fix or PR creation",
    }


def validate_task(task, expected_sha):
    """Exact allowlisted task envelope. No untrusted code or paths accepted."""
    if not isinstance(expected_sha, str) or not _COMMIT.fullmatch(expected_sha):
        return "Exact checked-out 40-hex Git commit required"
    if type(task) is not dict or set(task) != {
        "schema_version", "task_key", "issue_number", "source_sha",
        "max_attempts", "budget_seconds"
    }:
        return "Task envelope is missing fields or includes unapproved fields"
    if type(task["schema_version"]) is not int or task["schema_version"] != 1:
        return "Task schema invalid"
    if task["task_key"] != _TASK:
        return "Task is outside the one approved offline fixture"
    if type(task["issue_number"]) is not int or task["issue_number"] != _ISSUE:
        return "Task issue is not the allowlisted synthetic Issue #31"
    if task["source_sha"] != expected_sha:
        return "Task source SHA does not match the checked-out commit"
    if type(task["max_attempts"]) is not int or task["max_attempts"] != 1:
        return "Exactly one attempt is permitted in v0.1"
    if (type(task["budget_seconds"]) is not int
            or not 2 <= task["budget_seconds"] <= _MAX_SECONDS):
        return "Execution budget must be an integer 2..12 seconds"
    return None


def _run_quality(probe: Path, cwd: Path, deadline: float):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Executor budget exhausted")
    # -I isolated mode, -B no bytecode; cwd is a disposable scratch folder.
    # Only the reviewed fixed test probe is permitted, NEVER task-provided code.
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(probe)],
            cwd=cwd,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"},
            capture_output=True, text=True, check=False,
            timeout=remaining,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("Executor test time budget exceeded") from exc
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-400:]


def execute(task, expected_sha, fixture_dir=None):
    """Run a synthetic RED -> PATCH -> GREEN cycle without modifying checkout."""
    problem = validate_task(task, expected_sha)
    if problem:
        return _decision("BLOCKED", details=[problem])
    folder = Path(fixture_dir) if fixture_dir is not None else _FIXTURE
    source = folder / "calculator.py"
    probe = folder / "quality_probe.py"
    # This executor is only allowed to access the checked-in reviewed fixture.
    # The test-only fixture_dir injection is explicitly NOT available in CLI.
    try:
        if any(not path.is_file() or path.is_symlink() for path in (source, probe)):
            return _decision("BLOCKED", expected_sha,
                             ["Missing or symbolic-link fixture"])
        original = source.read_text(encoding="utf-8")
        probe_text = probe.read_text(encoding="utf-8")
        if original.count(_FROM) != 1 or _TO in original:
            return _decision("BLOCKED", expected_sha,
                             ["Synthetic source changed; explicit review required"])
    except (OSError, UnicodeError) as exc:
        return _decision("BLOCKED", expected_sha, [type(exc).__name__])
    budget = task["budget_seconds"]
    deadline = time.monotonic() + budget
    try:
        with tempfile.TemporaryDirectory(prefix="opdb-executor-demo-") as tmp:
            scratch = Path(tmp)
            subject = scratch / "calculator.py"
            test = scratch / "quality_probe.py"
            subject.write_text(original, encoding="utf-8")
            test.write_text(probe_text, encoding="utf-8")
            before, _ = _run_quality(test, scratch, deadline)
            if before:
                return _decision("NEEDS_INVESTIGATION", expected_sha,
                                 ["Pre-patch test unexpectedly passed; cannot prove repair"],
                                 before=True)
            changed = original.replace(_FROM, _TO)
            subject.write_text(changed, encoding="utf-8")
            after, tail = _run_quality(test, scratch, deadline)
            if not after:
                return _decision("FAILED_CANDIDATE", expected_sha,
                                 ["Patch did not pass independently checked probe",
                                  tail], before=False, after=False)
            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True),
                changed.splitlines(keepends=True),
                fromfile="a/foundry/fixtures/calculator.py",
                tofile="b/foundry/fixtures/calculator.py",
            ))
            return _decision(
                "DRAFT_PROPOSAL_READY", expected_sha,
                ["Synthetic baseline RED and patched candidate GREEN",
                 "Proposed diff exists in report, not applied to GitHub",
                 "Reviewer must approve any future agent-generated code"],
                diff=diff, before=False, after=True,
            )
    except (OSError, TimeoutError, UnicodeError, ValueError) as exc:
        return _decision("FAILED_CANDIDATE", expected_sha,
                         [type(exc).__name__ + ": " + str(exc)])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Safe offline executor DEMO")
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--demo-task", action="store_true",
                        help="Run one fixed synthetic Issue #31 task")
    parser.add_argument("--output", help="Report JSON; no GitHub side effects")
    args = parser.parse_args(argv)
    if not args.demo_task:
        result = _decision("NOT_CONFIGURED",
                           details=["No approved synthetic task was selected"])
    else:
        task = {
            "schema_version": 1, "task_key": _TASK, "issue_number": _ISSUE,
            "source_sha": args.expected_sha, "max_attempts": 1,
            "budget_seconds": _MAX_SECONDS,
        }
        result = execute(task, args.expected_sha)
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    print(encoded, end="")
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    return 0 if result["state"] in ("DRAFT_PROPOSAL_READY", "NOT_CONFIGURED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
