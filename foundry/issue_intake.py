"""Read-only intake of *one* actual GitHub issue into a fixed offline demo task.

GitHub issue title/body/comments are untrusted and NEVER become executable
instructions. This does not grant a general-purpose agent issue access.
"""
import argparse
import json
import re
from pathlib import Path

REPO = "mel2003ru-code/OpDB"
ISSUE = 31
API = "https://api.github.com/repos/" + REPO + "/issues/" + str(ISSUE)
URL = "https://github.com/" + REPO + "/issues/" + str(ISSUE)
SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_MAX_ISSUE_JSON_BYTES = 32 * 1024


def admit_issue(issue, checked_out_sha):
    """Return (task, failure); no network or repository mutation."""
    if not isinstance(checked_out_sha, str) or SHA.fullmatch(checked_out_sha) is None:
        return None, "Exact checked-out Git commit required"
    if not isinstance(issue, dict):
        return None, "GitHub issue payload missing or malformed"
    if (type(issue.get("number")) is not int or issue["number"] != ISSUE
            or issue.get("url") != API or issue.get("html_url") != URL
            or issue.get("repository_url") != API.rsplit("/issues/", 1)[0]
            or issue.get("state") != "open"
            or "pull_request" in issue):
        return None, "Issue is not the expected open OpDB #31 tracking task"
    # ALL user-authored title/body/comments are ignored, including prompt injection.
    # This is a fixed synthetic admission policy and cannot run other Issue tasks.
    return {
        "schema_version": 1,
        "task_key": "demo-add-v1",
        "issue_number": ISSUE,
        "source_sha": checked_out_sha,
        "max_attempts": 1,
        "budget_seconds": 12,
    }, None


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only one-issue demo admission")
    parser.add_argument("--issue-json", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        with Path(args.issue_json).open("rb") as handle:
            raw = handle.read(_MAX_ISSUE_JSON_BYTES + 1)
        if len(raw) > _MAX_ISSUE_JSON_BYTES:
            task, problem = None, "GitHub issue JSON exceeds 32 KiB"
        else:
            issue = json.loads(raw.decode("utf-8", "strict"))
            task, problem = admit_issue(issue, args.expected_sha)
    except (OSError, ValueError, UnicodeError) as exc:
        task, problem = None, type(exc).__name__ + ": " + str(exc)
    if task is None:
        # No task artifact when evidence is missing: fail-closed.
        print(json.dumps({"state": "BLOCKED", "reason": problem},
                         ensure_ascii=False))
        return 2
    Path(args.output).write_text(
        json.dumps(task, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "state": "ADMITTED_FIXED_DEMO_ONLY",
        "issue_number": ISSUE,
        "source_sha": args.expected_sha,
        "code_execution_authorized": False,
        "model_access_authorized": False,
        "github_write_authorized": False,
        "note": "Issue metadata admits one synthetic task, never issue instructions",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
