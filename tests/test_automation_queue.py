"""S-009 offline work-queue contract tests; no network or worker execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from foundry.automation_queue import next_step, _load, main

SHA = "a" * 40
SOURCE = Path(__file__).resolve().parents[1] / "foundry" / "automation_worklist.json"
PROOF = "https://github.com/mel2003ru-code/OpDB/pull/32"


class AutomationQueueTests(unittest.TestCase):
    def setUp(self):
        self.queue = json.loads(SOURCE.read_text(encoding="utf-8"))
        # Real queue evolves between scheduled iterations; tests use a stable
        # READY baseline, never hardcode the live progress state.
        for item in self.queue["items"]:
            item.update(status="READY", evidence_url=None)

    def test_live_review_only_queue_starts_at_first_task(self):
        result = next_step(self.queue, current_sha=SHA, ci_state="NO_RUNNER")
        self.assertEqual(result["state"], "PROPOSE_REVIEW_ONLY")
        self.assertEqual(result["task_id"], "FND-009A")
        self.assertEqual(result["ci_observation"], "NO_RUNNER")
        for flag in ("ci_attested", "task_execution_authorized",
                     "github_write_authorized", "worker_code_execution_authorized",
                     "automatic_merge_allowed", "production_allowed",
                     "trusted_controller_attested", "launch_authorized"):
            self.assertIs(result[flag], False)

    def test_recorded_completion_advances_but_does_not_attest(self):
        self.queue["items"][0].update(status="DONE", evidence_url=PROOF)
        result = next_step(self.queue, current_sha=SHA, ci_state="PASS")
        self.assertEqual(result["state"], "PROPOSE_REVIEW_ONLY")
        self.assertEqual(result["task_id"], "FND-009B")
        self.assertFalse(result["ci_attested"])

    def test_rerun_does_not_skip_uncompleted_task(self):
        first = next_step(self.queue, current_sha=SHA)
        second = next_step(self.queue, current_sha=SHA)
        self.assertEqual(first, second)
        self.assertEqual(first["task_id"], "FND-009A")

    def test_real_executed_ci_failure_blocks_new_proposal(self):
        result = next_step(self.queue, current_sha=SHA, ci_state="FAIL_EXECUTED")
        self.assertEqual(result["state"], "INVESTIGATE_EXECUTED_CI")
        self.assertFalse(result["task_execution_authorized"])

    def test_completed_queue_still_cannot_authorize_launch(self):
        for item in self.queue["items"]:
            item.update(status="DONE", evidence_url=PROOF)
        result = next_step(self.queue, current_sha=SHA, ci_state="PASS")
        self.assertEqual(result["state"], "QUEUE_COMPLETE_UNATTESTED")
        self.assertFalse(result["launch_authorized"])

    def test_reject_unknown_task_missing_proof_and_wrong_sha(self):
        variants = []
        wrong = copy.deepcopy(self.queue)
        wrong["items"][0]["id"] = "DEPLOY_PRODUCTION"
        variants.append(wrong)
        wrong = copy.deepcopy(self.queue)
        wrong["items"][0]["status"] = "DONE"
        variants.append(wrong)
        wrong = copy.deepcopy(self.queue)
        wrong["repository"] = "attacker/OpDB"
        variants.append(wrong)
        wrong = copy.deepcopy(self.queue)
        wrong["items"][1]["id"] = wrong["items"][0]["id"]
        variants.append(wrong)
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertEqual(next_step(variant, current_sha=SHA)["state"], "HOLD")
        self.assertEqual(next_step(self.queue, current_sha="invalid")["state"], "HOLD")

    def test_strict_loader_rejects_duplicate_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "queue.json"
            for payload in (b'{"x":1,"x":2}', b"x" * 8193):
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    _load(path)

    def test_cli_plan_has_no_execution_or_write_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "plan.json"
            source = Path(tmp) / "queue.json"
            source.write_text(json.dumps(self.queue), encoding="utf-8")
            code = main(["--queue", str(source), "--expected-sha", SHA,
                         "--ci-state", "NO_RUNNER", "--output", str(out)])
            self.assertEqual(code, 0)
            result = json.loads(out.read_text(encoding="utf-8"))
            self.assertFalse(result["github_write_authorized"])
            self.assertFalse(result["launch_authorized"])


if __name__ == "__main__":
    unittest.main()
