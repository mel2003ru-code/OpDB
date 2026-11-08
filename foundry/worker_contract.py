"""Foundry Controller ↔ Worker data contract 0.1; OFFLINE DEMO ONLY.

No model, subprocess, network, GitHub write, or code execution. Three separate
CLI phases exchange strictly bounded JSON. This is NOT an independently trusted
controller, authenticated IPC, or secure operating-system worker. The worker
reply is UNTRUSTED DATA and may be quarantined only for review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from .agent_executor import validate_task
from .model_gate import evaluate, offline_policy
from .patch_admission import admit as admit_patch

_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_PATH = "foundry/fixtures/calculator.py"
_MAX_MESSAGE = 16 * 1024
_MAX_CODE = 4096
_FIXED_BEFORE = "    return left - right\n"
_FIXED_AFTER = "    return left + right\n"
_REQUEST_KEYS = frozenset({
    "schema_version", "source_sha", "task_key", "issue_number",
    "operation", "allowed_path", "max_candidate_bytes", "max_attempts",
    "max_model_requests", "max_total_tokens", "max_cost_micro_usd",
    "network_allowed", "shell_allowed", "execution_allowed",
    "github_write_allowed",
})


def _block(reason):
    return {
        "state": "BLOCKED",
        "reason": reason,
        "candidate_diff": None,
        "worker_reply_executed": False,
        "model_invoked": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
    }


def _request_for(sha):
    return {
        "schema_version": 1,
        "source_sha": sha,
        "task_key": "demo-add-v1",
        "issue_number": 31,
        "operation": "PROPOSE_TEXT_ONLY",
        "allowed_path": _PATH,
        "max_candidate_bytes": _MAX_CODE,
        "max_attempts": 1,
        "max_model_requests": 0,
        "max_total_tokens": 0,
        "max_cost_micro_usd": 0,
        "network_allowed": False,
        "shell_allowed": False,
        "execution_allowed": False,
        "github_write_allowed": False,
    }


def prepare(task, checkout_sha):
    """Controller allows ONLY the reviewed synthetic Issue-31 task envelope."""
    issue = validate_task(task, checkout_sha)
    if issue is not None:
        return _block("Rejected issue task: " + issue)
    model = evaluate(offline_policy(checkout_sha), checkout_sha)
    if model["state"] != "OFFLINE_MOCK_POLICY_ONLY":
        return _block("Zero-cost model policy rejected")
    return {
        "state": "DATA_HANDOFF_READY",
        "request": _request_for(checkout_sha),
        "task_text_used_as_instructions": False,
        "worker_reply_executed": False,
        "model_invoked": False,
        "github_write_allowed": False,
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "launch_authorized": False,
        "limitation": "Offline data contract; not authenticated IPC or OS process isolation",
    }


def _valid_request(request, checkout_sha):
    if (type(checkout_sha) is not str or _SHA.fullmatch(checkout_sha) is None
            or type(request) is not dict or set(request) != _REQUEST_KEYS):
        return False
    expected = _request_for(checkout_sha)
    # Python bool is an int subclass: True == 1 and 0 == False, so a plain
    # dict equality is NOT a schema/type check on untrusted JSON.
    return all(
        type(request[key]) is type(value) and request[key] == value
        for key, value in expected.items()
    )


def mock_reply(request, checkout_sha, checkout_root):
    """Zero-cost deterministic fixture reply. Never execute source content."""
    if not _valid_request(request, checkout_sha):
        return None, "Request contents not approved by controller"
    # Fixed relative file only; caller/worker cannot select another path.
    source = Path(checkout_root) / _PATH
    try:
        if (source.is_symlink() or not source.is_file()
                or any(p.is_symlink() for p in source.parents)):
            return None, "Fixture unavailable or symlinked"
        with source.open("rb") as f:
            raw = f.read(_MAX_CODE + 1)
        if len(raw) > _MAX_CODE:
            return None, "Fixture too large"
        old = raw.decode("utf-8", "strict")
    except (OSError, UnicodeError):
        return None, "Fixture unavailable or invalid"
    if old.count(_FIXED_BEFORE) != 1 or _FIXED_AFTER in old:
        return None, "Reviewed synthetic arithmetic fixture changed"
    changed = old.replace(_FIXED_BEFORE, _FIXED_AFTER)
    reply = {
        "schema_version": 1,
        "source_sha": checkout_sha,
        "task_key": "demo-add-v1",
        "issue_number": 31,
        "path": _PATH,
        "original_sha256": hashlib.sha256(raw).hexdigest(),
        "candidate_sha256": hashlib.sha256(changed.encode("utf-8")).hexdigest(),
        "candidate_text": changed,
    }
    return reply, None


def review(request, reply, checkout_sha, checkout_root):
    """Controller *quarantines*, never executes or applies a worker response."""
    if not _valid_request(request, checkout_sha):
        return _block("Worker request changed or source SHA mismatch")
    result = admit_patch(reply, checkout_sha, checkout_root)
    if result["state"] != "QUARANTINED_FOR_REVIEW":
        return _block("Untrusted worker reply rejected: " +
                      "; ".join(result["reasons"]))
    return {
        "state": "REVIEW_ONLY_PATCH",
        "candidate_diff": result["diff"],
        "candidate_diff_sha256": result["diff_sha256"],
        "candidate_sha256": result["candidate_sha256"],
        "worker_reply_executed": False,
        "model_invoked": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
        "human_review_required": True,
        "limitation": "Text patch is UNTRUSTED. SHA is content integrity, NOT authenticity",
    }


def _load(path):
    # Keep controller input bounds independent of JSON parser behavior.
    with Path(path).open("rb") as f:
        raw = f.read(_MAX_MESSAGE + 1)
    if len(raw) > _MAX_MESSAGE:
        raise ValueError("Handoff message exceeds 16 KiB")
    return json.loads(raw.decode("utf-8", "strict"))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline data handoff, no execution")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--offline-mock", action="store_true")
    group.add_argument("--review", action="store_true")
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--task-file")
    parser.add_argument("--request-file")
    parser.add_argument("--reply-file")
    parser.add_argument("--checkout", default=".")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    artifact = None
    try:
        if args.prepare:
            if args.request_file or args.reply_file or not args.task_file:
                report = _block("Prepare requires only task-file")
            else:
                report = prepare(_load(args.task_file), args.expected_sha)
                if report["state"] == "DATA_HANDOFF_READY":
                    artifact = report["request"]
        elif args.offline_mock:
            if args.task_file or args.reply_file or not args.request_file:
                report = _block("Mock worker requires only request-file")
            else:
                artifact, error = mock_reply(
                    _load(args.request_file), args.expected_sha, args.checkout)
                report = _block(error) if error else {
                    "state": "OFFLINE_DATA_REPLY_ONLY",
                    "worker_reply_executed": False,
                    "model_invoked": False,
                    "github_write_allowed": False,
                    "automatic_merge_allowed": False,
                    "production_allowed": False,
                    "launch_authorized": False,
                }
        else:
            if args.task_file or not args.request_file or not args.reply_file:
                report = _block("Review requires request and reply JSON")
            else:
                report = review(_load(args.request_file), _load(args.reply_file),
                                args.expected_sha, args.checkout)
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        report = _block("Cannot process bounded data envelope: " +
                        type(exc).__name__)
    if artifact is not None and args.output:
        Path(args.output).write_text(json.dumps(artifact, sort_keys=True) + "\n",
                                     encoding="utf-8")
    elif args.output and args.review:
        Path(args.output).write_text(json.dumps(report, sort_keys=True) + "\n",
                                     encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["state"] in (
        "DATA_HANDOFF_READY", "OFFLINE_DATA_REPLY_ONLY", "REVIEW_ONLY_PATCH"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
