"""S-009: bounded, deterministic Foundry work-queue advice (NO execution).

A task is only a suggested human/assistant engineering edit in draft PR #32.
This code never calls GitHub, Docker, AI models, subprocesses, or a shell.
PR-controlled task state is NOT an independently trusted admission decision.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = "mel2003ru-code/OpDB"
SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_JSON_BYTES = 8192
TASKS = (
    ("FND-009A", (), "READ_ONLY_SNAPSHOT"),
    ("FND-009B", ("FND-009A",), "DURABLE_IDEMPOTENCY_LEDGER"),
    ("FND-009C", ("FND-009B",), "INDEPENDENT_REVIEW_HANDOFF"),
)
TASK_IDS = frozenset(t[0] for t in TASKS)
STATES = frozenset(("READY", "DONE", "BLOCKED"))
CI_STATES = frozenset(("PASS", "FAIL_EXECUTED", "NO_RUNNER", "UNKNOWN"))


def _result(state, reason, *, task_id=None, task_kind=None, sha=None, ci=None):
    return {
        "schema_version": 1,
        "state": state,
        "reason": reason,
        "repository": REPO,
        "source_sha": sha,
        "task_id": task_id,
        "task_kind": task_kind,
        "ci_observation": ci,
        "ci_attested": False,
        "task_execution_authorized": False,
        "github_write_authorized": False,
        "trusted_controller_attested": False,
        "worker_code_execution_authorized": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
        "human_review_required": True,
    }


def next_step(queue, *, current_sha, ci_state="UNKNOWN"):
    """Strictly propose the first unfinished, known, dependency-ready task.

    Caller-supplied metadata is untrusted. Even a complete READY plan does
    not authorize a worker, repository mutation, or a successful CI claim.
    """
    if (type(current_sha) is not str or not SHA.fullmatch(current_sha)
            or type(ci_state) is not str or ci_state not in CI_STATES):
        return _result("HOLD", "Missing current commit SHA or recognized CI status")
    if (type(queue) is not dict
            or set(queue) != {"schema_version", "repository", "pr_number",
                              "issue_number", "security_blocker", "items"}
            or type(queue["schema_version"]) is not int
            or queue["schema_version"] != 1
            or queue["repository"] != REPO
            or type(queue["pr_number"]) is not int or queue["pr_number"] != 32
            or type(queue["issue_number"]) is not int or queue["issue_number"] != 31
            or type(queue["security_blocker"]) is not int
            or queue["security_blocker"] != 21):
        return _result("HOLD", "Invalid or untrusted work-queue header",
                       sha=current_sha, ci=ci_state)
    items = queue["items"]
    if type(items) is not list or len(items) != len(TASKS):
        return _result("HOLD", "Incomplete queue or unexpected tasks",
                       sha=current_sha, ci=ci_state)
    entries = {}
    for entry in items:
        if (type(entry) is not dict
                or set(entry) != {"id", "status", "evidence_url"}
                or type(entry["id"]) is not str
                or entry["id"] not in TASK_IDS or entry["id"] in entries
                or type(entry["status"]) is not str
                or entry["status"] not in STATES
                or not (entry["evidence_url"] is None or
                        (type(entry["evidence_url"]) is str
                         and entry["evidence_url"].startswith(
                             "https://github.com/mel2003ru-code/OpDB/")))):
            return _result("HOLD", "Unknown, duplicated or malformed task",
                           sha=current_sha, ci=ci_state)
        if (entry["status"] == "DONE") != (entry["evidence_url"] is not None):
            return _result("HOLD", "Completed task must link reviewable evidence",
                           sha=current_sha, ci=ci_state)
        entries[entry["id"]] = entry
    for key, depends, kind in TASKS:
        item = entries.get(key)
        if item is None:
            return _result("HOLD", "Missing allowlisted task",
                           sha=current_sha, ci=ci_state)
        if item["status"] == "DONE":
            continue
        if item["status"] == "BLOCKED":
            return _result("WAIT_FOR_REVIEW", key + " explicitly blocked",
                           task_id=key, task_kind=kind,
                           sha=current_sha, ci=ci_state)
        if any(entries[parent]["status"] != "DONE" for parent in depends):
            return _result("WAIT_FOR_REVIEW", "Prerequisite is not recorded DONE",
                           task_id=key, task_kind=kind,
                           sha=current_sha, ci=ci_state)
        if ci_state == "FAIL_EXECUTED":
            return _result("INVESTIGATE_EXECUTED_CI", "Executed tests failed; do not promote",
                           task_id=key, task_kind=kind,
                           sha=current_sha, ci=ci_state)
        return _result(
            "PROPOSE_REVIEW_ONLY",
            ("CI runner unavailable; continue only reviewable planning"
             if ci_state == "NO_RUNNER" else
             "Next allowlisted engineering step; independent review still required"),
            task_id=key, task_kind=kind, sha=current_sha, ci=ci_state)
    return _result("QUEUE_COMPLETE_UNATTESTED",
                   "All tasks claim DONE; independent reviewers must confirm",
                   sha=current_sha, ci=ci_state)


def _load(path):
    with Path(path).open("rb") as handle:
        payload = handle.read(MAX_JSON_BYTES + 1)
    if len(payload) > MAX_JSON_BYTES:
        raise ValueError("JSON queue exceeds 8192 bytes")

    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError("Duplicate task queue field")
            data[key] = value
        return data

    return json.loads(payload.decode("utf-8", "strict"), object_pairs_hook=unique)


def main(argv=None):
    parser = argparse.ArgumentParser(description="S-009 plan-only work queue")
    parser.add_argument("--queue", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--ci-state", choices=sorted(CI_STATES), default="UNKNOWN")
    parser.add_argument("--output")
    opts = parser.parse_args(argv)
    try:
        decision = next_step(_load(opts.queue),
                             current_sha=opts.expected_sha, ci_state=opts.ci_state)
    except (OSError, ValueError, UnicodeError, TypeError):
        decision = _result("HOLD", "Unreadable or malformed queue")
    payload = json.dumps(decision, sort_keys=True, ensure_ascii=False) + "\n"
    if opts.output:
        Path(opts.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if decision["state"] in (
        "PROPOSE_REVIEW_ONLY", "QUEUE_COMPLETE_UNATTESTED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
