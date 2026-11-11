"""S-008B-2 RED tests: prototype contract, NOT independently trusted CI.

Only synthetic bytes and ephemeral SQLite. Never runs Docker, worker or candidate.
"""
import copy
import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest

from foundry import s008b2_protocol as protocol

REPO = "mel2003ru-code/OpDB"
SHA = "a" * 40
POLICY = "b" * 64
IMAGE = "sha256:" + "c" * 64
KEY = b"synthetic-test-controller-key-not-a-real-secret-" * 2
NOW = 1794140000
REQUEST = {"operation": "PROPOSE_TEXT_ONLY", "source_sha": SHA,
           "task_key": "demo-add-v1", "issue_number": 31,
           "execution_allowed": False, "github_write_allowed": False}


def make_envelope(**changes):
    fields = {
        "request": REQUEST,
        "repo": REPO,
        "policy_sha256": POLICY,
        "image_digest": IMAGE,
        "key": KEY,
        "issued_at": NOW - 10,
        "expires_at": NOW + 30,
        "nonce": "d" * 32,
    }
    fields.update(changes)
    return protocol.build_challenge(**fields)


def guest_report(envelope):
    challenge = envelope["challenge"]
    return json.dumps({
        "probe": "fixed-data-only-handoff-s008",
        "session_nonce": challenge["nonce"],
        "request_sha256": challenge["request_sha256"],
        "passed": True,
        "reply": {"candidate_text": "UNTRUSTED TEST DATA ONLY"},
        "launch_authorized": False,
        "github_write_allowed": False,
        "model_invoked": False,
        "arbitrary_model_code_executed": False,
        "trusted_controller_attested": False,
    }, sort_keys=True).encode()


