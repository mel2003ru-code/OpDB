# TASK-016 — M2/M3/M5 follow-up: reduce the write cost of the numeric Lens

- Milestone: M2 (cheaper writes with a Lens), motivated by the M5 result
- Depends on: TASK-014 (DONE, PR #64), TASK-015 (DONE, PR #67)
- Deliverable: **one pull request** against `main`

## Goal
`docs/M5_COMPARISON.md` (TASK-015) measured that `NumericTruthStore.apply`
is slower than plain SQLite for 1,000-row batches: 1.2x to 2.7x slower than
a covering index (A) and up to 1.8x slower than trigger-maintained summary
tables (B); worst case 10k rows overwrite, 12.4 vs 4.7 ms. The open time
(0.8-1.1 ms vs 0.13-0.27 ms) and file size (+7%) are also worse. Find where
the extra time goes in `apply` and remove what can be removed without
weakening atomicity, the stored-Lens validation at open, or the Source
cross-check. A negative result (nothing removable) is a valid outcome.

## What to build
1. Measure first: a profile script (new file under `experiments/`, or
   an extension of `m4_numeric_bench.py`) that splits a 1,000-row batch into
   Source statements, old-value lookup, `opdb_nlens_group` upserts,
   `opdb_nlens_val` inserts/deletes, extreme re-lookup after deleting or
   overwriting a group's current min/max, the negative/overflow checks and the
   meta update. Label anything not measurable as unavailable.
2. Optimise only measured hot spots in `opdb/numeric.py`. Candidates: one
   batched statement per table instead of a statement per key, restrict checks
   to touched groups, look up old values for the whole batch at once, skip
   work for keys whose value and group did not change, reuse prepared
   statements, check whether `opdb_nlens_val` needs `WITHOUT ROWID`
   (only if the stored format version stays compatible; otherwise report
   it as an idea, do not do it). Keep one `BEGIN IMMEDIATE` transaction and
   the same validation at open.
3. Keep a change only if repeated before/after runs on the same machine show
   a gain; otherwise submit the measurements as a negative result.

## Tests that must exist (new files only)
- Seeded oracle test (at least 20 seeds): after every batch and after
  close/reopen, `numeric_stats` for all groups equals both Source
  recomputation and a plain Python dict model. Cover duplicate keys in one
  batch, delete then put, overwrite that moves a key to another group,
  deleting the only min or max of a group, deleting a whole group, empty
  values, Unicode keys, deletes of absent keys.
- Rollback: an injected error mid-batch leaves Source and Lens unchanged;
  overflow still falls back to Source as before.
- Second store on the same file: a write through another connection is
  detected and the Lens is rebuilt or bypassed, never served stale.
- Existing tests (including TASK-014 tests) pass unchanged.

## Measurement
Rerun the M5 insert / overwrite / delete workloads for contender C (and A, B
as references) at 10k, 100k and 1M rows, median and p95 of at least 30
batches, two runs, before and after, on one machine. Report CPU, RAM,
Python, SQLite, git SHA and raw numbers. Append the before/after table to
`docs/M5_COMPARISON.md` as a new section (do not edit the earlier numbers).
Do not claim a target; report what was measured.

## Scope limits
`opdb/numeric.py`, `experiments/`, new files in `tests/`, a section appended
to `docs/M5_COMPARISON.md`. No change to the stored format (schema version
stays as is), protected files, Foundry or PR #38. About 600 lines or fewer,
tests included.
