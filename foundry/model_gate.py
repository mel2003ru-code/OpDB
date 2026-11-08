"""OpDB Agent Brain 0.1 — zero-cost MODEL ADMISSION gate, not an LLM.

This stage implements a deny-by-default contract for future model providers.
It never imports any HTTP client, reads API keys, performs inference, modifies
code, or publishes a PR. Only the fixed synthetic offline mock is admissible.
Even if a caller supplies forged owner_approved fields, remote inference stays
BLOCKED until a separately reviewed, actual spending controller exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

_SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
_FIELDS = frozenset({
    "schema_version", "source_sha", "issue_number", "task_key",
    "provider", "model_id", "max_model_requests", "max_total_tokens",
    "max_cost_micro_usd", "mode",
})
_MAX_JSON = 4096


def _decision(state, reason, sha=None):
    return {
        "schema_version": 1,
        "state": state,
        "reason": reason,
        "source_sha": sha,
        "model_requests_used": 0,
        "model_tokens_used": 0,
        "model_cost_micro_usd": 0,
        "model_invoked": False,
        "remote_network_authorized": False,
        "model_output_executable": False,
        "github_write_allowed": False,
        "automatic_merge_allowed": False,
        "production_allowed": False,
        "launch_authorized": False,
        "review_required": True,
    }


def evaluate(policy, checkout_sha):
    """Allow a fixed zero-cost mock *contract*, never a provider call."""
    if type(checkout_sha) is not str or not _SHA.fullmatch(checkout_sha):
        return _decision("BLOCKED", "Exact checkout SHA required")
    if type(policy) is not dict or set(policy) != _FIELDS:
        return _decision("BLOCKED", "Unexpected, missing or injected policy fields",
                         checkout_sha)
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        return _decision("BLOCKED", "Unknown model policy version", checkout_sha)
    if policy["source_sha"] != checkout_sha:
        return _decision("BLOCKED", "Policy bound to another commit", checkout_sha)
    if type(policy["issue_number"]) is not int or policy["issue_number"] != 31:
        return _decision("BLOCKED", "Only synthetic tracking task #31", checkout_sha)
    if policy["task_key"] != "demo-add-v1":
        return _decision("BLOCKED", "Real code task requires future owner approval",
                         checkout_sha)
    if (policy["mode"] != "offline_mock"
            or policy["provider"] != "offline_mock"
            or policy["model_id"] != "fixed-synthetic-v1"):
        return _decision("BLOCKED",
                         "Real AI/model provider is NOT configured or authorized",
                         checkout_sha)
    for key in ("max_model_requests", "max_total_tokens", "max_cost_micro_usd"):
        if type(policy[key]) is not int or policy[key] != 0:
            return _decision("BLOCKED",
                             "Mock must allocate exactly zero billed requests, tokens and cost",
                             checkout_sha)
    return _decision(
        "OFFLINE_MOCK_POLICY_ONLY",
        "Synthetic zero-cost policy validated; no inference and no patch execution",
        checkout_sha,
    )


def offline_policy(sha):
    """Build only the fixed permitted zero-cost policy."""
    return {
        "schema_version": 1,
        "source_sha": sha,
        "issue_number": 31,
        "task_key": "demo-add-v1",
        "provider": "offline_mock",
        "model_id": "fixed-synthetic-v1",
        "max_model_requests": 0,
        "max_total_tokens": 0,
        "max_cost_micro_usd": 0,
        "mode": "offline_mock",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Fail-closed Agent Brain policy preflight")
    p.add_argument("--expected-sha", required=True)
    p.add_argument("--offline-demo", action="store_true",
                   help="Only the fixed zero-cost synthetic policy; no model")
    p.add_argument("--policy-file",
                   help="Strict JSON policy; remote model invocations always blocked")
    p.add_argument("--output")
    args = p.parse_args(argv)
    if args.offline_demo and args.policy_file:
        result = _decision("BLOCKED", "Ambiguous policy sources")
    elif args.offline_demo:
        result = evaluate(offline_policy(args.expected_sha), args.expected_sha)
    elif args.policy_file:
        try:
            with Path(args.policy_file).open("rb") as handle:
                raw = handle.read(_MAX_JSON + 1)
            if len(raw) > _MAX_JSON:
                result = _decision("BLOCKED", "Policy exceeds 4096 bytes")
            else:
                result = evaluate(json.loads(raw.decode("utf-8", "strict")),
                                  args.expected_sha)
        except (OSError, ValueError, UnicodeError):
            result = _decision("BLOCKED", "Invalid or unavailable policy JSON")
    else:
        result = _decision("NOT_CONFIGURED", "No approved model policy")
    output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    print(output, end="")
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    return 0 if result["state"] in ("OFFLINE_MOCK_POLICY_ONLY", "NOT_CONFIGURED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
