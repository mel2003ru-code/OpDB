"""S-009A GitHub snapshot tests: deterministic, no network or credentials."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from foundry.github_snapshot import _load, main, snapshot, WORKFLOWS

PR_HEAD = "a" * 40
MAIN_HEAD = "b" * 40
CORE_HEAD = "c" * 40
QUALITY_HEAD = "d" * 40


def sample():
    def pr(num, head, ref, base, base_ref):
        return {
            "number": num, "state": "open", "draft": True, "merged": False,
            "head": {"sha": head, "ref": ref},
            "base": {"sha": base, "ref": base_ref},
        }

    runs = []
    jobs = {}
    for i, name in enumerate(WORKFLOWS):
        run_id = 900 + i
        runs.append({"id": run_id, "name": name, "status": "completed",
                     "conclusion": "failure", "head_sha": PR_HEAD})
        jobs[str(run_id)] = [{"run_id": run_id, "runner_id": 0,
                              "steps": [], "conclusion": "failure"}]
    return {
        "schema_version": 1,
        "repository": {"full_name": "mel2003ru-code/OpDB"},
        "main": {"name": "main", "commit": {"sha": MAIN_HEAD}, "protected": False},
        "pulls": [
            pr(32, PR_HEAD, "foundry/guarded-loop-gate-0-1", MAIN_HEAD, "main"),
            pr(33, CORE_HEAD, "core/source-only-truthstore-0-1", MAIN_HEAD, "main"),
            pr(34, QUALITY_HEAD, "quality/core-boundary-falsification-20261108",
               CORE_HEAD, "core/source-only-truthstore-0-1"),
        ],
        "issues": [{"number": 21, "state": "open"},
                   {"number": 31, "state": "open"}],
        "runs": runs,
        "jobs": jobs,
    }


class GitHubSnapshotTests(unittest.TestCase):
    def test_no_runner_failure_is_not_a_test_failure(self):
        result = snapshot(sample(), PR_HEAD)
        self.assertEqual(result["state"], "READ_ONLY_SNAPSHOT")
        self.assertEqual(result["ci_state"], "NO_RUNNER")
        self.assertTrue(result["lens_blocked"])
        self.assertEqual(set(result["workflow_run_ids"].values()), {900, 901, 902})
        for key in ("github_data_attested", "ci_attested",
                    "task_execution_authorized", "github_write_authorized",
                    "automatic_merge_allowed", "trusted_controller_attested",
                    "launch_authorized", "digest_is_authentication"):
            self.assertIs(result[key], False)

    def test_changed_pr_head_stops_snapshot(self):
        self.assertEqual(snapshot(sample(), "e" * 40)["state"], "HOLD_SNAPSHOT")

    def test_stacked_pr_out_of_sync_stops_snapshot(self):
        payload = sample()
        payload["pulls"][2]["base"]["sha"] = MAIN_HEAD
        self.assertEqual(snapshot(payload, PR_HEAD)["state"], "HOLD_SNAPSHOT")

    def test_spoofed_repository_fails_closed(self):
        payload = sample()
        payload["repository"]["full_name"] = "attacker/OpDB"
        self.assertEqual(snapshot(payload, PR_HEAD)["state"], "HOLD_SNAPSHOT")

    def test_executed_failure_is_distinguished(self):
        payload = sample()
        payload["jobs"]["900"] = [{"run_id": 900, "runner_id": 123,
                                     "steps": [{"name": "unittest"}],
                                     "conclusion": "failure"}]
        self.assertEqual(snapshot(payload, PR_HEAD)["ci_state"], "FAIL_EXECUTED")

    def test_green_requires_real_jobs_not_only_run_conclusion(self):
        payload = sample()
        for run in payload["runs"]:
            run["conclusion"] = "success"
            payload["jobs"][str(run["id"])] = [{
                "run_id": run["id"], "runner_id": 250,
                "steps": [{"name": "tests", "conclusion": "success"}],
                "conclusion": "success",
            }]
        result = snapshot(payload, PR_HEAD)
        self.assertEqual(result["ci_state"], "PASS")
        self.assertFalse(result["ci_attested"])

    def test_unknown_without_job_rows(self):
        payload = sample()
        payload["jobs"] = {}
        self.assertEqual(snapshot(payload, PR_HEAD)["ci_state"], "UNKNOWN")

    def test_missing_expected_workflow_yields_unknown(self):
        payload = sample()
        payload["runs"].pop()
        self.assertEqual(snapshot(payload, PR_HEAD)["ci_state"], "UNKNOWN")

    def test_closed_p0_never_authorizes_lens(self):
        payload = sample()
        payload["issues"][0]["state"] = "closed"
        result = snapshot(payload, PR_HEAD)
        self.assertFalse(result["issue_21_reported_open"])
        self.assertTrue(result["lens_blocked"])

    def test_rejected_malformed_and_boolean_ids(self):
        payload = sample()
        payload["pulls"][0]["number"] = True
        self.assertEqual(snapshot(payload, PR_HEAD)["state"], "HOLD_SNAPSHOT")
        payload = sample()
        payload["issues"].append({"number": 31, "state": "open"})
        self.assertEqual(snapshot(payload, PR_HEAD)["state"], "HOLD_SNAPSHOT")
        payload = sample()
        payload["jobs"]["900"][0]["runner_id"] = False
        self.assertEqual(snapshot(payload, PR_HEAD)["ci_state"], "UNKNOWN")

    def test_latest_run_selected_by_id_not_input_order(self):
        payload = sample()
        payload["runs"].insert(0, {
            "id": 899, "name": WORKFLOWS[0], "status": "completed",
            "conclusion": "success", "head_sha": PR_HEAD,
        })
        payload["jobs"]["899"] = [{
            "run_id": 899, "runner_id": 44, "steps": [{"name": "tests"}],
            "conclusion": "success",
        }]
        result = snapshot(payload, PR_HEAD)
        self.assertEqual(result["workflow_run_ids"][WORKFLOWS[0]], 900)

    def test_loader_and_cli_reject_duplicated_json_and_oversize(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            out = Path(tmp) / "output.json"
            path.write_text(json.dumps(sample()), encoding="utf-8")
            self.assertEqual(main(["--input", str(path), "--expected-sha",
                                   PR_HEAD, "--output", str(out)]), 0)
            verdict = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(verdict["ci_state"], "NO_RUNNER")
            for raw in (b'{"x":1,"x":2}', b"x" * (256 * 1024 + 1)):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    _load(path)
            path.write_text('{"x": NaN}', encoding="utf-8")
            with self.assertRaises(ValueError):
                _load(path)


if __name__ == "__main__":
    unittest.main()
