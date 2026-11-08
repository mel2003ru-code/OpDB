#!/usr/bin/env python3
"""Validate task-handoff metadata only; not database correctness or code proof."""
import datetime as dt
import json
import re
import sys
from pathlib import Path

REQUIRED = {
    "task_id": str, "workstream": str, "date_utc": str,
    "status": str, "summary": str, "commit_sha": str,
    "artifacts": list, "tested_environment": str,
    "reproduce_commands": list, "tests_passed": list,
    "tests_failed": list, "open_risks": list,
    "contract_changes": list, "requires_headquarters_decision": list,
}
STREAMS = {"TASK-001": "Safety", "TASK-002": "Core", "TASK-003": "Quality"}

def validate(path):
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        return ["handoff must be a JSON object"]
    errors = []
    for key, typ in REQUIRED.items():
        if not isinstance(doc.get(key), typ):
            errors.append(f"{key}: expected {typ.__name__}")
    task = doc.get("task_id")
    if task not in STREAMS:
        errors.append("unknown task_id")
    elif doc.get("workstream") != STREAMS[task]:
        errors.append("task/workstream mismatch")
    if doc.get("status") not in ("PASS", "FAIL", "NOT VERIFIED"):
        errors.append("invalid status")
    timestamp = doc.get("date_utc")
    if isinstance(timestamp, str):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",timestamp):
            errors.append("date_utc must be exact ISO UTC format YYYY-MM-DDTHH:MM:SSZ")
        else:
            try:
                dt.datetime.strptime(timestamp,"%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                errors.append("date_utc is not a valid calendar date")
    sha = doc.get("commit_sha")
    if isinstance(sha, str) and sha and not re.fullmatch(r"[a-fA-F0-9]{40}",sha):
        errors.append("commit_sha must be a 40-hex-character commit identifier or blank")
    if doc.get("status") == "PASS":
        if not doc.get("tested_environment") or not doc.get("reproduce_commands"):
            errors.append("PASS requires environment and reproduction commands")
        if doc.get("tests_failed"):
            errors.append("PASS cannot list failing tests")
    return errors

def main():
    if len(sys.argv)!=2:
        print("Usage: python scripts/validate_handoff.py path/to/handoff.json")
        return 2
    try:
        errors=validate(sys.argv[1])
    except (OSError, ValueError, TypeError) as exc:
        print(f"INVALID: {exc}")
        return 1
    if errors:
        print("INVALID:\n" + "\n".join("- "+e for e in errors))
        return 1
    print("VALID METADATA (does not imply correctness of an implementation)")
    return 0

if __name__=="__main__":
    sys.exit(main())
