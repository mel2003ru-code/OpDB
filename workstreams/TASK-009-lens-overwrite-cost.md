# TASK-009 — Measure and trim the cost of overwriting existing keys

- Milestone: M2 (closes it)
- Depends on: TASK-007 (merged as PR #45)
- Deliverable: one pull request against `main`

## Problem

TASK-007 cut the overhead of a 1,000-row batch of *new* keys. The journal
notes that overwriting existing keys is the most expensive case with a Lens
(the old length must be read for every row) and that
`experiments/lens_bench.py` does not measure it. M2 cannot be called done
until this case has a number.

## What to build

1. **Benchmark scenarios.** In `experiments/lens_bench.py` add, next to the
   current new-key batches, three batch kinds on a 1,000-row batch:
   `overwrite` (every key already exists, new value of different length),
   `delete` (existing keys), and `mixed` (one third each of new, overwrite,
   delete). Report the median batch time and the Lens-vs-Source overhead for
   each, for 10k, 100k and 1M rows, at least 30 batches each. Existing output
   keys must stay unchanged.
2. **Cheaper lookup, only if the numbers show it matters.** If overwrite
   overhead is more than +60% in the measurement, try to reduce it inside
   `TruthStore.apply` (for example fewer Python-level passes over the batch,
   or sorted key chunks so the primary-key lookups are sequential). Keep a
   change only if it lowers the measured overhead and every test passes; if
   nothing helps, change no engine code and report that as the result.

## Tests that must exist and pass

- New seeded oracle test (new file under `tests/`): 20 seeds, batches that
  overwrite existing keys with values of length 0, shorter, equal and longer,
  and delete-then-reinsert; Lens equals Source equals a plain Python dict
  model after every batch.
- A benchmark smoke test: the new scenarios run on a 2,000-row file with
  3 batches and return the expected keys.
- Every existing test passes unchanged.

## Measurement

Tables for all three scenarios and all three sizes, before and after the
change if engine code changed, with the machine description, in the pull
request text. A negative result (no improvement possible) is a valid outcome.

## Scope

Touch only `opdb/`, new files under `tests/`, `experiments/lens_bench.py`,
`experiments/README.md` if it lists benchmark output, and the status cell in
`workstreams/BACKLOG.md`. No triggers. No stored Lens (that is M3, see the
draft PR #50).
