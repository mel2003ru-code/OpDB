"""S-008B-2 reference-only authenticated envelope for a FUTURE trusted controller.

NOT a trust root: this PR controls this code and its tests. No service, secret,
GitHub write token, Docker invocation or launch path is enabled by this module.
A separately governed controller would have to review/pin its own implementation.
HMAC proves only possession of a controller secret; it DOES NOT prove worker
honesty, OS isolation, correctness, or publicly verifiable provenance.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3

_PROTOCOL = "opdb-s008b2-reference-v1"
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
_MAX_RESULT = 16 * 1024
_MAX_TTL_SECONDS = 120
_ALLOWED_REQUEST = frozenset({
    "schema_version", "source_sha", "task_key", "issue_number",
    "operation", "allowed_path", "max_candidate_bytes", "max_attempts",
    "max_model_requests", "max_total_tokens", "max_cost_micro_usd",
    "network_allowed", "shell_allowed", "execution_allowed",
    "github_write_allowed",
})
_CHALLENGE_KEYS = frozenset({
    "protocol", "repo", "source_sha", "task_key", "issue_number",
    "request_sha256", "policy_sha256", "image_digest", "nonce",
    "issued_at", "expires_at", "max_output_bytes",
})
_REPORT_REQUIRED = frozenset({
    "probe", "passed", "reply", "session_nonce", "request_sha256",
    "launch_authorized", "github_write_allowed", "model_invoked",
    "arbitrary_model_code_executed", "trusted_controller_attested",
})
_RECEIPT_BODY_KEYS = frozenset({
    "protocol", "repo", "source_sha", "nonce", "request_sha256",
    "response_sha256", "decision",
})


def _canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _mac(key, domain, obj):
    if type(key) is not bytes or len(key) < 32:
        raise ValueError("Controller key unavailable or too short")
    return hmac.new(key, b"OpDB/S008B2/" + domain + b"\x00" +
                    _canonical(obj), hashlib.sha256).hexdigest()


def _valid_request(req):
    if (type(req) is not dict or not set(req) <= _ALLOWED_REQUEST
            or type(req.get("source_sha")) is not str
            or not _SHA.fullmatch(req["source_sha"])
            or type(req.get("task_key")) is not str
            or req["task_key"] != "demo-add-v1"
            or type(req.get("issue_number")) is not int
            or req["issue_number"] != 31
            or req.get("operation") != "PROPOSE_TEXT_ONLY"):
        return False
    for flag in ("execution_allowed", "github_write_allowed"):
        if req.get(flag) is not False:
            return False
    for flag in ("network_allowed", "shell_allowed"):
        if flag in req and req[flag] is not False:
            return False
    for count in ("max_model_requests", "max_total_tokens", "max_cost_micro_usd"):
        if count in req and (type(req[count]) is not int or req[count] != 0):
            return False
    for count in ("max_attempts", "max_candidate_bytes"):
        if count in req and (type(req[count]) is not int or req[count] < 1):
            return False
    if "max_attempts" in req and req["max_attempts"] != 1:
        return False
    if "max_candidate_bytes" in req and req["max_candidate_bytes"] > 4096:
        return False
    if "schema_version" in req and (
            type(req["schema_version"]) is not int or req["schema_version"] != 1):
        return False
    if "allowed_path" in req and req["allowed_path"] != "foundry/fixtures/calculator.py":
        return False
    return True


def build_challenge(*, request, repo, policy_sha256, image_digest, key,
                    issued_at, expires_at, nonce):
    """OFFLINE reference for a separately controlled, never guest-visible key.

    Calling this from PR-controlled CI would NOT authenticate an independent
    controller. Synthetic unit-test keys are never production credentials.
    """
    if not _valid_request(request):
        raise ValueError("Only fixed zero-cost reviewed data task is accepted")
    if (type(repo) is not str or not _REPO.fullmatch(repo)
            or type(policy_sha256) is not str
            or not _SHA256.fullmatch(policy_sha256)
            or type(image_digest) is not str
            or not _IMAGE.fullmatch(image_digest)
            or type(nonce) is not str or not _NONCE.fullmatch(nonce)
            or type(issued_at) is not int or type(expires_at) is not int
            or issued_at < 1 or expires_at <= issued_at):
        raise ValueError("Malformed immutable challenge metadata")
    challenge = {
        "protocol": _PROTOCOL,
        "repo": repo,
        "source_sha": request["source_sha"],
        "task_key": request["task_key"],
        "issue_number": 31,
        "request_sha256": hashlib.sha256(_canonical(request)).hexdigest(),
        "policy_sha256": policy_sha256,
        "image_digest": image_digest,
        "nonce": nonce,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "max_output_bytes": _MAX_RESULT,
    }
    return {"challenge": challenge, "mac": _mac(key, b"challenge", challenge)}


def initialize_ledger(ledger):
    """Prototype schema ONLY. Trusted storage must be outside candidate checkout."""
    if not isinstance(ledger, sqlite3.Connection):
        raise ValueError("Trusted SQLite handle required")
    ledger.execute("PRAGMA synchronous=FULL")
    ledger.execute(
        "CREATE TABLE IF NOT EXISTS s008b2_consumed ("
        "nonce TEXT PRIMARY KEY NOT NULL, "
        "source_sha TEXT NOT NULL, "
        "response_sha256 TEXT NOT NULL, "
        "consumed_at INTEGER NOT NULL)"
    )
    ledger.commit()


def _decode_report(raw, nonce, request_sha256, limit):
    if type(raw) is not bytes or len(raw) > limit or not raw:
        raise ValueError("Unbounded or missing guest output")

    def unique_pairs(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate JSON property")
            out[key] = value
        return out

    def no_constant(_value):
        raise ValueError("Nonstandard JSON constant")

    report = json.loads(raw.decode("utf-8", "strict"),
                        object_pairs_hook=unique_pairs,
                        parse_constant=no_constant)
    if (type(report) is not dict
            or not _REPORT_REQUIRED <= set(report)
            or set(report) - _REPORT_REQUIRED - {"checked"}
            or report["probe"] != "fixed-data-only-handoff-s008"
            or report["passed"] is not True
            or type(report["reply"]) is not dict
            or report["session_nonce"] != nonce
            or report["request_sha256"] != request_sha256):
        raise ValueError("Guest report does not match authenticated request")
    for flag in ("model_invoked", "arbitrary_model_code_executed",
                 "github_write_allowed", "trusted_controller_attested",
                 "launch_authorized"):
        if report[flag] is not False:
            raise ValueError("Guest requested forbidden authority")
    # Observations are guest-asserted DATA, never a trusted confinement proof.
    if "checked" in report and (
            type(report["checked"]) is not dict
            or not report["checked"]
            or any(type(v) is not bool for v in report["checked"].values())):
        raise ValueError("Malformed guest observations")
    return report


def _blocked(reason):
    return {
        "state": "BLOCKED", "reason": reason, "receipt": None,
        "response_sha256": None, "trusted_controller_attested": False,
        "github_write_allowed": False, "automatic_merge_allowed": False,
        "production_allowed": False, "launch_authorized": False,
    }


def admit_result(envelope, report_bytes, *, repo, source_sha, policy_sha256,
                 image_digest, request, key, now, ledger):
    """Authenticate challenge and consume it exactly once; output quarantine only.

    This reference accepts trusted inputs as parameters; it CANNOT establish
    that they came from an independent trust root. An actual controller needs
    owner-governed code, verified checkout, secret store, clock and ledger.
    """
    try:
        if not _valid_request(request) or request["source_sha"] != source_sha:
            return _blocked("Untrusted task or source")
        if type(envelope) is not dict or set(envelope) != {"challenge", "mac"}:
            return _blocked("Malformed signed envelope")
        c = envelope["challenge"]
        tag = envelope["mac"]
        if (type(c) is not dict or set(c) != _CHALLENGE_KEYS
                or type(tag) is not str or not _SHA256.fullmatch(tag)):
            return _blocked("Malformed challenge or tag")
        if not hmac.compare_digest(_mac(key, b"challenge", c), tag):
            return _blocked("Challenge MAC mismatch")
        if (c["protocol"] != _PROTOCOL
                or c["repo"] != repo or c["source_sha"] != source_sha
                or c["task_key"] != "demo-add-v1"
                or type(c["issue_number"]) is not int or c["issue_number"] != 31
                or c["policy_sha256"] != policy_sha256
                or c["image_digest"] != image_digest
                or c["request_sha256"] != hashlib.sha256(_canonical(request)).hexdigest()
                or type(c["nonce"]) is not str or not _NONCE.fullmatch(c["nonce"])
                or type(c["issued_at"]) is not int
                or type(c["expires_at"]) is not int
                or type(now) is not int
                or c["issued_at"] > now or now >= c["expires_at"]
                or c["expires_at"] - c["issued_at"] > _MAX_TTL_SECONDS
                or type(c["max_output_bytes"]) is not int
                or c["max_output_bytes"] != _MAX_RESULT):
            return _blocked("Pinned context, freshness or limits mismatch")
        _decode_report(report_bytes, c["nonce"], c["request_sha256"],
                       c["max_output_bytes"])
        digest = hashlib.sha256(report_bytes).hexdigest()
        if not isinstance(ledger, sqlite3.Connection):
            return _blocked("Trusted ledger unavailable")
        # SQLite UNIQUE constraint + BEGIN IMMEDIATE serialize competing claims.
        # The nonce becomes consumed BEFORE any receipt leaves this function.
        # A crash after commit prevents retry rather than permitting duplicates.
        try:
            ledger.execute("BEGIN IMMEDIATE")
            ledger.execute(
                "INSERT INTO s008b2_consumed "
                "(nonce, source_sha, response_sha256, consumed_at) "
                "VALUES (?,?,?,?)",
                (c["nonce"], source_sha, digest, now))
            ledger.commit()
        except sqlite3.Error:
            ledger.rollback()
            return _blocked("Replay, inaccessible or invalid trusted ledger")
        receipt_body = {
            "protocol": _PROTOCOL, "repo": repo,
            "source_sha": source_sha, "nonce": c["nonce"],
            "request_sha256": c["request_sha256"],
            "response_sha256": digest, "decision": "QUARANTINED_FOR_REVIEW",
        }
        receipt = {"body": receipt_body,
                   "mac": _mac(key, b"receipt", receipt_body)}
        return {
            "state": "QUARANTINED_FOR_REVIEW",
            "reason": "Controller-side binding only; human review still required",
            "receipt": receipt, "response_sha256": digest,
            "trusted_controller_attested": False,
            "github_write_allowed": False, "automatic_merge_allowed": False,
            "production_allowed": False, "launch_authorized": False,
        }
    except (ValueError, TypeError, UnicodeError, OverflowError, sqlite3.Error):
        return _blocked("Invalid or unauthenticated bounded result")


def verify_receipt(receipt, key, expected_report_sha256):
    """Only symmetric-key holders can verify; NOT public-key attestation."""
    try:
        if (type(receipt) is not dict or set(receipt) != {"body", "mac"}
                or type(receipt["body"]) is not dict
                or set(receipt["body"]) != _RECEIPT_BODY_KEYS
                or type(receipt["mac"]) is not str
                or not _SHA256.fullmatch(receipt["mac"])
                or type(expected_report_sha256) is not str
                or not _SHA256.fullmatch(expected_report_sha256)):
            return False
        body = receipt["body"]
        return (
            body["protocol"] == _PROTOCOL
            and body["decision"] == "QUARANTINED_FOR_REVIEW"
            and body["response_sha256"] == expected_report_sha256
            and hmac.compare_digest(_mac(key, b"receipt", body),
                                    receipt["mac"])
        )
    except (ValueError, TypeError, UnicodeError):
        return False
