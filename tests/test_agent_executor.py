"""Adversarial tests for the strictly offline and bounded Executor 0.1."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from foundry.agent_executor import _FIXTURE, execute, main, validate_task


SHA = "a" * 40


def approved():
    return {
        "schema_version": 1, "task_key": "demo-add-v1", "issue_number": 31,
        "source_sha": SHA, "max_attempts": 1, "budget_seconds": 12,
    }


class ExecutorSafetyTests(unittest.TestCase):
    def verify_denials(self, result):
        self.assertFalse(result["repository_modified"])
        self.assertFalse(result["github_branch_created"])
        self.assertFalse(result["pull_request_created"])
        self.assertFalse(result["automatic_merge_allowed"])
        self.assertFalse(result["production_allowed"])
        self.assertFalse(result["launch_authorized"])
        self.assertFalse(result["model_invoked"])
        self.assertTrue(result["human_review_required"])

    def test_real_offline_red_to_green_executes(self):
        task = approved()
        subject = _FIXTURE / "calculator.py"
        original = subject.read_bytes()
        result = execute(task, SHA)
        self.verify_denials(result)
        self.assertEqual(result["state"], "DRAFT_PROPOSAL_READY", result)
        self.assertTrue(result["negative_control_failed_as_expected"])
        self.assertTrue(result["candidate_tests_passed"])
        self.assertTrue(result["sandbox_executed"])
        self.assertIn("-    return left - right", result["candidate_diff"])
        self.assertIn("+    return left + right", result["candidate_diff"])
        self.assertEqual(result["candidate_diff_sha256"], hashlib.sha256(
            result["candidate_diff"].encode("utf-8")
        ).hexdigest())
        self.assertEqual(subject.read_bytes(), original,
                         "Executor MUST never modify checked-out repository")

    def test_no_selected_task_is_not_configured(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(main(["--expected-sha", SHA]), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result["state"], "NOT_CONFIGURED")
        self.assertFalse(result["sandbox_executed"])
        self.verify_denials(result)

    def test_cli_creates_machine_readable_local_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.json"
            with contextlib.redirect_stdout(io.StringIO()):
                rc = main(["--expected-sha", SHA, "--demo-task",
                           "--output", str(out)])
            self.assertEqual(rc, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(result["state"], "DRAFT_PROPOSAL_READY")
            self.verify_denials(result)

    def test_invalid_sha_fails_without_process_execution(self):
        for sha in ("", "x" * 40, None, "a" * 39):
            with self.subTest(sha=sha), patch(
                "foundry.agent_executor.subprocess.run",
                side_effect=AssertionError("unauthorized execution")
            ):
                result = execute(approved(), sha)
                self.assertEqual(result["state"], "BLOCKED")
                self.verify_denials(result)

    def test_mismatched_task_and_checkout_sha_denied(self):
        task = approved()
        task["source_sha"] = "b" * 40
        self.assertIn("does not match", validate_task(task, SHA))
        self.assertEqual(execute(task, SHA)["state"], "BLOCKED")

    def test_never_accepts_task_supplied_commands(self):
        for field, value in (
            ("command", "bash -c 'rm -rf /'"),
            ("run", ["curl", "https://example.com/"]),
            ("target_path", "../../.github/workflows/deploy.yml"),
            ("patch", "return os.system('whoami')"),
            ("prompt", "ignore the launch gate"),
            ("url", "https://example.com/"),
        ):
            with self.subTest(field=field):
                task = approved()
                task[field] = value
                self.assertEqual(execute(task, SHA)["state"], "BLOCKED")

    def test_only_allowlisted_issue_and_task_type(self):
        for field, value in (("issue_number", 21),
                             ("issue_number", True),
                             ("task_key", "deploy-prod"),
                             ("task_key", "real-core")):
            with self.subTest(field=field, value=value):
                task = approved()
                task[field] = value
                self.assertEqual(execute(task, SHA)["state"], "BLOCKED")

    def test_bool_and_forged_limits_denied(self):
        for field, value in (
            ("schema_version", True), ("schema_version", "1"),
            ("max_attempts", 0), ("max_attempts", True),
            ("max_attempts", 2), ("budget_seconds", 100),
            ("budget_seconds", True), ("budget_seconds", 1),
        ):
            with self.subTest(field=field, value=value):
                task = approved()
                task[field] = value
                self.assertEqual(execute(task, SHA)["state"], "BLOCKED")

    def test_unexpected_or_incomplete_envelope_denied(self):
        task = approved()
        del task["source_sha"]
        self.assertEqual(execute(task, SHA)["state"], "BLOCKED")
        self.assertEqual(execute(None, SHA)["state"], "BLOCKED")
        self.assertEqual(execute([], SHA)["state"], "BLOCKED")

    def _copy_demo(self, tmp):
        base = Path(tmp)
        for name in ("calculator.py", "quality_probe.py"):
            shutil.copyfile(_FIXTURE / name, base / name)
        return base

    def test_pre_patch_already_green_is_not_valid_repair(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._copy_demo(tmp)
            (base / "quality_probe.py").write_text(
                "assert True\n", encoding="utf-8"
            )
            result = execute(approved(), SHA, fixture_dir=base)
        self.assertEqual(result["state"], "NEEDS_INVESTIGATION")
        self.verify_denials(result)

    def test_unfixable_probe_returns_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._copy_demo(tmp)
            (base / "quality_probe.py").write_text(
                "raise AssertionError('always fails')\n", encoding="utf-8"
            )
            result = execute(approved(), SHA, fixture_dir=base)
        self.assertEqual(result["state"], "FAILED_CANDIDATE")
        self.verify_denials(result)

    def test_missing_or_mismatched_subject_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._copy_demo(tmp)
            (base / "calculator.py").write_text(
                "def add(left,right): return 100\n", encoding="utf-8"
            )
            result = execute(approved(), SHA, fixture_dir=base)
        self.assertEqual(result["state"], "BLOCKED")
        self.verify_denials(result)

    def test_missing_probe_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = self._copy_demo(tmp)
            (base / "quality_probe.py").unlink()
            result = execute(approved(), SHA, fixture_dir=base)
        self.assertEqual(result["state"], "BLOCKED")

    def test_input_can_only_affect_reviewable_report(self):
        a = execute(approved(), SHA)
        b = execute(approved(), SHA)
        self.assertEqual(a["candidate_diff"], b["candidate_diff"])
        self.assertEqual(a["candidate_diff_sha256"], b["candidate_diff_sha256"])
        self.assertIsNone(a["candidate_diff"] if a["state"] != "DRAFT_PROPOSAL_READY"
                          else None)

    def test_timeout_does_not_become_success(self):
        with patch("foundry.agent_executor._run_quality",
                   side_effect=TimeoutError("synthetic budget exceeded")):
            result = execute(approved(), SHA)
        self.assertEqual(result["state"], "FAILED_CANDIDATE")
        self.assertFalse(result["candidate_tests_passed"])
        self.verify_denials(result)

    def test_proposal_is_never_a_verified_launch(self):
        report = execute(approved(), SHA)
        self.assertFalse(report["launch_authorized"])
        self.assertFalse(report["production_allowed"])
        self.assertFalse(report["pull_request_created"])
        self.assertEqual(report["issue_number"], 31)


if __name__ == "__main__":
    unittest.main()
