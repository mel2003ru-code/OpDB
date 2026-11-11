# TASK-010 — M2: measure and reduce Lens batch-write overhead

## Goal
Close the remaining M2 write-cost acceptance gap with a reproducible 1,000-row batch comparison against Source-only writes. This task measures and, if justified by the evidence, improves engine write behavior; it does not change project process.

## What to build
- Extend the existing Lens benchmark with a fixed-seed, repeatable 1,000-row batch workload, with equal initial rows and values before each timed batch in Source and Lens modes.
- Record baseline and candidate median timings on the same machine and state precisely whether the M2 target (Lens write overhead reduced by at least one third relative to the M1 baseline) is met. If the M1 baseline cannot be reconstructed, report this as not established, not as success.
- If the benchmark identifies a safe optimization in `TruthStore.apply`, implement it; keep only an improvement supported by repeated measurements. Preserve operation order and transactional semantics.

## Tests that must exist
- New independent tests using a plain Python key/value model and direct SQLite Source queries, including repeated keys, empty values, Unicode groups, deletes, and failed writes.
- Verify both Source and Lens against that independent model after each batch, including a second store reopened on the same file.
- All existing tests must pass unchanged. Do not edit protected files.

## Measurements
- Run at least 30 batches of 1,000 operations at 10k, 100k and 1M rows, on the same machine for baseline and candidate; report raw median milliseconds, overhead, repeated-run variability, Python/SQLite/CPU/OS.
- Compare with the M1 baseline only when the workload and environment are comparable; otherwise state that the milestone threshold is unverified.

## Scope limits
Only `opdb/`, `experiments/`, new files under `tests/`, and `workstreams/BACKLOG.md` for task status. No stored Lens/M3, Foundry, release, deployment, or protected-file changes. One PR, roughly 600 lines or fewer.
