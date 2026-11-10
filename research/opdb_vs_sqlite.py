"""LAB-001: SQLite-backed OpDB Source/Lens vs direct sqlite3 aggregate.

Research experiment, NOT a comparison of independent database engines.
Run from repo root: python -m research.opdb_vs_sqlite --sizes 10000 100000 1000000
Only stdlib; no network, no privileged writes, no production data.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

from opdb import TruthStore


def checked_out_sha() -> str:
    """Use actual checkout, not stale GITHUB_SHA on rerun attempts."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            text=True, capture_output=True, check=False, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    sha = proc.stdout.strip()
    return sha if proc.returncode == 0 and len(sha) == 40 else "UNKNOWN"


def raw_sqlite_stats(db: sqlite3.Connection, group: str) -> tuple[int, int]:
    """Aggregate in SQL, not by calling any OpDB or Lens method."""
    count, total = db.execute(
        "SELECT count(*),coalesce(sum(length(v)),0) "
        "FROM opdb_source_kv WHERE k=? COLLATE BINARY OR "
        "(k>=? COLLATE BINARY AND k<? COLLATE BINARY)",
        (group, group + "/", group + "0"),
    ).fetchone()
    return int(count), int(total)


def generated_rows(size: int, seed: int, groups: int = 10):
    rng = random.Random(seed)
    for index in range(size):
        key = f"g{index % groups}/{index:09d}"
        value = bytes((rng.randrange(256),)) * rng.randrange(65)
        yield key, value


def build_fixture(path: Path, size: int, seed: int) -> dict[str, tuple[int, int]]:
    """Write typed fixtures via public OpDB API; track a Python oracle."""
    expected: dict[str, list[int]] = {}
    with TruthStore(path, lens=False) as store:
        batch = []
        for key, value in generated_rows(size, seed):
            group = key.split("/", 1)[0]
            pair = expected.setdefault(group, [0, 0])
            pair[0] += 1
            pair[1] += len(value)
            batch.append(("put", key, value))
            if len(batch) == 1000:
                store.apply(batch)
                batch.clear()
        if batch:
            store.apply(batch)
    return {group: (pair[0], pair[1]) for group, pair in expected.items()}


def distribution_ns(samples: list[int]) -> dict[str, float]:
    if not samples:
        raise ValueError("No timing samples")
    ordered = sorted(samples)
    return {
        "median_us": round(statistics.median(ordered) / 1000, 3),
        "p95_us": round(ordered[math.ceil(len(ordered) * 0.95) - 1] / 1000, 3),
        "p99_us": round(ordered[math.ceil(len(ordered) * 0.99) - 1] / 1000, 3),
    }


def db_files_bytes(path: Path) -> dict[str, int]:
    """Measured after closing connections; WAL may have been checkpointed."""
    return {
        suffix or "db": (Path(str(path) + suffix).stat().st_size
                         if Path(str(path) + suffix).exists() else 0)
        for suffix in ("", "-wal", "-shm")
    }


def run_case(root: Path, size: int, seed: int, reads: int = 100,
             group: str = "g1") -> dict:
    if size < 1 or reads < 5:
        raise ValueError("size >= 1 and reads >= 5 required")
    path = root / f"lab001-{size}-{seed}.db"
    if path.exists():
        raise ValueError(f"Refusing to overwrite existing fixture: {path}")
    start = time.perf_counter_ns()
    model = build_fixture(path, size, seed)
    construction_ms = (time.perf_counter_ns() - start) / 1e6

    source = lens = raw = None
    try:
        start = time.perf_counter_ns()
        source = TruthStore(path, lens=False)
        source_open_ms = (time.perf_counter_ns() - start) / 1e6
        start = time.perf_counter_ns()
        lens = TruthStore(path, lens=True)
        lens_open_ms = (time.perf_counter_ns() - start) / 1e6
        start = time.perf_counter_ns()
        raw = sqlite3.connect(path, cached_statements=0)
        raw_open_ms = (time.perf_counter_ns() - start) / 1e6

        oracle = model.get(group, (0, 0))
        from_source = source.group_stats_source(group)
        from_lens = lens.group_stats(group)
        from_sql = raw_sqlite_stats(raw, group)
        source_pair = (from_source.row_count, from_source.value_bytes)
        lens_pair = (from_lens.row_count, from_lens.value_bytes)
        if not (oracle == source_pair == lens_pair == from_sql):
            raise AssertionError(
                f"Oracle mismatch: python={oracle}, source={source_pair}, "
                f"lens={lens_pair}, sqlite={from_sql}"
            )
        if from_source.served_from != "SOURCE" or from_lens.served_from != "LENS":
            raise AssertionError("Unexpected read path: not actually testing Lens")

        methods = {
            "opdb_source": lambda: source.group_stats_source(group),
            "opdb_lens": lambda: lens.group_stats(group),
            "sqlite_direct": lambda: raw_sqlite_stats(raw, group),
        }
        samples = {name: [] for name in methods}
        names = list(methods)
        for index in range(reads):
            # Rotate order to reduce systematic warm-cache position bias.
            for name in names[index % len(names):] + names[:index % len(names)]:
                started = time.perf_counter_ns()
                result = methods[name]()
                elapsed = time.perf_counter_ns() - started
                got = (result.row_count, result.value_bytes) if name != "sqlite_direct" else result
                if got != oracle:
                    raise AssertionError(f"Changed answer during read loop: {name}")
                samples[name].append(elapsed)
        return {
            "rows": size,
            "group": group,
            "group_expected": {"count": oracle[0], "value_bytes": oracle[1]},
            "checks": {"python_vs_opdb_source_vs_lens_vs_sqlite": "PASS",
                       "lens_served_from": from_lens.served_from},
            "construction_ms": round(construction_ms, 3),
            "open_ms": {
                "opdb_source": round(source_open_ms, 3),
                "opdb_lens_includes_full_rebuild": round(lens_open_ms, 3),
                "sqlite_direct": round(raw_open_ms, 3),
            },
            "reads_per_mode": reads,
            "read_latency": {name: distribution_ns(times)
                             for name, times in samples.items()},
        }
    finally:
        if raw is not None:
            raw.close()
        if lens is not None:
            lens.close()
        if source is not None:
            source.close()



