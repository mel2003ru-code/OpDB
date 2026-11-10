"""TASK-006/007 local-file Lens vs Source microbench; no cross-engine claims.

Run: python experiments/lens_bench.py [--sizes 10000 100000 1000000]
"""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opdb import TruthStore


def percentiles(samples):
    values = sorted(samples)
    return {"median_us": round(statistics.median(values) / 1000, 2),
            "p99_us": round(values[min(len(values) - 1,
                                       max(0, (99 * len(values) + 99) // 100 - 1))] / 1000, 2)}


def timed_reads(store, method, group, count):
    samples = []
    for _ in range(count):
        start = time.perf_counter_ns()
        result = method(group)
        samples.append(time.perf_counter_ns() - start)
        if result.row_count < 0:
            raise AssertionError("negative count")
    return percentiles(samples)


def write_rates(path, enabled, puts, batches):
    with TruthStore(path, lens=enabled) as store:
        start = time.perf_counter()
        for i in range(puts):
            store.put(f'bench/{i:08d}', b'a' * 100)
        put_rate = puts / (time.perf_counter() - start)
        start = time.perf_counter()
        batch_times = []
        for batch in range(batches):
            operations = [('put', f'batch{batch}/{i:08d}', b'b' * 100)
                          for i in range(1000)]
            before = time.perf_counter_ns()
            store.apply(operations)
            batch_times.append(time.perf_counter_ns() - before)
        apply_rate = batches * 1000 / (time.perf_counter() - start)
    return {"put_rows_s": round(put_rate, 1),
            "apply_1000_rows_s": round(apply_rate, 1),
            "apply_1000_median_ms": round(statistics.median(batch_times) / 1e6, 3)}


def run(size, root, reads, puts, batches):
    base = root / f'base-{size}.db'
    with sqlite3.connect(base) as conn:
        conn.execute('CREATE TABLE opdb_source_kv '
                     '(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)')
        value = b'X' * 100
        for start in range(0, size, 10000):
            conn.executemany('INSERT INTO opdb_source_kv VALUES (?,?)',
                             ((f'g{i % 10}/{i:09d}', value)
                              for i in range(start, min(size, start + 10000))))
    with TruthStore(base, lens=False) as src:
        source_result = timed_reads(src, src.group_stats_source, 'g1', reads)
    tracemalloc.start()
    with TruthStore(base, lens=True) as store:
        _, peak = tracemalloc.get_traced_memory()
        rebuild_ms = round(store._lens.rebuild_ns / 1e6, 2)
        lens_result = timed_reads(store, store.group_stats, 'g1', reads)
        assert store.group_stats('g1').row_count == store.group_stats_source('g1').row_count
    tracemalloc.stop()
    rates = {}
    for enabled in (False, True):
        work = root / f'write-{size}-{int(enabled)}.db'
        shutil.copyfile(base, work)
        rates['lens' if enabled else 'source'] = write_rates(work, enabled, puts, batches)
    overhead = {key: round(100 * (rates['source'][key] / rates['lens'][key] - 1), 1)
                for key in ('put_rows_s', 'apply_1000_rows_s')}
    # Comparing per-batch durations is less sensitive to Python list setup.
    overhead['apply_1000_median_ms'] = round(100 * (
        rates['lens']['apply_1000_median_ms'] /
        rates['source']['apply_1000_median_ms'] - 1), 1)
    result = {"rows": size, "value_bytes": 100, "reads": reads,
              "batches": batches,
              "source": source_result, "lens": lens_result,
              "lens_rebuild_ms": rebuild_ms, "lens_peak_tracemalloc_bytes": peak,
              "write_rates": rates, "write_overhead_percent": overhead}
    result['lens_read_faster'] = lens_result['median_us'] < source_result['median_us']
    result['write_overhead_over_20pct'] = any(v > 20 for v in overhead.values())
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', type=int, nargs='+', default=[10000, 100000, 1000000])
    parser.add_argument('--reads', type=int, default=30)
    parser.add_argument('--puts', type=int, default=100)
    parser.add_argument('--batches', type=int, default=30)
    opts = parser.parse_args()
    if opts.batches < 1:
        parser.error('--batches must be at least 1')
    print(json.dumps({"machine": platform.platform(), "python": platform.python_version(),
                      "sqlite": sqlite3.sqlite_version, "cpu": platform.processor(),
                      "logical_cpus": os.cpu_count(), "measurement": "local-file SQLite, warm reads; tracemalloc"}))
    with tempfile.TemporaryDirectory() as temp:
        for size in opts.sizes:
            print(json.dumps(run(size, Path(temp), opts.reads, opts.puts, opts.batches)), flush=True)


if __name__ == '__main__':
    main()
