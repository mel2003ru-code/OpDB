"""Offline repeatability, concurrency protocol and damage detection for S-009B."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from foundry.automation_ledger import (
    empty_ledger, record, reconcile, validate, load, main,
    HISTORIC_A_COMMIT, HISTORIC_A_URL,
)

HEAD = "a" * 40
LINK_B = "https://github.com/mel2003ru-code/OpDB/commit/" + "b" * 40
LINK_C = "https://github.com/mel2003ru-code/OpDB/commit/" + "c" * 40


def seeded():
    result, ledger = record(empty_ledger(), task_id="FND-009A", action="IMPORT_A",
                            observed_sha=HISTORIC_A_COMMIT, evidence_url=HISTORIC_A_URL)
    assert result["state"] == "RECORDED"
    return ledger


def queue(status="READY", proof=None):
    return {"schema_version": 1, "repository": "mel2003ru-code/OpDB",
            "pr_number": 32, "issue_number": 31, "security_blocker": 21,
            "items": [{"id": "FND-009A", "status": "DONE", "evidence_url": HISTORIC_A_URL},
                      {"id": "FND-009B", "status": status, "evidence_url": proof},
                      {"id": "FND-009C", "status": "READY", "evidence_url": None}]}


class AutomationLedgerTests(unittest.TestCase):
    def test_historic_import_bounded_and_idempotent(self):
        ledger = seeded()
        self.assertEqual(validate(ledger)["FND-009A"], "DONE")
        d, same = record(ledger, task_id="FND-009A", action="IMPORT_A",
                         observed_sha=HEAD, evidence_url=HISTORIC_A_URL)
        self.assertEqual(d["state"], "ALREADY_DONE")
        self.assertIsNone(same)
        self.assertFalse(d["github_write_authorized"])
        self.assertFalse(d["launch_authorized"])

    def test_claim_once_across_restart(self):
        ledger = seeded()
        d, claimed = record(ledger, task_id="FND-009B", action="CLAIM",
                            observed_sha=HEAD)
        self.assertEqual(d["state"], "RECORDED")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(json.dumps(claimed))
            fresh = load(path)
        self.assertEqual(validate(fresh)["FND-009B"], "CLAIMED")
        d, duplicate = record(fresh, task_id="FND-009B", action="CLAIM",
                              observed_sha="e" * 40)
        self.assertEqual(d["state"], "ALREADY_CLAIMED")
        self.assertIsNone(duplicate)

    def test_complete_then_skip_duplicate(self):
        ledger = seeded()
        _, claimed = record(ledger, task_id="FND-009B", action="CLAIM",
                            observed_sha=HEAD)
        d, done = record(claimed, task_id="FND-009B", action="COMPLETE",
                         observed_sha=HEAD, evidence_url=LINK_B)
        self.assertEqual(d["state"], "RECORDED")
        self.assertEqual(validate(done)["FND-009B"], "DONE")
        d, new = record(done, task_id="FND-009B", action="COMPLETE",
                        observed_sha="f" * 40, evidence_url=LINK_B)
        self.assertEqual(d["state"], "ALREADY_DONE")
        self.assertIsNone(new)
        d, new = record(done, task_id="FND-009B", action="COMPLETE",
                        observed_sha=HEAD, evidence_url=LINK_C)
        self.assertEqual(d["state"], "HOLD_CONFLICT")
        self.assertIsNone(new)
        self.assertEqual(done["events"][-1]["evidence_url"], LINK_B)

    def test_no_skipping_dependencies_or_claim(self):
        ledger = seeded()
        for action in ("CLAIM", "COMPLETE"):
            d, new = record(ledger, task_id="FND-009C", action=action,
                            observed_sha=HEAD,
                            evidence_url=LINK_C if action == "COMPLETE" else None)
            self.assertTrue(d["state"].startswith("HOLD"))
            self.assertIsNone(new)
        d, _ = record(ledger, task_id="FND-009B", action="COMPLETE",
                      observed_sha=HEAD, evidence_url=LINK_B)
        self.assertEqual(d["state"], "HOLD_NOT_CLAIMED")

    def test_blocked_claim_stays_blocked(self):
        _, claimed = record(seeded(), task_id="FND-009B", action="CLAIM",
                            observed_sha=HEAD)
        _, blocked = record(claimed, task_id="FND-009B", action="BLOCK",
                            observed_sha=HEAD)
        self.assertEqual(validate(blocked)["FND-009B"], "BLOCKED")
        d, _ = record(blocked, task_id="FND-009B", action="CLAIM",
                      observed_sha=HEAD)
        self.assertEqual(d["state"], "HOLD_BLOCKED")

    def test_hash_chain_detects_mutation(self):
        ledger = seeded()
        for patch in (lambda l: l["events"][0].update(state="CLAIMED"),
                      lambda l: l.update(head_sha256="f" * 64),
                      lambda l: l["events"][0].update(observed_sha="e" * 40)):
            bad = copy.deepcopy(ledger)
            patch(bad)
            with self.assertRaises(ValueError):
                validate(bad)

    def test_strict_schema_and_bool_alias_rejected(self):
        for replacement in (True, "1", 2):
            bad = seeded()
            bad["events"][0]["seq"] = replacement
            with self.assertRaises(ValueError):
                validate(bad)
        bad = seeded()
        bad["new_unauthorized_field"] = "run-now"
        with self.assertRaises(ValueError):
            validate(bad)

    def test_reconciliation_detects_progress_divergence(self):
        led = seeded()
        self.assertEqual(reconcile(led, queue())["state"], "CONSISTENT_ADVISORY")
        _, claim = record(led, task_id="FND-009B", action="CLAIM",
                          observed_sha=HEAD)
        self.assertEqual(reconcile(claim, queue())["state"], "CONSISTENT_ADVISORY")
        _, done = record(claim, task_id="FND-009B", action="COMPLETE",
                         observed_sha=HEAD, evidence_url=LINK_B)
        self.assertEqual(reconcile(done, queue())["state"], "HOLD_SYNC")
        self.assertEqual(reconcile(done, queue("DONE", LINK_B))["state"],
                         "CONSISTENT_ADVISORY")

    def test_wrong_evidence_and_overlong_ledger_refused(self):
        led = seeded()
        for link in ("https://github.com/other/OpDB/commit/" + "f" * 40,
                     "https://github.com/mel2003ru-code/OpDB/pull/32"):
            _, claimed = record(led, task_id="FND-009B", action="CLAIM",
                                observed_sha=HEAD)
            d, changed = record(claimed, task_id="FND-009B", action="COMPLETE",
                                observed_sha=HEAD, evidence_url=link)
            self.assertEqual(d["state"], "HOLD_INVALID")
            self.assertIsNone(changed)

    def test_local_cli_never_overwrites_existing_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            path.write_text(json.dumps(seeded()), encoding="utf-8")
            before = path.read_bytes()
            self.assertEqual(main(["--ledger", str(path), "--output", str(path),
                                   "--task-id", "FND-009B", "--action", "CLAIM",
                                   "--observed-sha", HEAD]), 2)
            self.assertEqual(path.read_bytes(), before)
            output = Path(tmp) / "next.json"
            self.assertEqual(main(["--ledger", str(path), "--output", str(output),
                                   "--task-id", "FND-009B", "--action", "CLAIM",
                                   "--observed-sha", HEAD]), 0)
            self.assertEqual(validate(load(output))["FND-009B"], "CLAIMED")
            self.assertEqual(path.read_bytes(), before)

    def test_duplicate_and_oversize_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for raw in (b'{"x":1,"x":2}', b"x" * (16 * 1024 + 1),
                        b'{"value":NaN}'):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    load(path)


if __name__ == "__main__":
    unittest.main()
