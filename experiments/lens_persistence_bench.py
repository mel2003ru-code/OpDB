"""TASK-008: explicit, local-only cold-open benchmark for persisted Lens.

Run: python experiments/lens_persistence_bench.py --sizes 10000 100000 1000000
No production DBs or network. Results are not security attestations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opdb import TruthStore  # noqa: E402


def sample(size: int, root: Path, repeat: int) -> dict:
    path = root / f"m3-{size}.db"
    start = time.perf_counter_ns()
    with TruthStore(path, lens=False) as store:
        for offset in range(0, size, 1000):
            store.apply([
                ("put", f"g{i % 10}/{i:09d}", b"x" * (i % 40))
                for i in range(offset, min(size, offset + 1000))
            ])
    fixture_ms = (time.perf_counter_ns() - start) / 1e6
    start = time.perf_counter_ns()
    with TruthStore(path, lens=True, persist_lens=True) as store:
        first_ms = (time.perf_counter_ns() - start) / 1e6
        if store._lens.loaded_from_disk:
            raise AssertionError("first open incorrectly claims stored checkpoint")
        oracle = store.group_stats_source("g1")
        if store.group_stats("g1").value_bytes != oracle.value_bytes:
            raise AssertionError("First build differs from Source")
    times = []
    for _ in range(repeat):
        start = time.perf_counter_ns()
        with TruthStore(path, lens=True, persist_lens=True) as store:
            times.append((time.perf_counter_ns() - start) / 1e6)
            if not store._lens.loaded_from_disk or not store.lens_enabled:
                raise AssertionError("Expected valid fast persisted reopen")
            data = store.group_stats("g1")
            if (data.row_count, data.value_bytes) != (
                oracle.row_count, oracle.value_bytes
            ):
                raise AssertionError("Restored Lens differs from oracle")
    stats = path.stat()
    return {
        "rows": size, "groups": 10,
        "fixture_ms": round(fixture_ms, 3),
        "first_persistent_build_ms": round(first_ms, 3),
        "reopen_median_ms": round(statistics.median(times), 3),
        "reopen_max_ms": round(max(times), 3),
        "reopens": repeat, "db_bytes_after_close": stats.st_size,
        "checks": "PASS",
        "limitation": "trusted single writer, SQLite-backed research only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+",
                        default=[10000, 100000, 1000000])
    parser.add_argument("--reopens", type=int, default=20)
    opts = parser.parse_args()
    if any(x <= 0 for x in opts.sizes) or not 1 <= opts.reopens <= 100:
        parser.error("size must be positive; reopens must be 1..100")
    try:
        p = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            check=True, timeout=5,
        )
        sha = p.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        sha = "UNKNOWN"
    print(json.dumps({
        "experiment": "M3", "sha": sha, "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version, "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
    }), flush=True)
    with tempfile.TemporaryDirectory(prefix="opdb-m3-bench-") as tmp:
        for size in opts.sizes:
            print(json.dumps(sample(size, Path(tmp), opts.reopens)), flush=True)


if __name__ == "__main__":
    main()
