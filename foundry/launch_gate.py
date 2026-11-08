"""Launch Gate 0.1: fail-closed *metadata* readiness, not an executable launcher.

A self-reported manifest is never authoritative release approval. No operations
on production, GitHub, secrets, models or deployment services are performed.
"""
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

SHA40 = re.compile(r"[0-9a-fA-F]{40}\Z")
SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
ACTION_URL = re.compile(
    r"https://github\.com/mel2003ru-code/OpDB/actions/runs/[1-9][0-9]*\Z"
)

REQUIRED_CHECKS = (
    "actual_core_adapter",
    "trusted_change_capture",
    "independent_quality",
    "full_oracle_and_fault_matrix",
    "reproducible_benchmarks",
    "independent_peer_baselines",
    "agent_execution_isolation",
    "agent_budget_and_rate_limits",
    "least_privilege_and_secrets",
    "staging_deployment_rehearsal",
    "rollback_and_restore_rehearsal",
    "production_policy_approval",
    "observability_and_emergency_stop",
    "superiority_pause_watcher",
)
MAX_CHECKS = len(REQUIRED_CHECKS)


def _valid_time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
        return parsed.utcoffset() == dt.timedelta(0)
    except ValueError:
        return False


def _result(state, failures, verified_fields=0):
    return {
        "state": state,
        "next_action": (
            "Obtain independently authenticated evidence and owner launch authorization"
            if state == "OWNER_REVIEW_REQUIRED"
            else "Continue implementing missing or failed pre-launch requirements"
        ),
        "button_label": "Запустить",
        "button_enabled": False,
        "launch_authorized": False,
        "launched": False,
        "launched_at_utc": None,
        "launch_request_at_utc": None,
        "verified_metadata_entries": verified_fields,
        "required_entries": MAX_CHECKS,
        "failures": failures,
        "scope": (
            "Self-reported metadata preflight only; does not verify signatures, "
            "launch a runner, authorize production or timestamp a real start"
        ),
    }


def evaluate(manifest):
    """A syntactically complete PASS set still requires human and trusted verification."""
    if manifest is None:
        return _result("NOT_READY", ["No launch manifest or real verified engine"])
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int:
        return _result("BLOCKED", ["Invalid manifest container/version"])
    if manifest["schema_version"] != 1:
        return _result("BLOCKED", ["Unknown manifest schema version"])
    sha = manifest.get("candidate_sha")
    if not isinstance(sha, str) or not SHA40.fullmatch(sha):
        return _result("BLOCKED", ["Exact candidate commit SHA is required"])
    checks = manifest.get("checks")
    if not isinstance(checks, dict):
        return _result("NOT_READY", ["Missing verification matrix"])
    extras = sorted(set(checks) - set(REQUIRED_CHECKS))
    if extras:
        return _result("BLOCKED", ["Unexpected check identifiers: " + ", ".join(extras)])
    failures = []
    passed = 0
    critical = False
    for item in REQUIRED_CHECKS:
        proof = checks.get(item)
        if not isinstance(proof, dict):
            failures.append(item + ": no evidence")
            continue
        status = proof.get("status")
        if status == "FAIL":
            critical = True
            failures.append(item + ": reported FAIL")
            continue
        if status != "PASS":
            failures.append(item + ": not PASS")
            continue
        if (proof.get("target_sha") != sha
                or not isinstance(proof.get("run_url"), str)
                or ACTION_URL.fullmatch(proof["run_url"]) is None
                or not isinstance(proof.get("sha256"), str)
                or SHA256.fullmatch(proof["sha256"]) is None
                or not _valid_time(proof.get("checked_at_utc"))):
            failures.append(item + ": missing/mismatched provenance fields")
            continue
        passed += 1
    if critical:
        return _result("BLOCKED", failures, passed)
    if failures:
        return _result("NOT_READY", failures, passed)
    return _result(
        "OWNER_REVIEW_REQUIRED",
        ["All 14 self-reported entries are syntactically complete but UNAUTHENTICATED",
         "Actual protected capture, independent Quality, staging, rollback and approvals "
         "must be checked against trusted external sources before enabling launch"],
        passed,
    )


def format_confirmed_start_time(utc_timestamp):
    """Formatting ONLY: callers must first confirm a real launch event externally.

    This function does not claim that an event occurred or record anything.
    """
    if not _valid_time(utc_timestamp):
        raise ValueError("A canonical UTC 'Z' event timestamp is required")
    instant = dt.datetime.fromisoformat(utc_timestamp[:-1] + "+00:00")
    return {
        "utc": instant.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "paris": instant.astimezone(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds"),
        "moscow": instant.astimezone(ZoneInfo("Europe/Moscow")).isoformat(timespec="seconds"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect prelaunch metadata; never launches")
    parser.add_argument("--manifest", help="Optional proposed launch manifest JSON")
    parser.add_argument("--output", help="Optional decision JSON output file")
    args = parser.parse_args(argv)
    try:
        manifest = (json.loads(Path(args.manifest).read_text(encoding="utf-8"))
                    if args.manifest else None)
        verdict = evaluate(manifest)
    except (OSError, ValueError, TypeError) as exc:
        verdict = _result("BLOCKED", [type(exc).__name__ + ": " + str(exc)])
    serialized = json.dumps(verdict, indent=2, ensure_ascii=False) + "\n"
    print(serialized, end="")
    if args.output:
        Path(args.output).write_text(serialized, encoding="utf-8")
    return 2 if verdict["state"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
