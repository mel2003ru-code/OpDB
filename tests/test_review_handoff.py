"""FND-009C: review handoff remains an unauthenticated request, never approval."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from foundry.automation_ledger import (
    empty_ledger, record, HISTORIC_A_COMMIT, HISTORIC_A_URL
)
from foundry.github_snapshot import snapshot
from foundry.review_handoff import handoff, main, _load
from tests.test_github_snapshot import sample, PR_HEAD

PROOF_B = "https://github.com/mel2003ru-code/OpDB/commit/" + "b" * 40


def inputs():
    _, ledger = record(empty_ledger(), task_id="FND-009A", action="IMPORT_A",
                       observed_sha=HISTORIC_A_COMMIT, evidence_url=HISTORIC_A_URL)
    _, ledger = record(ledger, task_id="FND-009B", action="CLAIM",
                       observed_sha=PR_HEAD)
    _, ledger = record(ledger, task_id="FND-009B", action="COMPLETE",
                       observed_sha=PR_HEAD, evidence_url=PROOF_B)
    _, ledger = record(ledger, task_id="FND-009C", action="CLAIM",
                       observed_sha=PR_HEAD)
    queue = {
        "schema_version": 1, "repository": "mel2003ru-code/OpDB",
        "issue_number": 31, "pr_number": 32, "security_blocker": 21,
        "items": [
            {"id": "FND-009A", "status": "DONE",
             "evidence_url": HISTORIC_A_URL},
            {"id": "FND-009B", "status": "DONE", "evidence_url": PROOF_B},
            {"id": "FND-009C", "status": "READY", "evidence_url": None},
        ],
    }
    return snapshot(sample(), PR_HEAD), ledger, queue


class ReviewHandoffTests(unittest.TestCase):
    def test_real_request_all_approvals_false(self):
        snap, led, work = inputs()
        result = handoff(snap, led, work, current_sha=PR_HEAD)
        self.assertEqual(result["state"], "REQUEST_INDEPENDENT_REVIEW")
        self.assertEqual(result["ci_observation"], "NO_RUNNER")
        self.assertEqual(len(result["review_requests"]), 2)
        self.assertEqual(
            {r["reviewer_role"] for r in result["review_requests"]},
            {"INDEPENDENT_SAFETY", "INDEPENDENT_QUALITY"})
        self.assertEqual(result["reviewable_code_evidence"]["FND-009A"],
                         HISTORIC_A_URL)
        for field in ("independent_safety_approved", "independent_quality_approved",
                      "github_data_attested", "reviewer_contacted",
                      "reviewer_approval_attested", "ci_attested",
                      "trusted_controller_attested", "worker_execution_authorized",
                      "github_write_authorized", "automatic_merge_allowed",
                      "production_allowed", "launch_authorized",
                      "handoff_published", "digest_is_authentication"):
            self.assertIs(result[field], False)

    def test_exact_sha_mismatch_stops(self):
        snap, led, work = inputs()
        self.assertEqual(handoff(snap, led, work,
                                 current_sha="f" * 40)["state"], "HOLD")

    def test_nonclaimed_task_cannot_forge_handoff(self):
        snap, led, work = inputs()
        led["events"].pop()
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")
        snap, led, work = inputs()
        _, led = record(led, task_id="FND-009C", action="BLOCK",
                        observed_sha=PR_HEAD)
        work["items"][2]["status"] = "BLOCKED"
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")

    def test_changed_ledger_and_worklist_refuse(self):
        snap, led, work = inputs()
        led["events"][2]["evidence_url"] = "https://github.com/attacker/OpDB"
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")
        snap, led, work = inputs()
        work["items"][1]["evidence_url"] = HISTORIC_A_URL
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")

    def test_injected_positive_attestation_refused(self):
        snap, led, work = inputs()
        snap["ci_attested"] = True
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")
        snap, led, work = inputs()
        snap["launch_authorized"] = True
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")

    def test_no_runner_not_mistaken_for_pass(self):
        snap, led, work = inputs()
        output = handoff(snap, led, work, current_sha=PR_HEAD)
        self.assertIn("CI DID NOT EXECUTE", " ".join(output["reasons"]))
        self.assertNotIn("PASS", output["reasons"][-1])

    def test_p0_closed_report_cannot_unblock_lens(self):
        snap, led, work = inputs()
        snap["issue_21_reported_open"] = False
        result = handoff(snap, led, work, current_sha=PR_HEAD)
        self.assertEqual(result["state"], "REQUEST_INDEPENDENT_REVIEW")
        self.assertTrue(result["p0_21_remains_release_blocker"])
        self.assertFalse(result["launch_authorized"])

    def test_malformed_pr_heads_or_run_refs_hold(self):
        snap, led, work = inputs()
        snap["draft_pr_heads"]["32"] = "b" * 40
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")
        snap, led, work = inputs()
        snap["workflow_run_ids"][next(iter(snap["workflow_run_ids"]))] = True
        self.assertEqual(handoff(snap, led, work, current_sha=PR_HEAD)["state"],
                         "HOLD")

    def test_cli_makes_only_new_local_file(self):
        snap, led, work = inputs()
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("snap.json", "led.json", "work.json")]
            for path, data in zip(paths, (snap, led, work)):
                path.write_text(json.dumps(data), encoding="utf-8")
            output = Path(tmp) / "handoff.json"
            args = [
                "--snapshot", str(paths[0]), "--ledger", str(paths[1]),
                "--worklist", str(paths[2]),
                "--expected-sha", PR_HEAD, "--output", str(output)]
            self.assertEqual(main(args), 0)
            self.assertTrue(output.exists())
            self.assertEqual(main(args), 2)  # never overwrite prior handoff
            stored = json.loads(output.read_text(encoding="utf-8"))
            self.assertFalse(stored["reviewer_contacted"])

    def test_loader_rejects_duplicates_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json"
            for raw in (b'{"x":1,"x":2}', b"0" * 101,
                        b'{"n": NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    _load(path, 100)


if __name__ == "__main__":
    unittest.main()