class ProtocolS008B2Tests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        protocol.initialize_ledger(self.db)

    def check(self, envelope=None, report=None, **overrides):
        envelope = make_envelope() if envelope is None else envelope
        report = guest_report(envelope) if report is None else report
        args = {
            "repo": REPO, "source_sha": SHA, "policy_sha256": POLICY,
            "image_digest": IMAGE, "request": REQUEST, "key": KEY,
            "now": NOW, "ledger": self.db,
        }
        args.update(overrides)
        return protocol.admit_result(envelope, report, **args)

    def test_signed_challenge_yields_only_quarantined_evidence(self):
        envelope = make_envelope()
        result = self.check(envelope)
        self.assertEqual(result["state"], "QUARANTINED_FOR_REVIEW")
        self.assertFalse(result["trusted_controller_attested"])
        self.assertFalse(result["launch_authorized"])
        self.assertFalse(result["github_write_allowed"])
        self.assertFalse(result["automatic_merge_allowed"])
        self.assertFalse(result["production_allowed"])
        self.assertTrue(protocol.verify_receipt(result["receipt"], KEY,
                                                 hashlib.sha256(guest_report(envelope)).hexdigest()))
        self.assertFalse(protocol.verify_receipt(result["receipt"], b"different-key",
                                                  result["response_sha256"]))

    def test_replay_is_one_use_even_with_identical_authenticated_message(self):
        envelope = make_envelope()
        self.assertEqual(self.check(envelope)["state"], "QUARANTINED_FOR_REVIEW")
        self.assertEqual(self.check(envelope)["state"], "BLOCKED")

    def test_tamper_wrong_key_policy_image_repo_and_commit_fail(self):
        e = make_envelope()
        for field, altered in (
            ("source_sha", "f" * 40), ("request_sha256", "0" * 64),
            ("policy_sha256", "1" * 64), ("image_digest", "sha256:" + "2" * 64),
            ("repo", "attacker/OpDB"), ("nonce", "0" * 32),
            ("expires_at", NOW + 2000),
        ):
            with self.subTest(field=field):
                tampered = copy.deepcopy(e)
                tampered["challenge"][field] = altered
                self.assertEqual(self.check(tampered)["state"], "BLOCKED")
        self.assertEqual(self.check(e, key=b"bad-key")["state"], "BLOCKED")
        self.assertEqual(self.check(e, repo="wrong/repo")["state"], "BLOCKED")
        self.assertEqual(self.check(e, policy_sha256="0" * 64)["state"], "BLOCKED")
        self.assertEqual(self.check(e, image_digest="sha256:"+"0"*64)["state"], "BLOCKED")
        self.assertEqual(self.check(e, source_sha="f"*40)["state"], "BLOCKED")
        self.assertEqual(self.check(e, request={"other":"task"})["state"], "BLOCKED")

    def test_expiry_future_issue_and_permissive_challenge_fail_closed(self):
        for kwargs in (
            {"issued_at": NOW - 200, "expires_at": NOW - 100},
            {"issued_at": NOW + 1, "expires_at": NOW + 30},
            {"issued_at": NOW - 1, "expires_at": NOW + 500},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.check(make_envelope(**kwargs))["state"], "BLOCKED")
        for mutation in (
            {"execution_allowed": True},
            {"github_write_allowed": True},
            {"max_model_requests": 1},
        ):
            with self.subTest(mutation=mutation):
                req = dict(REQUEST, **mutation)
                with self.assertRaises(ValueError):
                    make_envelope(request=req)

    def test_duplicate_json_oversize_wrong_echo_and_worker_claims_fail(self):
        e = make_envelope()
        valid = guest_report(e)
        cases = (
            b'{"session_nonce":"a","session_nonce":"b"}',
            valid + b'\n' + valid,
            b" " * 17000,
            valid.replace(b'"passed": true', b'"passed": false'),
            valid.replace(e["challenge"]["nonce"].encode(), b"0" * 32),
            valid.replace(b'"launch_authorized": false', b'"launch_authorized": true'),
            valid.replace(b'"reply": {', b'"reply": null, "ignored": {'),
        )
        for case in cases:
            with self.subTest(sample=case[:50]):
                self.assertEqual(self.check(e, case)["state"], "BLOCKED")

    def test_receipt_authentication_rejects_modified_evidence(self):
        result = self.check()
        receipt = copy.deepcopy(result["receipt"])
        receipt["body"]["response_sha256"] = "0" * 64
        self.assertFalse(protocol.verify_receipt(receipt, KEY, result["response_sha256"]))
        receipt = copy.deepcopy(result["receipt"])
        receipt["mac"] = "0" * 64
        self.assertFalse(protocol.verify_receipt(receipt, KEY, result["response_sha256"]))

    def test_fail_closed_on_uninitialized_replay_ledger(self):
        bad = sqlite3.connect(":memory:")
        self.addCleanup(bad.close)
        self.assertEqual(self.check(ledger=bad)["state"], "BLOCKED")

    def test_strict_wire_decode_rejects_duplicate_nested_keys(self):
        e = make_envelope()
        self.assertEqual(self.check(e, b'{"a":{"x":1,"x":2}}')["state"], "BLOCKED")

    def test_cross_connection_competing_replays_accept_at_most_one(self):
        envelope = make_envelope()
        report = guest_report(envelope)
        with tempfile.TemporaryDirectory(prefix="opdb-s008b2-test-") as tmp:
            database = tmp + "/ledger.sqlite3"
            with sqlite3.connect(database) as setup:
                protocol.initialize_ledger(setup)
            ready = threading.Barrier(2)
            outcomes = []
            def worker():
                with sqlite3.connect(database, timeout=5) as connection:
                    ready.wait(timeout=5)
                    decision = protocol.admit_result(
                        envelope, report, repo=REPO, source_sha=SHA,
                        policy_sha256=POLICY, image_digest=IMAGE,
                        request=REQUEST, key=KEY, now=NOW, ledger=connection)
                    outcomes.append(decision["state"])
            tasks = [threading.Thread(target=worker) for _ in range(2)]
            for task in tasks:
                task.start()
            for task in tasks:
                task.join(timeout=10)
                self.assertFalse(task.is_alive())
        self.assertCountEqual(outcomes, ["QUARANTINED_FOR_REVIEW", "BLOCKED"])

    def test_committed_nonce_survives_controller_restart_and_blocks_retry(self):
        envelope = make_envelope()
        with tempfile.TemporaryDirectory(prefix="opdb-s008b2-restart-") as tmp:
            database = tmp + "/ledger.sqlite3"
            with sqlite3.connect(database) as first:
                protocol.initialize_ledger(first)
                self.assertEqual(
                    self.check(envelope, ledger=first)["state"],
                    "QUARANTINED_FOR_REVIEW")
            with sqlite3.connect(database) as restarted:
                self.assertEqual(
                    self.check(envelope, ledger=restarted)["state"], "BLOCKED")

    def test_guest_data_is_not_correctness_or_isolation_attestation(self):
        envelope = make_envelope()
        payload = json.loads(guest_report(envelope))
        payload["reply"]["candidate_text"] = "MALICIOUS BUT JUST DATA"
        payload["checked"] = {"root_filesystem_read_only": True}
        result = self.check(envelope, json.dumps(payload).encode())
        self.assertEqual(result["state"], "QUARANTINED_FOR_REVIEW")
        self.assertFalse(result["trusted_controller_attested"])
        self.assertFalse(result["launch_authorized"])
        self.assertFalse(result["production_allowed"])

    def test_signed_challenge_has_no_exported_key(self):
        envelope = make_envelope()
        self.assertEqual(set(envelope), {"challenge", "mac"})
        self.assertNotIn(KEY.decode(), json.dumps(envelope))


if __name__ == "__main__":
    unittest.main()
