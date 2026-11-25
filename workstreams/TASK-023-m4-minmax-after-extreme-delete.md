# TASK-023 — M4: min/max after deleting the current extreme

## Goal
Show, with an independent oracle, that `NumericTruthStore` returns the correct
`minimum` and `maximum` after the current extreme of a group is deleted or
overwritten, including ties, negative values and non-ASCII keys. This is a
test-only task: the engine is not changed.

## What to build
- One new test file `tests/test_numeric_extreme_023.py`. Follow the helpers and
  constructor arguments of `tests/test_numeric_lens_014.py` (read it first);
  do not import from other test files, copy what you need.
- Scenarios, each checked after every batch against the oracle:
  - delete the unique minimum, then the unique maximum of a group;
  - delete one of several keys that tie for the minimum (the minimum must stay);
  - overwrite the maximum with a smaller value, and the minimum with a larger one;
  - negative values and `0`; Unicode group names and keys;
  - a group that becomes empty (stats: count 0, total 0, min and max `None`)
    and then receives new rows.

## Tests that must exist
- A seeded random test with at least 20 seeds mixing put/overwrite/delete
  batches; after each batch compare `numeric_stats(g)` and
  `numeric_stats_source(g)` for every group with a plain Python dict model
  (group value lists, `min`/`max`/`sum`/`len`). Neither oracle may call the
  code under test. Also check `served_from == "LENS"` for `numeric_stats`.
- Reopen the store on the same file after the last batch and compare again.
- Existing tests must pass unchanged. If a new check fails because of an
  engine defect, do not change the engine: keep the failing test and describe
  the defect in the pull request text.

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
