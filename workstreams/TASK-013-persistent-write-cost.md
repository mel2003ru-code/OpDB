# TASK-013 — M3: reduce the write cost of the persisted Lens

- Milestone: M3 — Lens survives restart
- Depends on: TASK-012 (DONE, PR #60)

## Goal
TASK-012 made healthy open of a 1M-row file take under 1 ms, but 1,000-row batches are slower than the in-memory Lens: independent reruns on main (4fcd201; Python 3.13.18, SQLite 3.53.1, 2 vCPU) gave 7.5 vs 4.4 ms at 10k rows and 8.8 vs 5.3 ms at 100k rows (about +65-70%; PR #60 text reported +30-55%). Find where the extra time goes in `PersistentTruthStore.apply` and remove what can be removed without weakening atomicity or the open-time checks.

## What to build
1. Measure first: extend `experiments/m3_persistent_bench.py` (or a new script) to split a 1,000-row batch into Source statements, old-length lookup, Lens upserts, the `n=0` delete, the negative-aggregate check and the meta update. Label anything not measurable as unavailable.
2. Optimise only measured hot spots in `opdb/persistent.py`. Candidates: replace the per-key `executemany`-style loop with batched statements, restrict the negative-aggregate check to touched groups, skip the `DELETE ... WHERE n=0` when no group reached zero, reuse prepared statements. Keep one `BEGIN IMMEDIATE` transaction, the same operation order and the same validation at open.
3. Keep a change only if repeated before/after runs on the same machine show a gain; otherwise submit the measurements as a negative result.

## Tests that must exist (new files only)
- Seeded oracle test (at least 20 seeds): Source recomputation and a plain Python dict after every batch and after close/reopen; duplicate keys in a batch, delete then put, empty values, Unicode keys, deletes of absent keys.
- Rollback: an injected error mid-batch leaves Source and Lens both unchanged.
- Existing tests (including `tests/test_persistent_lens_012.py`) pass unchanged.

## Measurement
Median and p95 of at least 30 batches of 1,000 operations (new keys, overwrites, deletes, mixed) at 10k, 100k and 1M rows, two runs, before and after, with the in-memory Lens and Source-only as references. Report CPU, RAM, Python, SQLite, SHA and raw numbers. Do not claim a target; report what was measured.

## Scope limits
`opdb/`, `experiments/`, new files in `tests/`, a short note appended under `docs/`. No change to the stored format (schema version stays 1), protected files, Foundry, PR #38 or the threat boundary. About 600 lines or fewer.