def write_comparison(root: Path, size: int, seed: int, *,
                     batches: int = 12, batch_size: int = 1000,
                     workload: str = "overwrite") -> dict:
    """Compare identical committed batches; do not include fixture setup in timing."""
    if workload not in ("append", "overwrite") or size < batch_size:
        raise ValueError("Unsupported workload or insufficient initial rows")
    if not 1 <= batch_size <= 1000 or not 1 <= batches <= 60:
        raise ValueError("Bound batch sizes/counts")
    base = root / f"write-base-{workload}-{size}-{seed}.db"
    expected = {g: list(p) for g, p in build_fixture(base, size, seed).items()}
    old: dict[str, int] = {}
    if workload == "overwrite":
        with sqlite3.connect(base) as raw:
            for index in range(batch_size):
                key = f"g{index % 10}/{index:09d}"
                row = raw.execute(
                    "SELECT length(v) FROM opdb_source_kv WHERE k=?", (key,)
                ).fetchone()
                if row is None:
                    raise AssertionError("Missing initial overwrite key")
                old[key] = row[0]
    rng = random.Random(seed + 99)
    work = []
    for batch in range(batches):
        operations = []
        for index in range(batch_size):
            key = (f"new/{batch:06d}/{index:06d}" if workload == "append"
                   else f"g{index % 10}/{index:09d}")
            value = bytes((rng.randrange(256),)) * rng.randrange(65)
            group = key.split("/", 1)[0]
            pair = expected.setdefault(group, [0, 0])
            previous = old.get(key)
            if previous is None:
                pair[0] += 1
            else:
                pair[1] -= previous
            pair[1] += len(value)
            old[key] = len(value)
            operations.append(("put", key, value))
        work.append(operations)

    readings = {}
    for mode in ("source", "lens", "sqlite_direct"):
        target = root / f"write-{workload}-{size}-{seed}-{mode}.db"
        shutil.copyfile(base, target)
        samples = []
        started = time.perf_counter_ns()
        if mode == "sqlite_direct":
            connection = sqlite3.connect(
                target, isolation_level=None, cached_statements=0
            )
            try:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute("PRAGMA synchronous=FULL")
                open_ms = (time.perf_counter_ns() - started) / 1e6
                for operations in work:
                    start = time.perf_counter_ns()
                    connection.execute("BEGIN IMMEDIATE")
                    try:
                        for _, key, value in operations:
                            connection.execute(
                                "INSERT INTO opdb_source_kv(k,v) VALUES (?,?) "
                                "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                                (key, value),
                            )
                        connection.execute(
                            "UPDATE opdb_meta SET commit_seq=commit_seq+1 "
                            "WHERE singleton=1"
                        )
                        connection.execute("COMMIT")
                    except BaseException:
                        connection.execute("ROLLBACK")
                        raise
                    samples.append(time.perf_counter_ns() - start)
                for group, pair in expected.items():
                    if raw_sqlite_stats(connection, group) != tuple(pair):
                        raise AssertionError(f"SQLite write mismatch: {group}")
            finally:
                connection.close()
        else:
            store = TruthStore(target, lens=(mode == "lens"))
            try:
                open_ms = (time.perf_counter_ns() - started) / 1e6
                for operations in work:
                    start = time.perf_counter_ns()
                    store.apply(operations)
                    samples.append(time.perf_counter_ns() - start)
                for group, pair in expected.items():
                    source = store.group_stats_source(group)
                    answer = store.group_stats(group)
                    for result in (source, answer):
                        if (result.row_count, result.value_bytes) != tuple(pair):
                            raise AssertionError(f"{mode} write mismatch: {group}")
                if mode == "lens" and not store.lens_enabled:
                    raise AssertionError("Lens silently disabled after writes")
            finally:
                store.close()
        readings[mode] = {
            "open_ms": round(open_ms, 3),
            "batch_latency": distribution_ns(samples),
        }
    return {
        "rows": size, "batches": batches, "batch_size": batch_size,
        "workload": workload, "oracle": "Python model + independent SQL/Source",
        "checks": "PASS", "modes": readings,
        "limitation": "All three use SQLite; direct SQL performs fewer API checks",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 100000, 1000000])
    parser.add_argument("--seed", type=int, default=1729)
    parser.add_argument("--reads", type=int, default=100)
    parser.add_argument("--group", default="g1")
    args = parser.parse_args()
    if any(size < 1 for size in args.sizes) or args.reads < 5:
        parser.error("sizes must be positive and reads >= 5")
    print(json.dumps({
        "experiment": "LAB-001", "scope": "SQLite-backed OpDB vs direct SQLite; not native DBMS",
        "checked_out_sha": checked_out_sha(), "seed": args.seed,
        "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(), "logical_cpus": os.cpu_count(),
        "workload": "identical typed KV, warmed aggregate reads; no write benchmark",
        "limitation": "SQLite baseline does not perform OpDB integrity validation",
    }), flush=True)
    with tempfile.TemporaryDirectory(prefix="opdb-lab001-") as directory:
        root = Path(directory)
        for size in args.sizes:
            row = run_case(root, size, args.seed, args.reads, args.group)
            path = root / f"lab001-{size}-{args.seed}.db"
            row["files_bytes_after_close"] = db_files_bytes(path)
            print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()
