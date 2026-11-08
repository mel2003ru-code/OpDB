"""OpDB Foundry read-only evidence preflight (research only, never deploys).

The input JSON is self-reported: this code does NOT attest the source or results.
No production, GitHub write, merge or service-management capability is present.
"""
import argparse
import json
import math
import re
import statistics
from pathlib import Path

PEERS = ("PostgreSQL", "MySQL", "SQLite")
WORKLOADS = ("read_heavy", "write_heavy", "mixed_oltp", "contention")
INVARIANTS = (
    "snapshot_identity", "commit_continuity", "external_writes",
    "forged_journal", "schema_plan_invalidation", "crash_recovery",
)
METRICS = ("throughput_ops_s", "p99_ms", "cpu_ms", "peak_ram_mib", "io_mib")
MIN_TRIALS = 7


def _hex(value, length):
    return isinstance(value, str) and bool(
        re.fullmatch("[0-9a-fA-F]{" + str(length) + "}", value)
    )


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _decision(state, reasons, coverage=0):
    return {
        "state": state,
        "pause_autonomous_improvements": state == "PAUSE_FOR_REVIEW",
        "production_allowed": False,
        "automatic_merge_allowed": False,
        "benchmark_pairs_checked": coverage,
        "reasons": reasons,
        "scope": "Self-reported metadata preflight; independent verification REQUIRED",
    }


def _validate_row(row):
    if not _text(row.get("peer_version")):
        return "peer version missing"
    if not _hex(row.get("dataset_sha256"), 64) or not _hex(
        row.get("raw_evidence_sha256"), 64
    ):
        return "dataset or raw evidence digest missing"
    if not _text(row.get("hardware_fingerprint")):
        return "hardware fingerprint missing"
    seeds = row.get("trial_seeds")
    if (not isinstance(seeds, list) or len(seeds) < MIN_TRIALS
            or any(type(seed) is not int for seed in seeds)
            or len(set(seeds)) != len(seeds)):
        return "at least seven distinct integer trial seeds required"
    for engine in ("opdb", "peer_data"):
        sample = row.get(engine)
        if not isinstance(sample, dict):
            return engine + " measurements missing"
        for metric in METRICS:
            values = sample.get(metric)
            if (not isinstance(values, list) or len(values) != len(seeds)
                    or any(type(v) not in (int, float) or not math.isfinite(v)
                           or v <= 0 for v in values)):
                return engine + " invalid " + metric
        if type(sample.get("errors")) is not int or sample["errors"] != 0:
            return engine + " must report zero errors"
    return None


