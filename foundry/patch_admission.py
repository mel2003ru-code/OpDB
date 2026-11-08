"""Agent 0.2: quarantine a proposed code change as DATA, never execute it.

This gate intentionally accepts only the existing synthetic calculator fixture.
Model-generated text is not trusted. Full code execution requires a separately
verified OS sandbox, independent Quality, and explicit approval; not wired here.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

_PATH = "foundry/fixtures/calculator.py"
_TASK = "demo-add-v1"
_SHA40 = re.compile(r"[a-fA-F0-9]{40}\Z")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")
_MAX_BYTES = 4096
_MAX_PROPOSAL_JSON_BYTES = 16 * 1024


def _deny(reason):
    return {
        "state": "REJECTED",
        "reasons": [reason],
        "diff": None,
        "diff_sha256": None,
        "candidate_sha256": None,
        "source_checkout_modified": False,
        "candidate_executed": False,
        "sandbox_verified": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
    }


def admit(proposal, checked_out_sha, checkout_root):
    """Return a proposed *textual* diff, never apply or run a candidate.

    Proof is limited to exact metadata/size/hash checks, not code safety.
    No arbitrary file paths, commands, test changes or CI configuration edits.
    """
    if not isinstance(checked_out_sha, str) or not _SHA40.fullmatch(checked_out_sha):
        return _deny("Missing exact expected Git commit SHA")
    required = {"schema_version", "source_sha", "task_key", "issue_number",
                "path", "original_sha256", "candidate_sha256", "candidate_text"}
    if type(proposal) is not dict or set(proposal) != required:
        return _deny("Proposal schema is missing fields or includes extra fields")
    if type(proposal["schema_version"]) is not int or proposal["schema_version"] != 1:
        return _deny("Invalid proposal schema version")
    if proposal["source_sha"] != checked_out_sha:
        return _deny("Proposal SHA does not match this checkout")
    if proposal["task_key"] != _TASK or type(proposal["issue_number"]) is not int or proposal["issue_number"] != 31:
        return _deny("Only synthetic Issue #31 / demo-add-v1 is admissible")
    if proposal["path"] != _PATH:
        return _deny("Only the fixed synthetic source path can be proposed")
    text = proposal["candidate_text"]
    if (type(text) is not str or "\x00" in text or "\r" in text
            or not text.endswith("\n")):
        return _deny("Candidate text encoding/format rejected")
    try:
        encoded = text.encode("utf-8", "strict")
    except UnicodeError:
        return _deny("Candidate must be valid UTF-8")
    if not encoded or len(encoded) > _MAX_BYTES:
        return _deny("Proposed code exceeds fixed 4096-byte limit")
    if not isinstance(proposal["original_sha256"], str) or not _SHA256.fullmatch(proposal["original_sha256"]):
        return _deny("Original content digest is missing or malformed")
    if not isinstance(proposal["candidate_sha256"], str) or not _SHA256.fullmatch(proposal["candidate_sha256"]):
        return _deny("Candidate digest is missing or malformed")
    if hashlib.sha256(encoded).hexdigest() != proposal["candidate_sha256"].lower():
        return _deny("Candidate content/digest mismatch")

    # The only filesystem read resolves a hard-coded path; never resolve input
    # as a path or execute a task-supplied instruction.
    root = Path(checkout_root)
    source = root / _PATH
    try:
        if (not root.is_dir() or not source.is_file()
                or any(p.is_symlink() for p in (root, *root.parents, source.parent, source))):
            return _deny("Trusted synthetic fixture does not exist or traverses symlinks")
        original_bytes = source.read_bytes()
        original = original_bytes.decode("utf-8", "strict")
    except (OSError, UnicodeError):
        return _deny("Could not read the trusted fixture")
    if hashlib.sha256(original_bytes).hexdigest() != proposal["original_sha256"].lower():
        return _deny("The expected original fixture changed")
    if len(original_bytes) > _MAX_BYTES:
        return _deny("Original fixture is too large")
    if original_bytes == encoded:
        return _deny("No change proposed")
    # Data-only unified diff for human review: NEVER touch checkout.
    diff = "".join(difflib.unified_diff(
        original.splitlines(keepends=True), text.splitlines(keepends=True),
        fromfile="a/" + _PATH, tofile="b/" + _PATH,
    ))
    return {
        "state": "QUARANTINED_FOR_REVIEW",
        "reasons": ["Hashes and allowed path validated; code is UNTRUSTED and unexecuted",
                    "No general model integration or operational sandbox is active"],
        "diff": diff,
        "diff_sha256": hashlib.sha256(diff.encode("utf-8")).hexdigest(),
        "candidate_sha256": hashlib.sha256(encoded).hexdigest(),
        "source_checkout_modified": False,
        "candidate_executed": False,
        "sandbox_verified": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Quarantine a fixed synthetic proposal; no execution")
    p.add_argument("--proposal", required=True)
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--checkout", required=True)
    p.add_argument("--output")
    args = p.parse_args(argv)
    try:
        with Path(args.proposal).open("rb") as stream:
            payload = stream.read(_MAX_PROPOSAL_JSON_BYTES + 1)
        if len(payload) > _MAX_PROPOSAL_JSON_BYTES:
            result = _deny("Proposal JSON exceeds 16 KiB")
        else:
            proposal = json.loads(payload.decode("utf-8", "strict"))
            result = admit(proposal, args.expected_sha, args.checkout)
    except (OSError, ValueError, UnicodeError) as exc:
        result = _deny(type(exc).__name__ + ": cannot load proposal")
    serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    print(serialized, end="")
    if args.output:
        Path(args.output).write_text(serialized, encoding="utf-8")
    return 0 if result["state"] == "QUARANTINED_FOR_REVIEW" else 2


if __name__ == "__main__":
    raise SystemExit(main())
