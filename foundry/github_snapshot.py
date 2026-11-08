"""S-009A: deterministic, read-only snapshot of exported GitHub REST metadata.

Inputs MUST be fetched by an independently controlled read-only transport.
This untrusted PR-controlled parser never receives a token, makes HTTP calls,
executes guest code, or attests that the supplied JSON came from GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPO = "mel2003ru-code/OpDB"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MAX_INPUT = 256 * 1024
MAX_RUNS = 30
WORKFLOWS = (
    "Foundry CI — metadata and research tests",
    "Foundry gated research preflight",
    "Foundry Sandbox — actual fixed probe, no untrusted code",
)
PR_NUMBERS = (32, 33, 34)
ISSUE_NUMBERS = (21, 31)
# A successful GitHub job alone is not evidence a required test step ran.
# These names match reviewed workflow definitions at this stage. PR-controlled
# YAML and exported REST JSON remain untrusted; this is only a fail-closed filter.
REQUIRED_CI_STEPS = {
    WORKFLOWS[0]: (
        "Run all repository unit tests, including bounded SQLite research probes",
    ),
    WORKFLOWS[1]: (
        "Exercise negative and synthetic victory cases",
        "Verify agent model policy rejects every paid inference path",
        "Explicitly forbid launch until real authenticated release evidence",
    ),
    WORKFLOWS[2]: (
        "Validate safe planning and synthetic failure guards",
        "Execute ONLY fixed reviewed confinement fixture in a real container",
        "S-008 isolated fixed handoff — tests and actual Docker observation",
    ),
}


def _required_steps_passed(workflow_name, steps):
    """False-green barrier: every required step must have explicit success."""
    required = REQUIRED_CI_STEPS.get(workflow_name)
    if not required or type(steps) is not list or not steps:
        return False
    observed = {}
    for step in steps:
        if (type(step) is not dict or type(step.get("name")) is not str
                or type(step.get("conclusion")) is not str
                or step["name"] in observed
                or step["conclusion"] not in ("success", "skipped")):
            return False
        observed[step["name"]] = step["conclusion"]
    return all(observed.get(name) == "success" for name in required)


def _blocked(reason):
    return {
        "schema_version": 1, "state": "HOLD_SNAPSHOT",
        "reason": reason, "repository": REPO,
        "github_data_attested": False, "ci_attested": False,
        "task_execution_authorized": False,
        "github_write_authorized": False, "automatic_merge_allowed": False,
        "trusted_controller_attested": False, "launch_authorized": False,
    }


def _sha(value):
    return type(value) is str and SHA40.fullmatch(value) is not None


def _canonical(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _items(collection, numbers, kind):
    if type(collection) is not list or len(collection) != len(numbers):
        raise ValueError("Expected exactly %s %s records" % (len(numbers), kind))
    items = {}
    for item in collection:
        if type(item) is not dict or type(item.get("number")) is not int:
            raise ValueError("Malformed " + kind + " record")
        number = item["number"]
        if number not in numbers or number in items:
            raise ValueError("Unexpected or duplicate " + kind + " record")
        items[number] = item
    if set(items) != set(numbers):
        raise ValueError("Missing " + kind + " record")
    return items


def _job_status(run, data):
    """A GitHub conclusion=failure is NOT evidence a test actually executed."""
    if run.get("status") != "completed":
        return "UNKNOWN"
    jobs = data.get("jobs")
    if (type(jobs) is not list or not 1 <= len(jobs) <= 10):
        return "UNKNOWN"
    observed = []
    for job in jobs:
        if type(job) is not dict or type(job.get("run_id")) is not int:
            return "UNKNOWN"
        if job["run_id"] != run["id"]:
            return "UNKNOWN"
        rid, steps, conclusion = job.get("runner_id"), job.get("steps"), job.get("conclusion")
        if type(rid) is not int or type(steps) is not list or len(steps) > 80:
            return "UNKNOWN"
        if rid == 0 and len(steps) == 0 and conclusion == "failure":
            observed.append("NO_RUNNER")
        elif rid > 0 and steps and conclusion == "success":
            # Do not accept setup-only jobs or jobs that skipped the real
            # regressions, even when GitHub reports conclusion=success.
            observed.append(
                "PASS" if _required_steps_passed(run.get("name"), steps)
                else "UNKNOWN"
            )
        elif rid > 0 and steps and conclusion == "failure":
            observed.append("FAIL_EXECUTED")
        else:
            observed.append("UNKNOWN")
    if "FAIL_EXECUTED" in observed and run.get("conclusion") == "failure":
        return "FAIL_EXECUTED"
    if (run.get("conclusion") == "success"
            and all(status == "PASS" for status in observed)):
        return "PASS"
    if (run.get("conclusion") == "failure"
            and all(status == "NO_RUNNER" for status in observed)):
        return "NO_RUNNER"
    return "UNKNOWN"


def snapshot(feed, expected_pr_sha):
    """Select latest exact-HEAD workflow runs and produce advisory coordination.

    No branch protection, review approval, or worker correctness is established.
    A returned CI PASS is only a self-reported parsed *observation*, never an
    independently trusted permission to run code or release anything.
    """
    if not _sha(expected_pr_sha):
        return _blocked("Expected current PR #32 commit SHA is invalid")
    if type(feed) is not dict or set(feed) != {
        "schema_version", "repository", "main", "pulls", "issues", "runs", "jobs"
    }:
        return _blocked("Missing or extra snapshot input fields")
    if type(feed["schema_version"]) is not int or feed["schema_version"] != 1:
        return _blocked("Unsupported schema version")
    if type(feed["repository"]) is not dict or feed["repository"].get("full_name") != REPO:
        return _blocked("GitHub repository identity mismatch")
    main = feed["main"]
    if (type(main) is not dict or main.get("name") != "main"
            or type(main.get("commit")) is not dict
            or not _sha(main["commit"].get("sha"))
            or type(main.get("protected")) is not bool):
        return _blocked("Malformed main branch snapshot")
    main_sha = main["commit"]["sha"]
    try:
        prs = _items(feed["pulls"], PR_NUMBERS, "PR")
        issues = _items(feed["issues"], ISSUE_NUMBERS, "Issue")
    except ValueError as exc:
        return _blocked(str(exc))
    details = {}
    for number in PR_NUMBERS:
        pr = prs[number]
        head = pr.get("head")
        base = pr.get("base")
        if (pr.get("state") != "open" or pr.get("draft") is not True
                or pr.get("merged") is not False
                or type(head) is not dict or not _sha(head.get("sha"))
                or type(head.get("ref")) is not str
                or type(base) is not dict or not _sha(base.get("sha"))
                or type(base.get("ref")) is not str):
            return _blocked("PR #%d not an open, unmerged draft with exact SHAs" % number)
        details[number] = {
            "head_sha": head["sha"], "head_ref": head["ref"],
            "base_sha": base["sha"], "base_ref": base["ref"],
        }
    if details[32]["head_sha"] != expected_pr_sha:
        return _blocked("PR #32 changed since expected HEAD was pinned")
    if details[32]["base_ref"] != "main" or details[32]["base_sha"] != main_sha:
        return _blocked("PR #32 base does not match exported main")
    if details[33]["base_ref"] != "main" or details[33]["base_sha"] != main_sha:
        return _blocked("PR #33 base does not match exported main")
    if (details[34]["base_ref"] != details[33]["head_ref"]
            or details[34]["base_sha"] != details[33]["head_sha"]):
        return _blocked("Stacked Quality PR #34 is not based on current Core #33")
    for issue in ISSUE_NUMBERS:
        if (issues[issue].get("state") not in ("open", "closed")
                or "pull_request" in issues[issue]):
            return _blocked("Malformed Issue #%d" % issue)
    if issues[31]["state"] != "open":
        return _blocked("Foundry Issue #31 is not open")
    runs = feed["runs"]
    jobs = feed["jobs"]
    if (type(runs) is not list or not 0 <= len(runs) <= MAX_RUNS
            or type(jobs) is not dict or len(jobs) > MAX_RUNS):
        return _blocked("Malformed or oversized workflow metadata")
    selected = {}
    seen_run_ids = set()
    for run in runs:
        if (type(run) is not dict or type(run.get("id")) is not int
                or run["id"] <= 0 or run["id"] in seen_run_ids
                or not _sha(run.get("head_sha"))
                or type(run.get("name")) is not str):
            return _blocked("Duplicate or malformed workflow run")
        seen_run_ids.add(run["id"])
        if run["head_sha"] != expected_pr_sha or run["name"] not in WORKFLOWS:
            continue
        existing = selected.get(run["name"])
        if existing is None or run["id"] > existing["id"]:
            selected[run["name"]] = run
    statuses = {}
    ids = {}
    for name in WORKFLOWS:
        run = selected.get(name)
        if run is None:
            statuses[name] = "UNKNOWN"
            ids[name] = None
        else:
            statuses[name] = _job_status(run, {"jobs": jobs.get(str(run["id"]))})
            ids[name] = run["id"]
    observations = set(statuses.values())
    if "FAIL_EXECUTED" in observations:
        ci_state = "FAIL_EXECUTED"
    elif observations == {"PASS"}:
        ci_state = "PASS"
    elif observations == {"NO_RUNNER"}:
        ci_state = "NO_RUNNER"
    else:
        ci_state = "UNKNOWN"
    try:
        digest = hashlib.sha256(_canonical(feed)).hexdigest()
    except (TypeError, ValueError, OverflowError):
        return _blocked("Noncanonical or malformed JSON values")
    return {
        "schema_version": 1,
        "state": "READ_ONLY_SNAPSHOT",
        "repository": REPO,
        "source_sha": expected_pr_sha,
        "main_sha": main_sha,
        "main_protected_reported": main["protected"],
        "draft_pr_heads": {str(n): details[n]["head_sha"] for n in PR_NUMBERS},
        "issue_21_reported_open": issues[21]["state"] == "open",
        "issue_31_reported_open": True,
        "lens_blocked": True,  # Unauthenticated snapshot can never close P0.
        "ci_state": ci_state,
        "workflow_observations": statuses,
        "workflow_run_ids": ids,
        "snapshot_payload_sha256": digest,
        "digest_is_authentication": False,
        "github_data_attested": False,
        "ci_attested": False,
        "task_execution_authorized": False,
        "github_write_authorized": False,
        "automatic_merge_allowed": False,
        "trusted_controller_attested": False,
        "launch_authorized": False,
        "next_step": (
            "Investigate actual executed CI failure before changes"
            if ci_state == "FAIL_EXECUTED"
            else "Read current FND-009 worklist and propose next reviewable draft change"
        ),
        "scope": "Read-only exported GitHub metadata; untrusted, advisory only",
    }


def _load(path):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("GitHub snapshot exceeds 256 KiB")

    def pairs_unique(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("Duplicate GitHub JSON key")
            seen[key] = value
        return seen

    return json.loads(raw.decode("utf-8", "strict"),
                      object_pairs_hook=pairs_unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError("Nonfinite GitHub JSON value")))


def main(argv=None):
    ap = argparse.ArgumentParser(description="S-009A advisory GitHub snapshot")
    ap.add_argument("--input", required=True, help="exported, untrusted GitHub REST JSON")
    ap.add_argument("--expected-sha", required=True)
    ap.add_argument("--output")
    args = ap.parse_args(argv)
    try:
        result = snapshot(_load(args.input), args.expected_sha)
    except (OSError, UnicodeError, TypeError, ValueError):
        result = _blocked("Cannot load bounded exported GitHub snapshot")
    payload = json.dumps(result, sort_keys=True, ensure_ascii=False) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if result["state"] == "READ_ONLY_SNAPSHOT" else 2


if __name__ == "__main__":
    raise SystemExit(main())
