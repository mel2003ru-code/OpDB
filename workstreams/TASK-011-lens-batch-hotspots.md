# TASK-011 — M2: isolate the remaining Lens batch-write cost

## Goal
Measure where Lens adds work during 1,000-operation batches after TASK-010, and reduce a verified engine hot spot only if repeated measurements demonstrate a safe benefit. This is an engine measurement/behavior task, not a process task.

## What to build
- Extend `experiments/lens_bench.py` with repeatable, fixed-seed 1,000-operation batches that distinguish new-key inserts, overwrites, deletes, and repeated-key mixed operations.
- For Source-only and Lens, restore identical Source contents and row counts outside every timed interval. Document whether rebuilding Lens, setup, and cleanup are excluded from timings.
- Record separately the time spent on Source writes and Lens maintenance where the existing `TruthStore.apply` implementation permits accurate measurement; otherwise explicitly label the breakdown as unavailable rather than estimating it.
- If a measurable, safe hot spot is found, optimize `opdb/` without changing operation order, atomicity, or the Source/Lens contract. Retain the change only if repeated before/after runs show an improvement; otherwise submit the measurement and negative result.

## Tests that must exist
- Add independent seeded tests with a plain Python dictionary and direct SQLite Source queries as separate oracles, including duplicate keys in one batch, empty bytes, Unicode keys, deletes of absent keys, and delete-then-put.
- Test rollback on a failed batch, and reopening a second store on the same file. Compare both Source and Lens to the independent model after each successful batch.
- All existing tests must pass unchanged.

## Measurements
- At least 30 batches of 1,000 operations for each scenario at 10k, 100k, and 1M initial rows; at least two independent runs on the same machine.
- Report raw median milliseconds for Source-only and Lens, overhead percentages, variability between runs, and CPU/OS/Python/SQLite details.
- If code changes, report before/after under the same environment and workload. Do not claim the M2 one-third reduction unless a comparable M1 baseline exists.

## Scope limits
Only `opdb/`, `experiments/`, new test files under `tests/`, and `workstreams/BACKLOG.md` for status. No changes to existing tests, protected files, stored Lens/M3, Foundry, PR #38, releases, or deployment. One task PR, approximately 600 lines or fewer.
