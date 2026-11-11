"""TASK-010: fixed-seed 1,000-operation batch, Source-only vs Lens, same file state.

Every timed batch starts from identical rows: touched keys are restored outside
the timer. Source and Lens batches alternate on separate copies of one base file.
Run: python experiments/m2_batch_check.py [--opdb-root DIR] [--sizes ...]
--opdb-root points at another checkout (e.g. the M1 merge) to time its engine.
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

VALUE = b'X' * 100


def make_batch(size, seed, batch):
    """Mixed batch: new keys, overwrites, deletes, repeats. Returns (ops, restore)."""
    rng = random.Random(seed * 100003 + batch)
    ops, touched = [], {}
    for _ in range(1000):
        roll = rng.random()
        if roll < 0.4:
            key = f'g{rng.randrange(10)}/new{batch:04d}-{rng.randrange(400):04d}'
        else:
            i = rng.randrange(size)
            key = f'g{i % 10}/{i:09d}'
        touched.setdefault(key, not key.split('/', 1)[1].startswith('new'))
        if roll < 0.85:
            ops.append(('put', key, bytes([65 + rng.randrange(20)]) * rng.randrange(0, 200)))
        else:
            ops.append(('delete', key))
    restore = [('put', k, VALUE) if existed else ('delete', k)
               for k, existed in touched.items()]
    return ops, restore


def build_base(path, size):
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE opdb_source_kv '
                     '(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)')
        for start in range(0, size, 10000):
            conn.executemany('INSERT INTO opdb_source_kv VALUES (?,?)',
                             ((f'g{i % 10}/{i:09d}', VALUE)
                              for i in range(start, min(size, start + 10000))))


def measure(TruthStore, root, size, batches, seed):
    base = root / f'base-{size}.db'
    if not base.exists():
        build_base(base, size)
    files = {mode: root / f'{mode}-{size}.db' for mode in ('source', 'lens')}
    for f in files.values():
        shutil.copyfile(base, f)
    samples = {'source': [], 'lens': []}
    stores = {m: TruthStore(files[m], lens=(m == 'lens')) for m in files}
    try:
        for batch in range(batches):
            ops, restore = make_batch(size, seed, batch)
            order = ('source', 'lens') if batch % 2 == 0 else ('lens', 'source')
            for mode in order:
                started = time.perf_counter_ns()
                stores[mode].apply(ops)
                samples[mode].append(time.perf_counter_ns() - started)
                stores[mode].apply(restore)
        for g in range(10):
            assert stores['lens'].group_stats(f'g{g}').row_count == \
                stores['source'].group_stats_source(f'g{g}').row_count
    finally:
        for s in stores.values():
            s.close()
    ms = {m: [x / 1e6 for x in v] for m, v in samples.items()}
    src, lens = statistics.median(ms['source']), statistics.median(ms['lens'])
    return {'rows': size, 'batches': batches, 'seed': seed,
            'source_median_ms': round(src, 3), 'lens_median_ms': round(lens, 3),
            'lens_overhead_percent': round(100 * (lens / src - 1), 1),
            'source_stdev_ms': round(statistics.stdev(ms['source']), 3),
            'lens_stdev_ms': round(statistics.stdev(ms['lens']), 3)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sizes', type=int, nargs='+', default=[10000, 100000, 1000000])
    p.add_argument('--batches', type=int, default=30)
    p.add_argument('--seed', type=int, default=10)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--opdb-root', default=str(Path(__file__).resolve().parents[1]))
    o = p.parse_args()
    if o.batches < 2:
        p.error('--batches must be at least 2')
    sys.path.insert(0, o.opdb_root)
    from opdb import TruthStore
    print(json.dumps({'opdb_root': o.opdb_root, 'platform': platform.platform(),
                      'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
                      'cpu': platform.processor() or platform.machine(),
                      'logical_cpus': os.cpu_count()}))
    with tempfile.TemporaryDirectory() as temp:
        for size in o.sizes:
            runs = [measure(TruthStore, Path(temp), size, o.batches, o.seed)
                    for _ in range(o.repeats)]
            print(json.dumps({'rows': size, 'runs': runs, 'median_overhead_percent':
                              statistics.median(r['lens_overhead_percent'] for r in runs)}),
                  flush=True)


if __name__ == '__main__':
    main()
