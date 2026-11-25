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
- Build a store in a temporary file with a seeded random starting state (at
  least 100 keys in several groups, group of a key is the part before the first
  `/`), then `close()` it.
- Inject a failure that happens inside the transaction, with a separate
  `sqlite3` connection, while the store is closed:
  `CREATE TRIGGER boom BEFORE DELETE ON opdb_nlens_val BEGIN SELECT RAISE(ABORT, 'injected failure'); END`
  and commit. Reopen the store on the same file.
- Before the failing batch, copy the whole Source out with an independent
  `sqlite3` connection (`SELECT k, v FROM opdb_source_kv ORDER BY k`) and record
  `numeric_stats(g)` (count, total, minimum, maximum) for every group.
- Run a mixed batch with `apply`: new keys, an overwrite of an existing key,
  and a delete of an existing key (the delete fires the trigger). The engine
  raises `sqlite3.IntegrityError`; assert exactly that class with
  `assertRaises`.

## Tests that must exist
- After the failed batch: a new copy of Source from an independent connection
  equals the copy taken before; none of the new keys exists.
- For every group, `numeric_stats(g)` and `numeric_stats_source(g)` of the same
  store object equal the recorded values and a plain Python dict model of the
  state before the batch (count, total, minimum, maximum).
- `close()` the store, reopen it on the same file and compare again; also open a
  second store object on the same file and compare.
- Run at least 10 seeds with different victim keys. Close every store before
  the temporary directory is removed.
- Existing tests must pass unchanged. If a new check shows that data was
  partly written, keep the failing test and describe the defect in the pull
  request text; do not change the engine.

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
