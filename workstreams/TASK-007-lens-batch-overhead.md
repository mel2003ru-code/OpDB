# TASK-007 — Cheaper batch writes with a Lens

- Milestone: M2
- Depends on: TASK-006 (merged as PR #41)
- Deliverable: one pull request against `main`

## Problem

With the Lens on, `apply()` runs one extra `SELECT` per operation to learn
the old value length. Measured on PR #41: a 1,000-row batch is 50–110%
slower with the Lens than without. Single `put` is dominated by fsync and
is barely affected.

## What to build

1. **Batched lookup of old lengths.** Before the write loop, fetch
   `k, typeof(v), length(v)` for the distinct keys of the batch in chunks
   (`WHERE k IN (...)`, at most 500 keys per statement), still inside the
   `BEGIN IMMEDIATE` transaction. Track the running state of each key in
   memory while walking the batch, so a key that appears many times in one
   batch is handled without further queries. Deltas must stay exact.
2. **Open with a damaged row.** Today `TruthStore(path, lens=True)` raises
   if any Source row breaks the typed contract. It must open with the Lens
   disabled instead (`lens_enabled == False`, `group_stats` served from
   `SOURCE`); reads of the damaged row keep raising `SourceIntegrityError`
   as before.
3. **Benchmark stability.** `experiments/lens_bench.py`: default to at
   least 30 batches and report the median batch time, so the overhead
   figure is repeatable.
4. **Doc fix.** `docs/LENS_0.1.md`, first paragraph: the sentence is broken
   around the stray text `NaN`; restore it.

## Tests that must exist and pass

- New seeded oracle test for batches: 20 seeds, batches of 1–2,000
  operations with heavy key repetition inside a batch (put, overwrite,
  delete, delete-then-put of the same key), Lens equals Source equals a
  Python-dict model after every batch.
- A batch larger than one lookup chunk (more than 500 distinct keys) with
  a mix of existing and new keys.
- Open-with-damaged-row test for point 2.
- Every existing test passes unchanged.

## Measurement

Run the benchmark before and after on the same machine for 10k, 100k and
1M rows and put both tables in the pull request text.

Done when the 1,000-row batch overhead is at least one third lower than
before at every size. A quick prototype of the batched lookup gave about
+34% against +59% for the per-row lookup on a 100k-row file, so the last
part of the overhead is probably not removable while SQLite performs the
write: the engine cannot see the old row during its own upsert. If the
target is missed, report the numbers and say what limits them.

## Scope

Touch only `opdb/`, new files under `tests/`, `experiments/lens_bench.py`,
`docs/LENS_0.1.md` and the status cell in `workstreams/BACKLOG.md`.
No triggers. No stored Lens (that is M3).
