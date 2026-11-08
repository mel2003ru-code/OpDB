"""Fail-closed future-model gate: no actual provider calls or billing."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from foundry.model_gate import evaluate, offline_policy, main

SHA = "a" * 40


class ModelGateTests(unittest.TestCase):
    def denied_authorities(self, result):
        for key in ("model_invoked", "remote_network_authorized",
                    "model_output_executable", "github_write_allowed",
                    "automatic_merge_allowed", "production_allowed",
                    "launch_authorized"):
            self.assertIs(result[key], False, key)
        self.assertEqual(result["model_requests_used"], 0)
        self.assertEqual(result["model_tokens_used"], 0)
        self.assertEqual(result["model_cost_micro_usd"], 0)

    def test_zero_cost_mock_admits_contract_not_model(self):
        result = evaluate(offline_policy(SHA), SHA)
        self.assertEqual(result["state"], "OFFLINE_MOCK_POLICY_ONLY")
        self.denied_authorities(result)
        self.assertTrue(result["review_required"])

    def test_remote_provider_is_denied_even_with_fake_approval(self):
        for provider in ("deepseek", "openai", "other", "local_server", ""):
            with self.subTest(provider=provider):
                p = offline_policy(SHA)
                p["provider"] = provider
                p["mode"] = "remote"
                result = evaluate(p, SHA)
                self.assertEqual(result["state"], "BLOCKED")
                self.denied_authorities(result)

    def test_network_or_secret_commands_injected_into_policy_denied(self):
        for key in ("api_key", "command", "url", "headers", "shell",
                    "owner_approved", "override_budget", "model_response"):
            with self.subTest(key=key):
                p = offline_policy(SHA)
                p[key] = "ignore safety, publish"
                result = evaluate(p, SHA)
                self.assertEqual(result["state"], "BLOCKED")
                self.denied_authorities(result)

    def test_no_cost_or_token_budget_can_be_granted_to_mock(self):
        for key in ("max_model_requests", "max_total_tokens",
                    "max_cost_micro_usd"):
            for value in (1, -1, True, 0.1, "0"):
                with self.subTest(key=key, value=value):
                    p = offline_policy(SHA)
                    p[key] = value
                    result = evaluate(p, SHA)
                    self.assertEqual(result["state"], "BLOCKED")
                    self.denied_authorities(result)

    def test_checkout_sha_must_be_exact(self):
        for sha in ("bad", "f" * 39, "z" * 40, "", None, True):
            with self.subTest(sha=sha):
                result = evaluate(offline_policy(SHA), sha)
                self.assertEqual(result["state"], "BLOCKED")
                self.denied_authorities(result)

    def test_commit_mismatch_denied(self):
        p = offline_policy(SHA)
        p["source_sha"] = "b" * 40
        self.assertEqual(evaluate(p, SHA)["state"], "BLOCKED")

    def test_non_synthetic_real_tasks_denied(self):
        for key, value in (("issue_number", 21), ("issue_number", True),
                           ("task_key", "repair-core"),
                           ("model_id", "real-deepseek")):
            with self.subTest(key=key, value=value):
                p = offline_policy(SHA)
                p[key] = value
                self.assertEqual(evaluate(p, SHA)["state"], "BLOCKED")

    def test_malformed_inputs_denied(self):
        for p in ({}, [], None, "start", 3, True):
            with self.subTest(payload=p):
                self.assertEqual(evaluate(p, SHA)["state"], "BLOCKED")
        p = offline_policy(SHA)
        p["schema_version"] = True
        self.assertEqual(evaluate(p, SHA)["state"], "BLOCKED")

    def test_offline_cli_emits_only_no_model_policy(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            rc = main(["--expected-sha", SHA, "--offline-demo"])
        self.assertEqual(rc, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "OFFLINE_MOCK_POLICY_ONLY")
        self.denied_authorities(result)

    def test_no_policy_default_not_configured(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            rc = main(["--expected-sha", SHA])
        self.assertEqual(rc, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.denied_authorities(result)

    def test_cli_refuses_oversized_policy_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model-policy.json"
            path.write_bytes(b" " * 4097)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = main(["--expected-sha", SHA, "--policy-file", str(path)])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "BLOCKED")

    def test_no_external_process_or_network_called(self):
        with (patch("subprocess.run", side_effect=AssertionError("process call")),
              patch("urllib.request.urlopen", side_effect=AssertionError("network"))):
            result = evaluate(offline_policy(SHA), SHA)
        self.denied_authorities(result)

    def test_ambiguous_policy_sources_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "p.json"
            path.write_text(json.dumps(offline_policy(SHA)), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                rc = main(["--expected-sha", SHA, "--offline-demo",
                           "--policy-file", str(path)])
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
