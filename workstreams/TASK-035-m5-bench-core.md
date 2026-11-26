# TASK-035 — M5: benchmark core (data, timing, SQLite contender)

## Goal
First part of one reproducible benchmark set that will compare SQLite, the OpDB
Source/Lens and, later, a Rust LSM on the same data, the same machine and the same
durability settings. This task builds the harness core and the SQLite contender
with a correctness oracle. It measures; it makes no speed claim.

## What to build
A small package `experiments/bench/` (standard library only, each file about
100 lines or fewer):
- `experiments/bench/__init__.py` (a docstring only).
- `experiments/bench/data.py`: `make_rows(n, seed, value_bytes)` returns a list of
  `(key, value)`; keys are `grp<i>/<n>` with `i = n % 1000` (1,000 groups), the
  value of row `n` is `random.Random(seed * 1000003 + n).randbytes(value_bytes)`;
  `digest(rows)` returns the sha256 hex digest of all keys and values in order.
- `experiments/bench/timing.py`: `measure(fn, runs, timer=time.perf_counter_ns)`
  calls `fn()` `runs` times and returns the list of durations in milliseconds;
  `summarize(samples)` returns `{"runs": [...], "median_ms", "min_ms", "max_ms"}`;
  `machine_info()` returns the Python version, `sqlite3.sqlite_version`, a platform
  string and `os.cpu_count()`.
- `experiments/bench/sqlite_contender.py`: class `SqliteContender(path,
  synchronous="FULL")` with `name = "sqlite"`; it sets `PRAGMA journal_mode=WAL` and
  `PRAGMA synchronous=<synchronous>`, creates
  `kv(k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID`; `bulk_insert(rows, batch=1000)`
  writes one transaction per batch with `executemany`; `get(key)` returns the
  value or `None`; `count()`; `close()`.
- `experiments/bench/run.py`: `main(argv)` with `--sizes`, `--runs`, `--seed`,
  `--value-bytes` (default 16), `--synchronous` (default FULL), `--json PATH`. For
  every size and every run it creates a fresh temporary directory and file, times
  `bulk_insert` of all rows (workload `bulk_insert`), then verifies the stored
  data against the generated rows (every key when `n <= 2000`, otherwise 1,000
  keys picked with the seed), then times 200 seeded `get` calls of existing keys
  (workload `point_read`). Writes a JSON file: `{"schema": 1, "command": [...],
  "seed": ..., "synchronous": ..., "machine": {...}, "data_digest": {size:
  digest}, "results": [{"contender", "size", "workload", "verified": true,
  "runs": [...], "median_ms", "min_ms", "max_ms"}]}` and prints a short table.

## Tests that must exist
New file `tests/test_bench_core_035.py`, about 120 lines or fewer:
1. Determinism: the same seed gives the same rows and digest, another seed a
   different digest; 1,000 groups appear for `n = 5000`; keys are unique.
2. `summarize` on known samples (odd and even count) gives the right median, min
   and max; `measure` with an injected fake timer returns the expected durations.
3. `SqliteContender`: insert 2,000 rows, every `get` equals the generated value,
   `count()` is 2,000, a missing key gives `None`; the WAL and synchronous
   settings are really applied (read them back with `PRAGMA`).
4. `run.main` with `--sizes 500 --runs 2 --seed 3 --json <tmp>` writes JSON whose
   `results` hold both workloads, two run samples each, `verified` true, and a
   `data_digest` for 500; run it twice with the same seed: the digests are equal.
- Close every connection before the temporary directory is removed (needed on
  Windows). Existing tests must pass unchanged.

## Notes checked against the engine
- `sqlite3` is in the standard library; `PRAGMA journal_mode=WAL` works in a
  temporary directory; `random.Random.randbytes` exists (Python 3.9+).
- `experiments/` has no `__init__.py`: it is a namespace package and tests import
  with `from experiments.bench import data` when run from the repository root.
  Do NOT add `experiments/__init__.py`.
- Timings are wall-clock milliseconds; the test must not assert any speed value.

## Measurement
None in this task: the first published table comes from a later manual run.

## Scope
The five files above plus one test file, about 600 lines or fewer together.
Standard library only. One task PR. No protected files, no changes to `opdb/`, no
paid models.
