"""Read-only coordinator for one bounded OpDB research iteration.

Consumes research.cycle JSON and produces exactly one *proposed next step*.
No GitHub writes, code generation, model inference, merge, deployment or production
access. Current SQLite/Python probes are NOT evidence of a working OpDB DBMS.
"""
import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

TRACK_ISSUES = {
    **{f"R{i:02d}": i + 6 for i in range(1, 11)},
    "TASK-001": 2, "TASK-002": 3, "TASK-003": 4,
}
MODELS = {"R04", "R05", "R09"}
PRIORITY = ("TASK-001", "TASK-002", "TASK-003",
            "R06", "R07", "R03", "R10", "R01", "R02",
            "R04", "R05", "R08", "R09")
SHA = re.compile(r"[a-fA-F0-9]{40}\Z")


def _make(state, reasons, *, sha=None, seed=None, issue=31, action=None):
    """Every state blocks mutation. Do not turn advisory plans into authorization."""
    return {
        "schema_version": 1,
        "state": state,
        "source_sha": sha,
        "seed": seed,
        "next_issue": issue,
        "proposed_next_action": action or "Stop this iteration and inspect evidence",
        "reasons": reasons,
        "safety_blocker_issue": 21,
        "research_only": True,
        "source_only_required": True,
        "trusted_engine_verified": False,
        "automated_code_change_allowed": False,
        "automatic_merge_allowed": False,
        "staging_deploy_allowed": False,
        "production_deploy_allowed": False,
        "pause_for_superiority_confirmed": False,
        "scope": "Research routing, NOT verified OpDB nor an autonomous coding agent",
    }


def _invalid(why):
    return _make("HOLD_EVIDENCE", [why])


