# TASK-032 — M3: rebuild and reopen keep the answers

## Goal
Show, against a plain Python dict model, that `NumericTruthStore` gives the same
answers across many batches, explicit `rebuild()` calls and close/reopen cycles,
and that a healthy file reopens without a rebuild. Test-only task: the engine is
not changed.

## What to build
- One new test file `tests/test_numeric_rebuild_reopen_032.py`. Follow the
  helpers of `tests/test_numeric_lens_014.py` (read it first); do not import
  from other test files.
- A seeded random test with at least 20 seeds. Per seed: a fresh file, 30
  random batches of 1 to 6 operations (put and delete, keys of the form
  `g<0..3>/k<0..9>`, values between -50 and 50) over a dict model. After every
  batch compare `numeric_stats(g)` and `numeric_stats_source(g)` for every
  group plus one unknown group with the model (count, total, minimum,
  maximum). Every 10th batch alternate:
  - close the store and open the same file again: `open_mode == "PERSISTED"`
    and `open_reason == ""`, answers equal the model;
  - call `store.rebuild()`: answers do not change.
- Also: calling `rebuild()` twice in a row changes nothing; a rebuilt file
  reopens with `open_mode == "PERSISTED"`.

## Tests that must exist
- The seeded test above and the two extra checks.
- Existing tests must pass unchanged. If a new check shows an engine defect,
  keep the failing test and describe the defect in the pull request text.

## Notes checked against the engine
- A group is the part of a key before the first `/`; `numeric_stats(g)` takes the
  group name.
- Values are 8-byte big-endian signed integers: `x.to_bytes(8, "big", signed=True)`.
- A BRAND-NEW empty file reports `open_mode == "REBUILT"` on its first open (it has
  no stored Lens yet); only a file that was written and closed reopens as
  `"PERSISTED"`. Check `open_mode` only on reopen, never on the first open.
- `numeric_stats(g).served_from` is `"LENS"` after these operations.
- Open a fresh file for every seed and `close()` every store before the
  temporary directory is removed (needed on Windows).

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
