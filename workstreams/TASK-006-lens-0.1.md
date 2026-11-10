# TASK-006 — Lens 0.1: one incrementally maintained aggregate

- Date: 2026-11-10
- Depends on: PR #39 (`opdb/core.py`, merge first) and
  [ADR-006](../docs/adr/ADR-006-trust-boundary.md)
- Deliverable: **one pull request** against `main`

## Goal

Make OpDB do one thing that plain SQLite key-value access does not: answer
an aggregate question in constant time from a derived structure that is
proven, on every test run, to equal a full recomputation from Source.

## What to build

**Groups.** A key's group is the text before its first `/`
(`"orders/2026/17"` → group `"orders"`; a key without `/` is its own group).

**Aggregate.** For every group the engine maintains `row_count` and
`value_bytes` (sum of value lengths).

**API** (add to `TruthStore`):

- `group_stats(group) -> GroupStats(row_count, value_bytes, served_from)`
  where `served_from` is `"LENS"` or `"SOURCE"`.
- `group_stats_source(group)` — always computes from Source rows; this is
  the reference path and must stay simple.
- `lens_enabled` becomes `True` when a valid Lens is loaded.

**Maintenance rules.**

1. A table `opdb_meta` holds a commit sequence number. `apply()` increments
   it in the same transaction as the data change.
2. `apply()` computes the per-group delta of its own batch (it must read the
   old value length of overwritten or deleted keys inside the transaction)
   and applies the delta to the in-memory Lens only after `COMMIT` succeeds.
   No SQLite triggers.
3. The Lens remembers the sequence number and `PRAGMA data_version` it is
   valid for. Before answering from the Lens, compare both with the
   database. On any mismatch: answer from Source, discard the Lens, rebuild.
4. On open, the Lens is rebuilt from one consistent snapshot. Nothing about
   the Lens needs to be stored on disk in 0.1.
5. If `apply()` fails or rolls back, the Lens must be unchanged.

## Tests that must exist and pass

- **Oracle equality.** Seeded random sequences of put / overwrite / delete /
  batch (at least 20 seeds × 2,000 operations): after every operation
  `group_stats(g)` equals `group_stats_source(g)` and equals an independent
  Python-dict model, for every group touched.
- **Rollback.** A batch that fails validation or aborts mid-transaction
  leaves Lens answers unchanged.
- **Crash.** Kill the process (`os._exit`) before commit and after commit;
  after reopen Lens answers equal Source.
- **Outside write.** A second raw SQLite connection changes a row; the next
  `group_stats` must report `served_from == "SOURCE"` with the correct
  numbers, and later calls return to `"LENS"` after rebuild.
- **Edge cases.** Empty value, empty group result, key without `/`, group
  that becomes empty, overwrite with a different length, 10,000-operation
  batch touching one key many times.
- All 43 existing Core tests keep passing unchanged.

## Measurement (report, not a gate)

Add `experiments/lens_bench.py` printing, for 10k / 100k / 1M rows and
100-byte values on a local file database:

- `group_stats` via Lens vs `group_stats_source` (median and p99),
- `put` and 1,000-row `apply` throughput with the Lens on vs off,
- Lens rebuild time on open, and peak memory of the Lens.

Put the numbers and the machine description in the PR text. If the Lens
does not beat Source reads, or write overhead exceeds 20%, say so plainly —
that is an acceptable result for this task.

## Rules for this task

- Touch only `opdb/`, `tests/`, `experiments/lens_bench.py` and one short
  doc `docs/LENS_0.1.md`.
- Do not add or change workflows, gates, preflights, handoff schemas or
  status reports. Do not edit or delete existing tests.
- Standard library only. Keep the change under roughly 600 added lines
  including tests.
- No performance claim against other databases; only Lens vs Source.
- Done means: tests green in CI on the PR, benchmark numbers in the PR
  text, owner review. The owner merges.

## Not in this task

Persisted Lens, multiple Lens kinds, SQL, multi-process writers, a native
storage engine, adaptive or predictive controllers.
