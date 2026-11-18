# TASK-017 — M3/M4 follow-up: reduce the rebuild-from-Source time of the numeric Lens

- Milestone: M3 (Lens survives restart: a damaged or stale Lens is rebuilt) and M4
- Depends on: TASK-014 (DONE, PR #64), TASK-016 (DONE, PR #70)
- Deliverable: **one pull request** against `main`

## Goal
`docs/M4_NUMERIC_LENS.md` reports that the first open of a 1M-row file (a
rebuild) took 4.9 s, and `NumericTruthStore._refresh` repeats the same rebuild
after every commit made by another connection. The rebuild is therefore the
slowest operation the numeric Lens has, and it is the price of every recovery
from a stale, damaged or overflowed Lens. Measure where the time goes and make
`rebuild()` cheaper without changing what it produces. A negative result
(nothing worth removing) is a valid outcome.

## What to build
1. Measure first: a script under `experiments/` that splits a rebuild at 10k,
   100k and 1M rows into the Source scan, key validation and grouping in
   Python, the in-memory aggregation, the two `DELETE`s, the
   `opdb_nlens_group` insert, the `opdb_nlens_val` insert and the commit.
   Label anything not measurable as unavailable.
2. Optimise only measured hot spots in `opdb/numeric.py`. Candidates: sort
   `vals` by the primary key of `opdb_nlens_val` before the bulk insert so
   B-tree pages fill sequentially; avoid holding all rows as Python tuples at
   once (chunked insert, still one `BEGIN IMMEDIATE`); validate keys in bulk;
   `DELETE` of whole tables versus dropping and recreating them (only if the
   stored schema and version stay identical). The stored format, schema
   version, open validation, `open_mode`/`open_reason` values and overflow fallback must not change.
3. Keep a change only if repeated before/after runs on the same machine show
   a gain larger than the run-to-run spread; otherwise submit the measurements
   as a negative result. No other threshold is set: report the numbers.

## Tests that must exist (new files only)
- At least 20 seeds: build a store with put/overwrite/delete, call `rebuild()`
  and compare every group (`count`, `sum`, `min`, `max`) with a plain Python
  dict model and with a fresh SQL recomputation over Source. The table
  contents after the new `rebuild()` must equal the contents after the old
  one; the oracle is an expected table derived from Source by plain SQL/Python,
  not a copy of the old implementation.
- Calling `rebuild()` twice in a row without writes gives identical tables.
- Negative numbers, ties, empty values rejected as before, Unicode keys,
  a single group holding every row, many groups with one row each.
- Failure inside rebuild (wrong-width Source value written from outside, and an
  injected error half way through the insert) leaves the previous Lens tables
  untouched and the store untrusted; overflow still falls back to Source.
- A second store on the same file: a commit by one store causes the other to
  rebuild and then answer equal to Source.
- Existing tests unchanged and green.

## Measurement
Time of `rebuild()` and of first open of an untrusted file at 10k, 100k and
1M rows, median and worst of at least 7 runs, two independent runs, before and
after, on one machine. Commit the "before" numbers (taken on the unchanged
code) in the PR. Report CPU, RAM, OS, disk type, Python, SQLite, git SHA and raw numbers.
Append the table as a new section to `docs/M4_NUMERIC_LENS.md` (do not edit
earlier numbers). Do not claim a target; report what was measured.

## Scope limits
`opdb/numeric.py`, `experiments/`, new files in `tests/`, a section appended to
`docs/M4_NUMERIC_LENS.md`. No change to the stored format or schema version, no
protected files, Foundry or PR #38. About 600 lines or fewer, tests included.
