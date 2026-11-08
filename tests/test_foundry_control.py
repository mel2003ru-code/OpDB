"""Synthetic tests for Foundry preflight. No real DB performance claims."""
import copy
import unittest

from foundry.control import INVARIANTS, PEERS, WORKLOADS, evaluate


def candidate():
    sha = "a" * 40
    runs = []
    for peer in PEERS:
        for workload in WORKLOADS:
            runs.append({
                "peer": peer,
                "peer_version": "synthetic-v0",
                "workload": workload,
                "dataset_sha256": "d" * 64,
                "raw_evidence_sha256": "e" * 64,
                "hardware_fingerprint": "same-synthetic-host",
                "trial_seeds": list(range(7)),
                "opdb": {
                    "throughput_ops_s": [140.0] * 7,
                    "p99_ms": [8.0] * 7,
                    "cpu_ms": [8.0] * 7,
                    "peak_ram_mib": [80.0] * 7,
                    "io_mib": [8.0] * 7,
                    "errors": 0,
                },
                "peer_data": {
                    "throughput_ops_s": [100.0] * 7,
                    "p99_ms": [10.0] * 7,
                    "cpu_ms": [10.0] * 7,
                    "peak_ram_mib": [100.0] * 7,
                    "io_mib": [10.0] * 7,
                    "errors": 0,
                },
            })
    return {
        "schema_version": 1,
        "candidate_sha": sha,
        "quality": {
            "verdict": "PASS", "target_sha": sha, "independent": True,
            "run_url": "https://github.com/example/OpDB/actions/runs/123",
            "environment": "synthetic test only", "seed": 42,
            "evidence_sha256": "c" * 64,
            "invariants": dict.fromkeys(INVARIANTS, "PASS"),
        },
        "benchmarks": {
            "independent": True, "independent_repetitions": 2,
            "protocol_sha256": "b" * 64, "runs": runs,
        },
    }


class FoundryControlTests(unittest.TestCase):
    def assert_state(self, evidence, expected):
        verdict = evaluate(evidence)
        self.assertEqual(verdict["state"], expected, verdict)
        self.assertFalse(verdict["production_allowed"])
        self.assertFalse(verdict["automatic_merge_allowed"])
        self.assertEqual(
            verdict["pause_autonomous_improvements"], expected == "PAUSE_FOR_REVIEW"
        )
        return verdict

    def test_missing_evidence(self):
        self.assert_state(None, "NOT_CONFIGURED")

    def test_unknown_schema(self):
        self.assert_state({"schema_version": 999}, "BLOCKED")

    def test_missing_source_sha(self):
        x = candidate(); x["candidate_sha"] = ""
        self.assert_state(x, "BLOCKED")

    def test_missing_quality(self):
        x = candidate(); del x["quality"]
        self.assert_state(x, "NOT_VERIFIED")

    def test_failed_quality(self):
        x = candidate(); x["quality"]["verdict"] = "FAIL"
        self.assert_state(x, "BLOCKED")

    def test_unverified_quality(self):
        x = candidate(); x["quality"]["independent"] = False
        self.assert_state(x, "NOT_VERIFIED")

    def test_sha_mismatch(self):
        x = candidate(); x["quality"]["target_sha"] = "b" * 40
        self.assert_state(x, "NOT_VERIFIED")

    def test_forged_journal_negative_result_blocks(self):
        x = candidate(); x["quality"]["invariants"]["forged_journal"] = "FAIL"
        self.assert_state(x, "BLOCKED")

    def test_missing_safety_invariant(self):
        x = candidate(); del x["quality"]["invariants"]["crash_recovery"]
        self.assert_state(x, "NOT_VERIFIED")

    def test_no_comparative_data(self):
        x = candidate(); del x["benchmarks"]
        self.assert_state(x, "CONTINUE_RESEARCH")

    def test_missing_pair(self):
        x = candidate(); x["benchmarks"]["runs"].pop()
        self.assert_state(x, "CONTINUE_RESEARCH")

    def test_repeated_pair(self):
        x = candidate()
        x["benchmarks"]["runs"].append(copy.deepcopy(x["benchmarks"]["runs"][0]))
        self.assert_state(x, "NOT_VERIFIED")

    def test_p99_regression(self):
        x = candidate(); x["benchmarks"]["runs"][0]["opdb"]["p99_ms"] = [11.0] * 7
        self.assert_state(x, "CONTINUE_RESEARCH")

    def test_cpu_memory_io_regression(self):
        for metric in ("cpu_ms", "peak_ram_mib", "io_mib"):
            with self.subTest(metric=metric):
                x = candidate()
                x["benchmarks"]["runs"][0]["opdb"][metric] = [200.0] * 7
                self.assert_state(x, "CONTINUE_RESEARCH")

    def test_one_bad_throughput_trial(self):
        x = candidate()
        x["benchmarks"]["runs"][0]["opdb"]["throughput_ops_s"][0] = 101.0
        self.assert_state(x, "CONTINUE_RESEARCH")

    def test_invalid_numeric_values_are_not_verified(self):
        for value in (float("nan"), float("inf"), True, -1.0, 0.0):
            with self.subTest(value=str(value)):
                x = candidate()
                x["benchmarks"]["runs"][0]["opdb"]["throughput_ops_s"][0] = value
                self.assert_state(x, "NOT_VERIFIED")

    def test_duplicate_seeds(self):
        x = candidate(); x["benchmarks"]["runs"][0]["trial_seeds"] = [2] * 7
        self.assert_state(x, "NOT_VERIFIED")

    def test_hardware_must_match(self):
        x = candidate()
        x["benchmarks"]["runs"][0]["hardware_fingerprint"] = "different-host"
        self.assert_state(x, "NOT_VERIFIED")

    def test_missing_raw_digest(self):
        x = candidate()
        x["benchmarks"]["runs"][0]["raw_evidence_sha256"] = None
        self.assert_state(x, "NOT_VERIFIED")

    def test_full_synthetic_fixture_is_review_only(self):
        result = self.assert_state(candidate(), "PAUSE_FOR_REVIEW")
        self.assertEqual(result["benchmark_pairs_checked"], 12)
        self.assertIn("self-reported", result["scope"].lower())

    def test_untrusted_flags_cannot_authorize_deployment(self):
        x = candidate()
        x["production_approved"] = True
        x["staging"] = {"passed": True, "rollback_passed": True}
        self.assertFalse(evaluate(x)["production_allowed"])

    def test_deterministic(self):
        x = candidate()
        self.assertEqual(evaluate(x), evaluate(copy.deepcopy(x)))


if __name__ == "__main__":
    unittest.main()
