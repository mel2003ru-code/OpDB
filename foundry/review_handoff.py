"""FND-009C — bounded, READ-ONLY handoff for independent Safety/Quality review.

Consumes untrusted 009A snapshot and 009B task receipts. It NEVER requests
GitHub approval, posts comments, contacts reviewers, calls models or executes
candidate code. The output is a *request for independent review*, NOT review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from foundry.automation_ledger import validate, reconcile, HISTORIC_A_URL
from foundry.automation_queue import REPO, CI_STATES
from foundry.github_snapshot import WORKFLOWS

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
REPO_URL = "https://github.com/" + REPO
MAX_SNAPSHOT = 64 * 1024
MAX_LEDGER = 16 * 1024
MAX_QUEUE = 8192
MAX_OUTPUT = 24 * 1024


def _safe_result(state, reasons):
    return {
        "schema_version": 1,
        "state": state,
        "reasons": reasons,
        "independent_safety_approved": False,
        "independent_quality_approved": False,
        "github_data_attested": False,
        "reviewer_contacted": False,
        "reviewer_approval_attested": False,
        "ci_attested": False,
        "trusted_controller_attested": False,
        "worker_execution_authorized": False,
        "github_write_authorized": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
    }


def handoff(snapshot, ledger, worklist, *, current_sha):
    """Return request-for-review manifest, never an approval.

    All supplied JSON is editable PR data. Even syntactically valid values do
    not establish independent attestation; link provenance must be rechecked
    against the real GitHub API by a separate reviewer.
    """
    if type(current_sha) is not str or SHA40.fullmatch(current_sha) is None:
        return _safe_result("HOLD", ["Current PR SHA missing or malformed"])
    try:
        states = validate(ledger)
        ledger_result = reconcile(ledger, worklist)
    except (TypeError, ValueError, OverflowError):
        return _safe_result("HOLD", ["Ledger is malformed or inconsistent"])
    if ledger_result["state"] != "CONSISTENT_ADVISORY":
        return _safe_result("HOLD", ["Ledger/worklist divergence: manual reconciliation"])
    if states.get("FND-009A") != "DONE" or states.get("FND-009B") != "DONE":
        return _safe_result("HOLD", ["Prior engineering stages have no recorded completion"])
    if states.get("FND-009C") not in ("CLAIMED", "DONE"):
        return _safe_result("HOLD", ["FND-009C must be claimed before preparing handoff"])
    if (type(snapshot) is not dict
            or snapshot.get("state") != "READ_ONLY_SNAPSHOT"
            or snapshot.get("schema_version") != 1
            or snapshot.get("repository") != REPO
            or snapshot.get("source_sha") != current_sha
            or snapshot.get("github_data_attested") is not False
            or snapshot.get("ci_attested") is not False
            or snapshot.get("launch_authorized") is not False):
        return _safe_result("HOLD", ["Fresh, unauthenticated S-009A snapshot required"])
    heads = snapshot.get("draft_pr_heads")
    runs = snapshot.get("workflow_run_ids")
    observed = snapshot.get("workflow_observations")
    ci = snapshot.get("ci_state")
    if (type(heads) is not dict or set(heads) != {"32", "33", "34"}
            or heads["32"] != current_sha
            or any(type(sha) is not str or SHA40.fullmatch(sha) is None
                   for sha in heads.values())
            or type(ci) is not str or ci not in CI_STATES
            or type(snapshot.get("main_sha")) is not str
            or SHA40.fullmatch(snapshot["main_sha"]) is None
            or type(runs) is not dict or type(observed) is not dict
            or set(runs) != set(WORKFLOWS) or set(observed) != set(WORKFLOWS)):
        return _safe_result("HOLD", ["Incomplete PR-head or workflow provenance"])
    for name, number in runs.items():
        if (type(name) is not str or not name.startswith("Foundry ")
                or (number is not None and (type(number) is not int or number <= 0))
                or observed[name] not in CI_STATES):
            return _safe_result("HOLD", ["Malformed workflow reference"])
    statuses = set(observed.values())
    inferred = ("FAIL_EXECUTED" if "FAIL_EXECUTED" in statuses else
                "PASS" if statuses == {"PASS"} else
                "NO_RUNNER" if statuses == {"NO_RUNNER"} else "UNKNOWN")
    if inferred != ci:
        return _safe_result("HOLD", ["Workflow observations contradict CI summary"])
    if (snapshot.get("issue_31_reported_open") is not True
            or type(snapshot.get("issue_21_reported_open")) is not bool
            or snapshot.get("lens_blocked") is not True):
        return _safe_result("HOLD", ["Foundry tracking or P0 block not established"])
    proof = {}
    for task in ("FND-009A", "FND-009B"):
        done = next(e for e in ledger["events"] if e["task_id"] == task
                    and e["state"] == "DONE")
        proof[task] = done["evidence_url"]
    if proof["FND-009A"] != HISTORIC_A_URL:
        return _safe_result("HOLD", ["Historical task receipt changed"])
    refs = {name: (
        REPO_URL + "/actions/runs/" + str(number) if number is not None else None
    ) for name, number in runs.items()}
    notes = [
        "No independent Safety/Quality approval is present in this manifest",
        "PR-controlled metadata and SHA256 are not trusted provenance",
        "P0 #21 blocks Lens regardless of the issue status reported here",
    ]
    if ci == "NO_RUNNER":
        notes.append("CI DID NOT EXECUTE: runner_id=0, steps=[] must be rechecked")
    elif ci == "FAIL_EXECUTED":
        notes.append("Executed CI failed: investigate before promoting any changes")
    else:
        notes.append("Reported CI observation is unauthenticated, never a release gate")
    result = {
        **_safe_result("REQUEST_INDEPENDENT_REVIEW", notes),
        "repository": REPO,
        "target_pr": 32,
        "target_sha": current_sha,
        "main_sha": snapshot.get("main_sha"),
        "related_pr_heads": heads,
        "issue_21_reported_open": snapshot["issue_21_reported_open"],
        "p0_21_remains_release_blocker": True,
        "ci_observation": ci,
        "workflow_observations": observed,
        "workflow_run_urls": refs,
        "worklist_status": "FND-009C " + states["FND-009C"],
        "reviewable_code_evidence": proof,
        "review_requests": [
            {"reviewer_role": "INDEPENDENT_SAFETY",
             "issue": 2, "state": "PENDING_EXTERNAL_REVIEW",
             "must_examine": [
                 "P0 #21: verify immutable source-only fallback and external writer behavior",
                 "Controller and GitHub permissions must be outside PR-controlled code",
                 "No worker secrets, privileged Docker host execution or unbounded resource use",
                 "Ledger/queue GitHub CAS and interrupted two-file update",
             ]},
            {"reviewer_role": "INDEPENDENT_QUALITY",
             "issue": 4, "state": "PENDING_EXTERNAL_REVIEW",
             "must_examine": [
                 "Reproduce exact HEAD tests on an allocated runner independently",
                 "Verify 009A/009B/009C evidence and false-green CI classification",
                 "Verify duplicate CLAIMED/DONE and crash/resume do not rerun work",
                 "Verify stacked Core PR #34 is based on exact PR #33 HEAD",
             ]},
        ],
        "next_phase": "External review and observed scheduled end-to-end cycle",
        "handoff_published": False,
        "human_review_required": True,
        "source_only_required": True,
    }
    encoded = json.dumps(result, sort_keys=True, ensure_ascii=True,
                         allow_nan=False, separators=(",", ":")).encode("ascii")
    if len(encoded) > MAX_OUTPUT:
        return _safe_result("HOLD", ["Handoff exceeds 24 KiB"])
    result["manifest_sha256"] = hashlib.sha256(encoded).hexdigest()
    result["digest_is_authentication"] = False
    return result


def _load(path, limit):
    with Path(path).open("rb") as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Input exceeds handoff byte limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field")
            result[key] = value
        return result

    return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(
                          ValueError("Nonfinite JSON")))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan-only independent-review handoff")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--worklist", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        paths = [Path(args.snapshot), Path(args.ledger), Path(args.worklist)]
        if Path(args.output).resolve() in [p.resolve() for p in paths]:
            raise ValueError("Cannot overwrite source evidence")
        result = handoff(_load(paths[0], MAX_SNAPSHOT),
                         _load(paths[1], MAX_LEDGER),
                         _load(paths[2], MAX_QUEUE),
                         current_sha=args.expected_sha)
        if result["state"] == "REQUEST_INDEPENDENT_REVIEW":
            with Path(args.output).open("x", encoding="utf-8") as dest:
                dest.write(json.dumps(result, sort_keys=True, indent=2) + "\n")
    except (TypeError, ValueError, OSError, UnicodeError):
        result = _safe_result("HOLD", ["Cannot read or write bounded handoff inputs"])
    print(json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["state"] == "REQUEST_INDEPENDENT_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
