# TASK-038 — M5: benchmark transactions, rollback and crash recovery

## Goal
Add the transaction workloads: many small committed transactions, a rolled-back
transaction that must leave no trace, and recovery after a process that dies in the
middle of a transaction. Each check is a correctness result first and a timing
second.

## What to build
Depends on TASK-037 being merged. Add:
- `experiments/bench/transactions.py` with:
  - `commit_many(contender, rows, per_txn=100)`: writes the rows in transactions
    of 100 (one commit each) and returns the number of commits;
  - `rollback_check(contender, rows)`: writes some rows, then starts a batch of 100
    further rows and rolls it back, and returns the keys that are visible after the
    rollback (must be none of the rolled-back keys);
  - `crash_check(path, rows)`: runs a child Python process
    (`subprocess.run([sys.executable, "-c", code])`) that opens a SQLite file, commits
    the first 200 rows, begins a transaction, inserts 100 more rows without
    committing and calls `os._exit(1)`; the parent reopens the file and returns the
    set of present keys (must be exactly the first 200 rows) and the result of
    `PRAGMA integrity_check`.
- Methods on `SqliteContender`: `begin()`, `insert(rows)`, `commit()`,
  `rollback()` (explicit transaction control with `isolation_level=None`).
- `OpdbSourceContender` and `OpdbNumericContender`: `rollback_check` uses `apply`
  with a batch that ends in an invalid operation (for example a put with a value
  of the wrong size for the numeric contender, or an unknown operation name for the
  source contender); `apply` raises `ValueError` and nothing from that batch may be
  visible. `crash_check` is `NOT_IMPLEMENTED` for the OpDB contenders (their
  `apply` cannot be interrupted from outside).
- `experiments/bench/run.py` (complete file): workloads `txn_commit` (timed),
  `txn_rollback` and `txn_crash` (correctness verdicts `PASS` or `FAIL`, no
  timing). A failed check aborts the run.

## Tests that must exist
New file `tests/test_bench_txn_038.py`, about 120 lines or fewer:
1. `commit_many` on 1,000 rows returns 10 commits and every row is present.
2. `rollback_check` returns no rolled-back key for SQLite, for `opdb_source` and
   for `opdb_numeric_lens` (8-byte values); the rows written before the batch are
   still present.
3. `crash_check` on SQLite returns exactly the first 200 keys and
   `integrity_check` is `ok`.
4. `run.main` output has `txn_commit` timing rows, `PASS` verdicts for rollback on
   all contenders and for crash on SQLite, and `NOT_IMPLEMENTED` crash rows for
   the OpDB contenders.
- Close every connection before the temporary directory is removed (needed on
  Windows). Existing tests must pass unchanged.

## Notes checked against the engine
- A SQLite transaction that is not committed when the process exits is rolled
  back on the next open; with WAL the file stays consistent.
- `TruthStore.apply` validates the whole batch before writing: any invalid
  operation raises `ValueError` and leaves Source unchanged (checked in TASK-034).

## Measurement
None.

## Scope
Two files changed or added plus one test file, about 600 lines or fewer together.
Standard library only. One task PR. No protected files, no changes to `opdb/`, no
paid models.
