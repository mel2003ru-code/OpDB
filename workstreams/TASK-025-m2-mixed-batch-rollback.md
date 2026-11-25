# TASK-025 — M2: failed mixed batch leaves Source and Lens unchanged

## Goal
Show that when a mixed batch (insert, overwrite, delete) fails inside the
transaction, `NumericTruthStore` rolls back completely: Source rows and all
answers equal the state before the batch. Test-only task: the engine is not
changed.

## What to build
- One new test file `tests/test_numeric_rollback_025.py`. Follow the helpers and
  constructor arguments of `tests/test_numeric_lens_014.py` (read it first);
  do not import from other test files.
- Build a store with a seeded random starting state (at least 200 keys in
  several groups). Before the failing batch, copy the whole Source out with an
  independent `sqlite3` connection (`SELECT k, v FROM opdb_source_kv`) and
  record `numeric_stats` for every group.
- Inject a failure that happens **inside** the transaction: with a separate
  `sqlite3` connection delete one row of the value-index table
  `opdb_nlens_val` that belongs to a key the next batch will delete or overwrite
  (read `opdb/numeric.py` to see which table and columns exist). Then call
  `apply` with a mixed batch (new keys, an overwrite, that delete). Expect the
  integrity exception the engine raises today (read the code; assert the
  exception class that it actually raises, do not invent one).

## Tests that must exist
- After the failed batch: the Source copy from an independent connection is
  byte-for-byte the same as before; no new key from the batch exists.
- Answers after the failure equal the plain Python dict model of the state
  before the batch (use `numeric_stats_source`; do not require `LENS`).
- Run at least 10 seeds with different failing keys.
- A second store opened on the same file sees the same Source state.
- Existing tests must pass unchanged. If a new check shows that data was
  partly written, keep the failing test and describe the defect in the pull request
text; do not change the engine.

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
