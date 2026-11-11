"""S-009B: append-only, review-only task receipts for Foundry's existing draft PR.

GitHub (not this module) persists ledger JSON through its contents API with
an expected blob SHA. This PR-controlled hash chain detects accidental edits,
not a malicious rewriter: it is neither an independent trust root nor an
authorization for any code execution, merge, model use or deployment.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path

from foundry.automation_queue import TASKS, REPO

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_URL = re.compile(
    r"https://github\.com/mel2003ru-code/OpDB/commit/([0-9a-f]{40})\Z"
)
ZERO = "0" * 64
MAX_EVENTS = 12
MAX_BYTES = 16 * 1024
KNOWN = tuple(x[0] for x in TASKS)
DEPENDENCIES = {task: tuple(parents) for task, parents, _ in TASKS}
# A was completed in a previous, verified-to-exist draft commit before
# the ledger existed. This imports a *reviewable artefact*, not a CI verdict.
HISTORIC_A_COMMIT = "b2bf62645528b1fa880cb1238a08064f27b9d638"
HISTORIC_A_URL = (
    "https://github.com/mel2003ru-code/OpDB/commit/" + HISTORIC_A_COMMIT
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      allow_nan=False, separators=(",", ":")).encode("ascii")


def empty_ledger():
    return {"schema_version": 1, "repository": REPO,
            "issue_number": 31, "pr_number": 32,
            "head_sha256": ZERO, "events": []}


def _valid_url(url):
    return type(url) is str and COMMIT_URL.fullmatch(url) is not None


def _check_event(event, previous, last_state, expected_seq):
    if (type(event) is not dict or set(event) != {
            "seq", "task_id", "state", "observed_sha", "evidence_url",
            "prev_sha256", "event_sha256"}):
        raise ValueError("Invalid event shape")
    task, state = event["task_id"], event["state"]
    if (type(event["seq"]) is not int or event["seq"] != expected_seq
            or type(task) is not str or task not in KNOWN
            or type(state) is not str or state not in ("CLAIMED", "DONE", "BLOCKED")
            or type(event["observed_sha"]) is not str
            or SHA40.fullmatch(event["observed_sha"]) is None
            or event["prev_sha256"] != previous
            or type(event["event_sha256"]) is not str
            or SHA256.fullmatch(event["event_sha256"]) is None):
        raise ValueError("Invalid task, event sequence, SHA or previous digest")
    evidence = event["evidence_url"]
    if state == "DONE":
        if not _valid_url(evidence):
            raise ValueError("DONE must point to exact repository commit")
    elif evidence is not None:
        raise ValueError("Non-DONE event cannot claim evidence")
    prior = last_state.get(task)
    if prior is None:
        if state == "DONE" and not (
                task == "FND-009A" and expected_seq == 1
                and evidence == HISTORIC_A_URL
                and event["observed_sha"] == HISTORIC_A_COMMIT):
            raise ValueError("Only exact historic 009A reviewable code can be imported")
        if state not in ("CLAIMED", "DONE"):
            raise ValueError("Task cannot start as blocked")
        if any(last_state.get(dep) != "DONE" for dep in DEPENDENCIES[task]):
            raise ValueError("Unmet predecessor")
    elif prior != "CLAIMED" or state not in ("DONE", "BLOCKED"):
        raise ValueError("Invalid transition or repeated task")
    payload = {k: v for k, v in event.items() if k != "event_sha256"}
    if hashlib.sha256(_canonical(payload)).hexdigest() != event["event_sha256"]:
        raise ValueError("Event digest mismatch")
    last_state[task] = state
    return event["event_sha256"]


def validate(ledger):
    """Raise on corruption. Return last observed state by allowlisted task."""
    if (type(ledger) is not dict or set(ledger) != {
            "schema_version", "repository", "issue_number", "pr_number",
            "head_sha256", "events"}
            or type(ledger["schema_version"]) is not int
            or ledger["schema_version"] != 1
            or ledger["repository"] != REPO
            or type(ledger["issue_number"]) is not int
            or ledger["issue_number"] != 31
            or type(ledger["pr_number"]) is not int
            or ledger["pr_number"] != 32
            or type(ledger["head_sha256"]) is not str
            or SHA256.fullmatch(ledger["head_sha256"]) is None):
        raise ValueError("Invalid ledger envelope")
    events = ledger["events"]
    if type(events) is not list or len(events) > MAX_EVENTS:
        raise ValueError("Invalid ledger event count")
    prior, state = ZERO, {}
    for index, event in enumerate(events, 1):
        prior = _check_event(event, prior, state, index)
    if prior != ledger["head_sha256"]:
        raise ValueError("Ledger head digest mismatch")
    if len(_canonical(ledger)) > MAX_BYTES:
        raise ValueError("Ledger exceeds 16 KiB")
    return state


def _decision(state, reason, task_id=None, *, changed=False):
    return {
        "schema_version": 1, "state": state, "reason": reason,
        "task_id": task_id, "ledger_changed": changed,
        "receipt_attested": False, "hash_chain_is_signature": False,
        "github_write_authorized": False, "worker_execution_authorized": False,
        "automatic_merge_allowed": False, "production_allowed": False,
        "launch_authorized": False, "human_review_required": True,
    }


def record(ledger, *, task_id, action, observed_sha, evidence_url=None):
    """Return (decision, new ledger). Never mutate the source object.

    CLAIM reserves work until an explicit COMPLETE or BLOCK. No automatic
    lease expiry or retry: crashes cause a reviewable hold, not duplicate work.
    """
    try:
        states = validate(ledger)
    except (TypeError, ValueError, OverflowError) as exc:
        return _decision("HOLD_INVALID", str(exc), task_id), None
    if (type(task_id) is not str or task_id not in KNOWN
            or type(action) is not str
            or action not in ("CLAIM", "COMPLETE", "BLOCK", "IMPORT_A")
            or type(observed_sha) is not str
            or SHA40.fullmatch(observed_sha) is None):
        return _decision("HOLD_INVALID", "Task/action/commit pin invalid", task_id), None
    if action in ("CLAIM", "BLOCK") and evidence_url is not None:
        return _decision("HOLD_INVALID", "Action cannot contain evidence", task_id), None
    if action in ("COMPLETE", "IMPORT_A") and not _valid_url(evidence_url):
        return _decision("HOLD_INVALID", "Exact GitHub commit link required", task_id), None
    prior = states.get(task_id)
    if prior == "DONE":
        old = next(e for e in ledger["events"] if
                   e["task_id"] == task_id and e["state"] == "DONE")
        if action in ("COMPLETE", "IMPORT_A") and old["evidence_url"] != evidence_url:
            return _decision("HOLD_CONFLICT", "Completed task evidence differs", task_id), None
        return _decision("ALREADY_DONE", "Completed task cannot be repeated", task_id), None
    if prior == "BLOCKED":
        return _decision("HOLD_BLOCKED", "Task blocked; manual review required", task_id), None
    if action == "CLAIM":
        if prior == "CLAIMED":
            return _decision("ALREADY_CLAIMED", "Existing claim requires review", task_id), None
        if any(states.get(dep) != "DONE" for dep in DEPENDENCIES[task_id]):
            return _decision("HOLD_DEPENDENCY", "Previous task has not completed", task_id), None
        desired = "CLAIMED"
    elif action == "IMPORT_A":
        if (task_id != "FND-009A" or prior is not None
                or ledger["events"] or observed_sha != HISTORIC_A_COMMIT
                or evidence_url != HISTORIC_A_URL):
            return _decision("HOLD_INVALID", "Historic import pin mismatch", task_id), None
        desired = "DONE"
    else:
        if prior != "CLAIMED":
            return _decision("HOLD_NOT_CLAIMED", "Explicit claim required first", task_id), None
        desired = "DONE" if action == "COMPLETE" else "BLOCKED"
    new = copy.deepcopy(ledger)
    event = {
        "seq": len(new["events"]) + 1, "task_id": task_id,
        "state": desired, "observed_sha": observed_sha,
        "evidence_url": evidence_url if desired == "DONE" else None,
        "prev_sha256": new["head_sha256"],
    }
    event["event_sha256"] = hashlib.sha256(_canonical(event)).hexdigest()
    new["events"].append(event)
    new["head_sha256"] = event["event_sha256"]
    try:
        validate(new)
    except (TypeError, ValueError, OverflowError) as exc:
        return _decision("HOLD_INVALID", str(exc), task_id), None
    return _decision("RECORDED", "Review-only event appended", task_id, changed=True), new


def reconcile(ledger, queue):
    """Worklist and receipt file must agree before advancing the scheduler."""
    try:
        states = validate(ledger)
        if (type(queue) is not dict or set(queue) != {
                "schema_version", "repository", "pr_number", "issue_number",
                "security_blocker", "items"}
                or type(queue["schema_version"]) is not int or queue["schema_version"] != 1
                or queue["repository"] != REPO
                or type(queue["pr_number"]) is not int or queue["pr_number"] != 32
                or type(queue["issue_number"]) is not int or queue["issue_number"] != 31
                or type(queue["security_blocker"]) is not int or queue["security_blocker"] != 21
                or type(queue["items"]) is not list):
            raise ValueError("Missing or untrusted worklist header")
        items = queue["items"]
        if (len(items) != len(KNOWN) or
                {e.get("id") for e in items if type(e) is dict} != set(KNOWN)):
            raise ValueError("Unknown worklist entries")
        for item in items:
            task = item["id"]
            status = item.get("status")
            proof = item.get("evidence_url")
            last = states.get(task)
            if last == "DONE":
                event = next(e for e in ledger["events"] if e["task_id"] == task and
                             e["state"] == "DONE")
                if status != "DONE" or proof != event["evidence_url"]:
                    raise ValueError("DONE event/worklist mismatch: " + task)
            elif last == "BLOCKED":
                if status != "BLOCKED" or proof is not None:
                    raise ValueError("Blocked event/worklist mismatch: " + task)
            elif status != "READY" or proof is not None:
                raise ValueError("Uncompleted worklist item mismatch: " + task)
        return _decision("CONSISTENT_ADVISORY", "Ledger and queue agree")
    except (TypeError, ValueError, OverflowError) as exc:
        return _decision("HOLD_SYNC", str(exc))


def load(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Ledger exceeds 16 KiB")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate ledger JSON key")
            result[key] = value
        return result
    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("Nonfinite JSON value")))


def main(argv=None):
    parser = argparse.ArgumentParser(description="S-009B draft-only receipt ledger")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--action", choices=("CLAIM", "COMPLETE", "BLOCK", "IMPORT_A"), required=True)
    parser.add_argument("--observed-sha", required=True)
    parser.add_argument("--evidence-url")
    parser.add_argument("--output", required=True, help="new local JSON file; NEVER pushes GitHub")
    args = parser.parse_args(argv)
    try:
        if Path(args.ledger).resolve() == Path(args.output).resolve():
            raise ValueError("Output must differ from input; use GitHub blob CAS separately")
        decision, new = record(load(args.ledger), task_id=args.task_id,
                               action=args.action, observed_sha=args.observed_sha,
                               evidence_url=args.evidence_url)
        if new is not None:
            with Path(args.output).open("x", encoding="utf-8") as dest:
                dest.write(json.dumps(new, sort_keys=True, indent=2) + "\n")
    except (OSError, ValueError, UnicodeError) as exc:
        decision = _decision("HOLD_INVALID", type(exc).__name__ + ": " + str(exc))
    print(json.dumps(decision, sort_keys=True, ensure_ascii=False))
    return 0 if decision["state"] == "RECORDED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
