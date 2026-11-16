# TASK-015 — M5: same aggregate workload on plain SQLite and OpDB

- Milestone: M5 — Honest comparison harness
- Depends on: TASK-014 (DONE)
- Deliverable: **one pull request** against `main`
- Related: draft PR #48 (LAB-001) is an unmerged pilot; do not build on it or
  touch it. This task is independent and measures write cost as well.

## Goal
Measure, on one machine, how OpDB's numeric Lens compares with the two
ways a developer would do the same job in plain SQLite: (A) a covering index
on (group, value) with the aggregate computed by a query, and (B) a summary
table kept up to date by SQL triggers. Scripts and raw numbers go in the
repository. Negative results are valid and must be reported as they are.

## What to build
1. `experiments/m5_compare.py` (standard library only, `--sizes`, `--seed`,
   `--runs`, `--json PATH`). One fixture generator shared by all contenders:
   keys `grp<i>/<n>`, 8-byte signed values, fixed seed, about 1,000 groups.
2. Contenders on the same rows: **A** `sqlite3` table + index, aggregate by
   `SELECT count,sum,min,max ... WHERE g=?`; **B** `sqlite3` table + summary
   table maintained by INSERT/UPDATE/DELETE triggers (min/max via index
   lookup on the affected group); **C** `NumericTruthStore` (Lens);
   **D** `NumericTruthStore.numeric_stats_source` (Source recomputation).
   Same `journal_mode` and `synchronous` for all, recorded in the output.
3. Workloads: one-group aggregate read; 1,000-row batch of new keys;
   1,000-row batch of overwrites; 1,000-row batch of deletes; database file
   size; time to open an existing 1M-row file.
4. Before any timing is accepted, every contender's answers for all groups
   must equal an independent Python dict model; abort the run on mismatch.

## Tests that must exist (new files only)
- `tests/test_m5_compare.py`: on a 2,000-row fixture with at least 5 seeds,
  contenders A, B, C, D agree with the dict model after put / overwrite /
  delete batches, including deleting the only extreme of a group.
- The script's `--json` output has every contender and workload filled in.
- Existing tests unchanged and green.

## Measurement
Sizes 10k, 100k, 1M; medians over at least 15 runs; record machine, Python
and SQLite versions, git SHA. Put the table in `docs/M5_COMPARISON.md` and
state plainly where OpDB loses (write cost, file size, open time) as well
as where it wins. Claim nothing about databases other than those measured.

## Scope limits
`experiments/`, new files in `tests/`, `docs/M5_COMPARISON.md`. No change to
`opdb/` unless a correctness bug is found (then fix it separately and say
so). About 600 lines or fewer, tests included.
