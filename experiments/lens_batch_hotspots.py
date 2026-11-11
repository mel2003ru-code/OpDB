"""TASK-011: 1,000-operation batches by kind, Source-only vs Lens, same file state.

Scenarios: insert (new keys), overwrite, delete, repeat (repeated keys, put/delete
mix). Each timed batch starts from identical rows: restoration, store setup and
Lens rebuild (done when the store opens) are all OUTSIDE the timed interval.
Source and Lens run on separate copies of one base file, alternating order.
Breakdown: only the post-commit Lens update (AggregateLens.advance) is timed, by
wrapping that method. The in-transaction part (existing-key lookup, version
checks, SQL writes) cannot be separated without editing TruthStore.apply, so it
is reported as unavailable, not estimated.
Run: python experiments/lens_batch_hotspots.py [--sizes ...] [--repeats 2]
"""
import argparse
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opdb import TruthStore

VALUE = b'X' * 100
SCENARIOS = ('insert', 'overwrite', 'delete', 'repeat')


def existing_key(i):
    return f'g{i % 10}/{i:09d}'


def make_batch(kind, size, seed, batch):
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


def build_base(path, size):
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


def measure(root, size, kind, batches, seed):
    base = root / f'base-{size}.db'
    if not base.exists():
        build_base(base, size)
    files = {m: root / f'{kind}-{m}-{size}.db' for m in ('source', 'lens')}
    for f in files.values():
        shutil.copyfile(base, f)
    samples = {'source': [], 'lens': []}
    advance, active = [], [False]
    stores = {m: TruthStore(files[m], lens=(m == 'lens')) for m in files}
    instrument_advance(stores['lens'], advance, active)
    try:
        for batch in range(batches):
            ops, restore = make_batch(kind, size, seed, batch)
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sizes', type=int, nargs='+', default=[10000, 100000, 1000000])
    p.add_argument('--batches', type=int, default=30)
    p.add_argument('--seed', type=int, default=11)
    p.add_argument('--repeats', type=int, default=2)
    o = p.parse_args()
    if o.batches < 2:
        p.error('--batches must be at least 2')
    cpu = platform.processor() or platform.machine()
    print(json.dumps({'platform': platform.platform(), 'python': platform.python_version(),
                      'sqlite': sqlite3.sqlite_version, 'cpu': cpu,
                      'logical_cpus': os.cpu_count()}))
    with tempfile.TemporaryDirectory() as temp:
        for size in o.sizes:
            for kind in SCENARIOS:
                runs = [measure(Path(temp), size, kind, o.batches, o.seed)
                        for _ in range(o.repeats)]
                print(json.dumps({'rows': size, 'scenario': kind, 'batches': o.batches,
                                  'runs': runs,
                                  'median_overhead_percent': round(statistics.median(
                                      r['lens_overhead_percent'] for r in runs), 1)}),
                      flush=True)


if __name__ == '__main__':
    main()
