# TASK-030 — M2: order of operations inside one batch

## Goal
Show, against a plain Python dict model, that `NumericTruthStore.apply` handles
repeated keys inside one batch in order: the last operation on a key wins.
Test-only task: the engine is not changed.

## What to build
- One new test file `tests/test_numeric_batch_semantics_030.py`. Follow the
  helpers of `tests/test_numeric_lens_014.py` (read it first); do not import
  from other test files.
- Explicit scenarios, each compared with the model after the batch:
  - two puts of the same key in one batch: the second value wins;
  - put then delete of the same key: the key is absent;
  - delete then put of the same key: the key is present with the new value;
  - a delete of a key that never existed, together with a valid put: allowed,
    the put is applied;
  - an empty batch `apply([])`: no error and nothing changes;
  - overwriting a key with the value it already has: answers do not change.
- Source is read independently with `sqlite3`
  (`SELECT k, v FROM opdb_source_kv ORDER BY k`) and compared with the model
  after every batch, in addition to `numeric_stats` and `numeric_stats_source`.

## Tests that must exist
- The explicit scenarios above.
- A seeded random test with at least 20 seeds: random batches of 1 to 8
  operations over a small pool of keys so that keys repeat inside one batch,
  mixing put and delete. The model applies the operations of each batch in
  order to a dict. After every batch compare the independent Source read and,
  for every group of the pool plus one unknown group, `numeric_stats(g)` and
  `numeric_stats_source(g)` (count, total, minimum, maximum) with the model.
- Existing tests must pass unchanged. If a new check shows an engine defect,
  keep the failing test and describe the defect in the pull request text.

## Notes checked against the engine
- A group is the part of a key before the first `/`; `numeric_stats(g)` takes the
  group name. Use keys of the form `group/name`.
- Values are 8-byte big-endian signed integers: `x.to_bytes(8, "big", signed=True)`.
- `store.get(key)` returns the stored 8 bytes, or `None` for an absent key.
- After these batches `numeric_stats(g).served_from` is `"LENS"`.
- Open a fresh file for every scenario and `close()` every store before the
  temporary directory is removed (needed on Windows).

## Measurement
None.

## Scope
One new file under `tests/`, about 200 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