def evaluate(evidence):
    """Pure decision function; no automatic release path in any state."""
    if evidence is None:
        return _decision("NOT_CONFIGURED", ["No admitted OpDB evidence"])
    if (not isinstance(evidence, dict) or type(evidence.get("schema_version")) is not int
            or evidence["schema_version"] != 1):
        return _decision("BLOCKED", ["Unsupported or malformed evidence schema"])
    candidate_sha = evidence.get("candidate_sha")
    if not _hex(candidate_sha, 40):
        return _decision("BLOCKED", ["Exact source commit SHA is required"])
    quality = evidence.get("quality")
    if not isinstance(quality, dict):
        return _decision("NOT_VERIFIED", ["Independent Quality report missing"])
    if quality.get("verdict") == "FAIL":
        return _decision("BLOCKED", ["Quality reports FAIL"])
    if quality.get("verdict") != "PASS":
        return _decision("NOT_VERIFIED", ["Quality verdict is not PASS"])
    if (quality.get("target_sha") != candidate_sha
            or quality.get("independent") is not True
            or not _text(quality.get("environment"))
            or type(quality.get("seed")) is not int
            or not _text(quality.get("run_url"))
            or not quality["run_url"].startswith("https://github.com/")
            or not _hex(quality.get("evidence_sha256"), 64)):
        return _decision("NOT_VERIFIED", ["Quality provenance incomplete or mismatched"])
    invariants = quality.get("invariants")
    if not isinstance(invariants, dict):
        return _decision("NOT_VERIFIED", ["Quality invariant matrix missing"])
    missing = [k for k in INVARIANTS if k not in invariants]
    if missing:
        return _decision("NOT_VERIFIED", ["Missing safety invariants: " + ", ".join(missing)])
    failures = [k for k in INVARIANTS if invariants[k] != "PASS"]
    if failures:
        return _decision("BLOCKED", ["Safety invariants not PASS: " + ", ".join(failures)])
    benchmarks = evidence.get("benchmarks")
    if not isinstance(benchmarks, dict):
        return _decision("CONTINUE_RESEARCH", ["No benchmark evidence"])
    if (benchmarks.get("independent") is not True
            or type(benchmarks.get("independent_repetitions")) is not int
            or benchmarks["independent_repetitions"] < 2
            or not _hex(benchmarks.get("protocol_sha256"), 64)):
        return _decision("NOT_VERIFIED", ["Benchmark provenance or replication incomplete"])
    rows = benchmarks.get("runs")
    if not isinstance(rows, list):
        return _decision("NOT_VERIFIED", ["Benchmark comparison matrix missing"])
    expected = {(p, w) for p in PEERS for w in WORKLOADS}
    observed = {}
    hardware = set()
    workload_inputs = {}
    if len(rows) > len(expected):
        return _decision("NOT_VERIFIED", ["More rows than unique expected workload pairs"])
    for row in rows:
        if not isinstance(row, dict):
            return _decision("NOT_VERIFIED", ["Malformed benchmark row"])
        if type(row.get("peer")) is not str or type(row.get("workload")) is not str:
            return _decision("NOT_VERIFIED", ["Malformed peer or workload identity"])
        key = (row["peer"], row["workload"])
        if key not in expected or key in observed:
            return _decision("NOT_VERIFIED", ["Unknown or repeated benchmark pair"])
        problem = _validate_row(row)
        if problem:
            return _decision("NOT_VERIFIED", [str(key) + ": " + problem])
        fingerprint = (row["dataset_sha256"], tuple(row["trial_seeds"]))
        prior = workload_inputs.setdefault(row["workload"], fingerprint)
        if prior != fingerprint:
            return _decision("NOT_VERIFIED", ["Dataset or paired trial seeds differ across peers for " + row["workload"]])
        observed[key] = row
        hardware.add(row["hardware_fingerprint"])
    if set(observed) != expected:
        return _decision(
            "CONTINUE_RESEARCH",
            ["Incomplete comparison matrix, missing " + str(len(expected - set(observed))) + " pairs"],
            len(observed),
        )
    if len(hardware) != 1:
        return _decision("NOT_VERIFIED", ["Compared runs use different hardware"], len(observed))
    regressions = []
    for key, row in observed.items():
        a, b = row["opdb"], row["peer_data"]
        median_gain = statistics.median(a["throughput_ops_s"]) / statistics.median(
            b["throughput_ops_s"]
        )
        paired_gains = [x / y for x, y in zip(
            a["throughput_ops_s"], b["throughput_ops_s"]
        )]
        if median_gain < 1.20 or min(paired_gains) < 1.10:
            regressions.append(str(key) + " throughput margin insufficient")
        for metric in ("p99_ms", "cpu_ms", "peak_ram_mib", "io_mib"):
            if statistics.median(a[metric]) > statistics.median(b[metric]):
                regressions.append(str(key) + " " + metric + " regression")
    if regressions:
        return _decision("CONTINUE_RESEARCH", regressions, len(observed))
    return _decision(
        "PAUSE_FOR_REVIEW",
        [
            "All 12 self-reported peer/workload pairs meet conservative preflight thresholds",
            "Suspend NEW improvement proposals when an authenticated scheduler consumes this signal; "
            "independently verify raw evidence, recovery/build costs and the scope before any win claim",
        ],
        len(observed),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only metadata gate, NEVER deploys")
    parser.add_argument("--evidence", help="Candidate JSON evidence file")
    parser.add_argument("--output", help="Optional machine-readable decision JSON")
    args = parser.parse_args(argv)
    try:
        evidence = (json.loads(Path(args.evidence).read_text(encoding="utf-8"))
                    if args.evidence else None)
        verdict = evaluate(evidence)
    except (OSError, ValueError, TypeError) as exc:
        verdict = _decision("BLOCKED", [type(exc).__name__ + ": " + str(exc)])
    output = json.dumps(verdict, indent=2, ensure_ascii=False) + "\n"
    print(output, end="")
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    return 2 if verdict["state"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
