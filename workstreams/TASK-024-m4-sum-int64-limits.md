# TASK-024 — M4: sum at signed 64-bit limits and on overflow

## Goal
Show, against Python integers, that `NumericTruthStore` gives the right
`total` for sums that reach or leave the signed 64-bit range, and that a
sum overflow never produces a wrong answer. Test-only task: the engine is not
changed.

## What to build
- One new test file `tests/test_numeric_sum_limits_024.py`. Follow the helpers
  and constructor arguments of `tests/test_numeric_lens_014.py` (read it
  first); do not import from other test files.
- Read `opdb/numeric.py` first: `INT64_MIN`, `INT64_MAX`, `LensOverflow` and the
  code after the `overflow` flag in `apply`. A group sum outside the 64-bit range
  leaves the stored Lens untrusted, and answers must then come from Source.
- Scenarios, each compared with the oracle:
  - a group whose sum is exactly `INT64_MAX`, and exactly `INT64_MIN`;
  - single values `INT64_MAX` and `INT64_MIN`;
  - a batch that pushes a group sum one past `INT64_MAX`, and one past
    `INT64_MIN`;
  - a batch that overflows one group while another group stays in range;
  - a later batch that brings the overflowed group back into range.

## Tests that must exist
- After every batch compare `count`, `total`, `minimum`, `maximum` from both
  `numeric_stats(g)` and `numeric_stats_source(g)` with Python integer
  arithmetic on a plain dict model (Python ints do not overflow). Do **not**
  assert `served_from == "LENS"` for a group that overflowed: either
  `"LENS"` or `"SOURCE"` is accepted, but the numbers must equal the model.
- Reopen the store on the same file after an overflowing batch and compare again.
- Existing tests must pass unchanged. If a new check fails because of an
  engine defect, keep the failing test and describe the defect in the pull request
text; do not change the engine.

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
