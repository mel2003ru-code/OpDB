"""TASK-006/007/009/011 local-file Lens vs Source microbench; no cross-engine claims.

Run: python experiments/lens_bench.py [--sizes 10000 100000 1000000]
TASK-011: python experiments/lens_bench.py --hotspots [--repeats 2] [--seed 11]
runs only the 1,000-operation batches by kind: insert (new keys), overwrite,
delete, repeat (repeated keys, put/delete mix). Each timed batch starts from
identical rows: restoration, store setup and Lens rebuild (done when the store
opens) are all OUTSIDE the timed interval. Source and Lens run on separate
copies of one base file, alternating order. Breakdown: only the post-commit
Lens update (AggregateLens.advance) is timed, by wrapping that method. The
in-transaction part (existing-key lookup, version checks, SQL writes) cannot be
separated without editing TruthStore.apply, so it is reported as unavailable,
not estimated.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import random
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


def _existing_key(index):
    # run() seeds one existing key for every source row across ten groups.
    return f'g{index % 10}/{index:09d}'


def _scenario_batch(kind, batch):
    overwrite_value = b'Y' * (61 + (batch % 7) * 7)
    if kind == 'overwrite':
        keys = [_existing_key(i) for i in range(1000)]
        return ([('put', key, overwrite_value) for key in keys],
                [('put', key, b'X' * 100) for key in keys])
    if kind == 'delete':
        keys = [_existing_key(i) for i in range(1000)]
        return ([('delete', key) for key in keys],
                [('put', key, b'X' * 100) for key in keys])
    if kind == 'mixed':
        new_ops = [('put', f'new/{batch:03d}/{i:04d}', b'N' * 73)
                   for i in range(333)]
        overwrite_ops = [('put', _existing_key(i), overwrite_value)
                         for i in range(333)]
        delete_keys = [_existing_key(333 + i) for i in range(334)]
        delete_ops = [('delete', key) for key in delete_keys]
        # Undo everything outside the timer: drop the new keys and put the
        # original value back for overwritten and deleted keys.
        restore = ([('delete', op[1]) for op in new_ops] +
                   [('put', _existing_key(i), b'X' * 100) for i in range(333)] +
                   [('put', key, b'X' * 100) for key in delete_keys])
        return new_ops + overwrite_ops + delete_ops, restore
    raise ValueError(f'unknown scenario: {kind}')


def _measure_scenario(base, root, size, kind, enabled, batches):
    mode = 'lens' if enabled else 'source'
    work = root / f'scenario-{size}-{kind}-{mode}.db'
    shutil.copyfile(base, work)
    samples = []
    with TruthStore(work, lens=enabled) as store:
        for batch in range(batches):
            operations, restore = _scenario_batch(kind, batch)
            started = time.perf_counter_ns()
            store.apply(operations)
            samples.append(time.perf_counter_ns() - started)
            # Every batch starts from the same rows and values; this
            # restoration is deliberately outside the timed interval.
            if restore:
                store.apply(restore)
    work.unlink(missing_ok=True)
    return round(statistics.median(samples) / 1e6, 3)


def run_write_scenarios(base, root, size, batches):
    if size < 1000:
        raise ValueError('scenario benchmark requires at least 1000 existing rows')
    scenarios = {}
    for kind in ('overwrite', 'delete', 'mixed'):
        source_ms = _measure_scenario(base, root, size, kind, False, batches)
        lens_ms = _measure_scenario(base, root, size, kind, True, batches)
        overhead = round(100 * (lens_ms / source_ms - 1), 1) if source_ms else None
        scenarios[kind] = {
            'batches': batches,
            'source_median_batch_ms': source_ms,
            'lens_median_batch_ms': lens_ms,
            'lens_overhead_percent': overhead,
        }
    return scenarios


VALUE = b'X' * 100
HOTSPOT_SCENARIOS = ('insert', 'overwrite', 'delete', 'repeat')


def existing_key(i):
    return _existing_key(i)


def hotspot_batch(kind, size, seed, batch):
    """Return (operations, restore); restore undoes the batch exactly."""
    rng = random.Random(seed * 100003 + batch)
    if kind == 'insert':
        keys = [f'g{rng.randrange(10)}/ins{batch:04d}-{i:04d}' for i in range(1000)]
        return ([('put', k, bytes([65 + rng.randrange(20)]) * rng.randrange(0, 200))
                 for k in keys], [('delete', k) for k in keys])
    picks = rng.sample(range(size), 1000)
    keys = [existing_key(i) for i in picks]
    if kind == 'overwrite':
        return ([('put', k, bytes([65 + rng.randrange(20)]) * rng.randrange(0, 200))
                 for k in keys], [('put', k, VALUE) for k in keys])
    if kind == 'delete':
        return ([('delete', k) for k in keys], [('put', k, VALUE) for k in keys])
    if kind == 'repeat':
        pool = keys[:60] + [f'g{n % 10}/rep{batch:04d}-{n:03d}' for n in range(40)]
        ops = []
        for _ in range(1000):
            k = rng.choice(pool)
            if rng.random() < 0.7:
                ops.append(('put', k, bytes([65 + rng.randrange(20)]) * rng.randrange(0, 200)))
            else:
                ops.append(('delete', k))
        restore = ([('put', k, VALUE) for k in keys[:60]] +
                   [('delete', k) for k in pool[60:]])
        return ops, restore
    raise ValueError(f'unknown scenario: {kind}')


def build_hotspot_base(path, size):
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE opdb_source_kv '
                     '(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)')
        for start in range(0, size, 10000):
            conn.executemany('INSERT INTO opdb_source_kv VALUES (?,?)',
                             ((existing_key(i), VALUE)
                              for i in range(start, min(size, start + 10000))))


def instrument_advance(store, sink, active):
    original = store._lens.advance

    def timed(*args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return original(*args, **kwargs)
        finally:
            if active[0]:  # count only the timed batch, not its restore
                sink.append(time.perf_counter_ns() - started)
    store._lens.advance = timed


def measure_hotspot(root, size, kind, batches, seed):
    base = root / f'hotspot-base-{size}.db'
    if not base.exists():
        build_hotspot_base(base, size)
    files = {m: root / f'{kind}-{m}-{size}.db' for m in ('source', 'lens')}
    for f in files.values():
        shutil.copyfile(base, f)
    samples = {'source': [], 'lens': []}
    advance, active = [], [False]
    stores = {m: TruthStore(files[m], lens=(m == 'lens')) for m in files}
    instrument_advance(stores['lens'], advance, active)
    try:
        for batch in range(batches):
            ops, restore = hotspot_batch(kind, size, seed, batch)
            order = ('source', 'lens') if batch % 2 == 0 else ('lens', 'source')
            for mode in order:
                active[0] = True
                started = time.perf_counter_ns()
                stores[mode].apply(ops)
                samples[mode].append(time.perf_counter_ns() - started)
                active[0] = False
                stores[mode].apply(restore)
        # Correctness gate: the Lens must still equal Source after all batches.
        for g in range(10):
            a, b = stores['lens'].group_stats(f'g{g}'), stores['lens'].group_stats_source(f'g{g}')
            assert (a.row_count, a.value_bytes) == (b.row_count, b.value_bytes)
    finally:
        for s in stores.values():
            s.close()
        for f in files.values():
            f.unlink(missing_ok=True)
    ms = {m: [x / 1e6 for x in v] for m, v in samples.items()}
    src, lens = statistics.median(ms['source']), statistics.median(ms['lens'])
    return {'source_median_ms': round(src, 3), 'lens_median_ms': round(lens, 3),
            'lens_overhead_percent': round(100 * (lens / src - 1), 1),
            'source_stdev_ms': round(statistics.stdev(ms['source']), 3),
            'lens_stdev_ms': round(statistics.stdev(ms['lens']), 3),
            'lens_advance_median_ms': round(statistics.median(advance) / 1e6, 4),
            'in_transaction_breakdown': 'unavailable'}


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
    result['batch_scenarios'] = run_write_scenarios(base, root, size, batches)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sizes', type=int, nargs='+', default=[10000, 100000, 1000000])
    parser.add_argument('--reads', type=int, default=30)
    parser.add_argument('--puts', type=int, default=100)
    parser.add_argument('--batches', type=int, default=30)
    parser.add_argument('--hotspots', action='store_true',
                        help='TASK-011: only 1,000-op batches by kind')
    parser.add_argument('--seed', type=int, default=11)
    parser.add_argument('--repeats', type=int, default=2)
    opts = parser.parse_args()
    if opts.batches < 1:
        parser.error('--batches must be at least 1')
    print(json.dumps({"machine": platform.platform(), "python": platform.python_version(),
                      "sqlite": sqlite3.sqlite_version, "cpu": platform.processor(),
                      "logical_cpus": os.cpu_count(), "measurement": "local-file SQLite, warm reads; tracemalloc"}))
    with tempfile.TemporaryDirectory() as temp:
        for size in opts.sizes:
            if opts.hotspots:
                for kind in HOTSPOT_SCENARIOS:
                    runs = [measure_hotspot(Path(temp), size, kind, max(2, opts.batches),
                                            opts.seed) for _ in range(opts.repeats)]
                    print(json.dumps({'rows': size, 'scenario': kind,
                                      'batches': max(2, opts.batches), 'runs': runs,
                                      'median_overhead_percent': round(statistics.median(
                                          r['lens_overhead_percent'] for r in runs), 1)}),
                          flush=True)
                continue
            print(json.dumps(run(size, Path(temp), opts.reads, opts.puts, opts.batches)), flush=True)


if __name__ == '__main__':
    main()
