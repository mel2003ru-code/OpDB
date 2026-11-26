# TASK-037 — M5: benchmark range scan and filter workloads

## Goal
Add two read workloads to the benchmark: counting rows of a key range and counting
rows of a range that pass a value filter. A contender without the capability is
reported as `NOT_IMPLEMENTED`, never as a result.

## What to build
Depends on TASK-036 being merged. Add:
- `experiments/bench/workloads.py`: `pick_groups(seed, count=50)` returns 50
  distinct group numbers in `0..999`, deterministic for a seed;
  `expected_range_count(rows, group)` and `expected_filter_count(rows, group,
  threshold=128)` compute the model answer in plain Python (a row passes the filter
  when the first byte of its value is `< threshold`).
- `range_count(group)` and `filter_count(group, threshold)` methods:
  - `SqliteContender`: range is `k >= 'grp<g>/' AND k < 'grp<g>0'` (the character
    `'0'` follows `'/'`); filter adds `AND substr(v, 1, 1) < x'80'`.
  - `OpdbSourceContender` and `OpdbNumericContender`: `range_count` uses
    `store.scan("grp<g>/", limit=1000)` (a group holds at most 1,000 rows up to a
    million rows); `filter_count` does not exist: report `NOT_IMPLEMENTED`.
- `experiments/bench/run.py` (complete file): workloads `range_scan` (the 50
  groups, total time) and `filter` (same). Before timing, every answer of every
  contender is compared with the model; a mismatch aborts the run. Result rows keep
  the existing shape; a missing capability gives `{"contender", "workload",
  "status": "NOT_IMPLEMENTED"}`.

## Tests that must exist
New file `tests/test_bench_range_037.py`, about 120 lines or fewer:
1. `pick_groups` is deterministic, has 50 distinct values in range, differs for
   another seed.
2. On 3,000 generated rows (size 3,000 gives 3 rows per group) every contender's
   `range_count` equals the model for several groups; SQLite `filter_count`
   equals the model; `OpdbSourceContender` has no `filter_count`.
3. `run.main` writes JSON with verified `range_scan` rows for all contenders and
   a `filter` row for SQLite plus `NOT_IMPLEMENTED` rows for the OpDB contenders.
- Close every store before the temporary directory is removed. Existing tests
  must pass unchanged.

## Notes checked against the engine
- `TruthStore.scan(prefix, limit)` returns `(key, value)` pairs ordered by key and
  requires `1 <= limit <= 1000`.
- SQLite compares BLOBs bytewise, so `substr(v, 1, 1) < x'80'` is a byte filter.

## Measurement
None.

## Scope
Two files changed or added plus one test file, about 600 lines or fewer together.
Standard library only. One task PR. No protected files, no changes to `opdb/`, no
paid models.