def _valid_sha(value):
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def plan(report, expected_sha):
    """Return a conservative deterministic next-step decision."""
    if not _valid_sha(expected_sha):
        return _invalid("Expected GitHub commit SHA missing or malformed")
    if not isinstance(report, dict):
        return _invalid("Research-cycle report missing or not an object")
    source_sha = report.get("repository_sha")
    if not _valid_sha(source_sha) or source_sha.lower() != expected_sha.lower():
        return _invalid("Research report commit does not match the checked-out SHA")
    seed = report.get("seed")
    if type(seed) is not int or seed < 0:
        return _invalid("Research-cycle seed is missing or invalid")
    started = report.get("start_utc")
    if not isinstance(started, str):
        return _invalid("No UTC timestamp in the research report")
    try:
        timestamp = dt.datetime.fromisoformat(started)
        if timestamp.tzinfo is None or timestamp.utcoffset() != dt.timedelta(0):
            return _invalid("Research timestamp must contain UTC timezone")
    except ValueError:
        return _invalid("Malformed research timestamp")
    if not all(isinstance(report.get(name), str) and report[name].strip()
               for name in ("python", "sqlite", "platform")):
        return _invalid("Research environment is unrecorded")

    try:
        digest = hashlib.sha256(json.dumps(
            report, sort_keys=True, ensure_ascii=False, allow_nan=False,
            separators=(",", ":")
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        return _invalid("Research JSON contains non-canonical data")

    results = report.get("results")
    if not isinstance(results, list) or len(results) != len(TRACK_ISSUES):
        return _invalid("All 13 tracks must be present exactly once")
    found = {}
    for record in results:
        if not isinstance(record, dict):
            return _invalid("Malformed workstream record")
        track = record.get("track")
        if type(track) is not str or track not in TRACK_ISSUES or track in found:
            return _invalid("Unknown or duplicate workstream")
        issue = record.get("issue")
        if type(issue) is not int or issue != TRACK_ISSUES[track]:
            return _invalid("Workstream/issue mapping mismatch")
        status = record.get("status")
        allowed = (
            {"NOT_CONFIGURED", "NOT_VERIFIED", "FAIL", "IMPLEMENTATION_SMOKE_PASS"}
            if track.startswith("TASK-") else
            {"FAIL", "MODEL_SMOKE_PASS" if track in MODELS else "SQLITE_SMOKE_PASS"}
        )
        if status not in allowed:
            return _invalid("Unknown/inconsistent status for " + track)
        if status == "FAIL" and not (
            isinstance(record.get("error"), str) and record["error"].strip()
        ):
            return _invalid("Failed workstream must contain failure evidence")
        found[track] = record

    controls = report.get("negative_controls")
    if not isinstance(controls, list) or len(controls) != 1:
        return _invalid("Expected one independent negative-control record")
    check = controls[0]
    if not isinstance(check, dict):
        return _invalid("Malformed adversarial control record")
    if (check.get("status") != "EXPECTED_COUNTEREXAMPLE"
            or check.get("external_untracked_stale") is not True
            or check.get("forged_journal_mismatch") is not True
            or check.get("source_integrity") != "ok"):
        return _make(
            "ESCALATE_SAFETY",
            ["P0 negative control failed or did not reproduce the expected unsafe behavior",
             "This fixture is deliberately vulnerable; never interpret it as Proof Gate PASS"],
            sha=source_sha, seed=seed, issue=21,
            action="Investigate the adversarial test fixture and hold all Lens-related claims",
        )
    for track in PRIORITY:
        if found[track]["status"] == "FAIL":
            return _make(
                "INVESTIGATE_FAILED_TRACK",
                ["Workstream " + track + " reported FAIL",
                 "Independent reproduction required before claiming a fix",
                 "Adversarial P0 counterexample is expected, not a successful actual Safety test",
                 "Research evidence SHA256: " + digest],
                sha=source_sha, seed=seed, issue=TRACK_ISSUES[track],
                action="Reproduce the failed test on a disposable fixture, investigate, propose a reviewed PR",
            )
    if any(found[t]["status"] == "NOT_CONFIGURED"
           for t in ("TASK-001", "TASK-002", "TASK-003")):
        return _make(
            "REQUEST_EXECUTABLE_ADAPTER",
            ["R01-R10 reference probes do not establish native OpDB correctness",
             "Safety/Core/Quality executable integration remains incomplete",
             "Issue #21 blocks untrusted capture; default Source-only",
             "Research evidence SHA256: " + digest],
            sha=source_sha, seed=seed, issue=3,
            action="Import original runnable Core code with exact SHA and tests; request independent Safety/Quality review",
        )
    return _make(
        "AWAIT_INDEPENDENT_QUALITY",
        ["Task statuses are research labels, not certified engine guarantees",
         "Independent adversarial Quality verdict and trusted capture are still required",
         "Research evidence SHA256: " + digest],
        sha=source_sha, seed=seed, issue=4,
        action="Run Quality oracle on executable combined Core+Safety adapter and submit signed-off evidence",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="One safe, bounded read-only planning step")
    parser.add_argument("--research", required=True, help="research.cycle JSON report path")
    parser.add_argument("--expected-sha", required=True, help="checked-out 40-digit Git commit SHA")
    parser.add_argument("--output", help="optional decision JSON path")
    args = parser.parse_args(argv)
    try:
        payload = json.loads(Path(args.research).read_text(encoding="utf-8"))
        decision = plan(payload, args.expected_sha)
    except (OSError, ValueError, TypeError) as exc:
        decision = _invalid(type(exc).__name__ + ": " + str(exc))
    encoded = json.dumps(decision, indent=2, ensure_ascii=False) + "\n"
    print(encoded, end="")
    if args.output:
        Path(args.output).write_text(encoded, encoding="utf-8")
    return 2 if decision["state"] in ("HOLD_EVIDENCE", "ESCALATE_SAFETY",
                                      "INVESTIGATE_FAILED_TRACK") else 0


if __name__ == "__main__":
    raise SystemExit(main())
