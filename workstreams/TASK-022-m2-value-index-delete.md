# TASK-022 — M2: measure numeric Lens value-index deletion strategy

## Goal
TASK-016 found no removable overhead in its broad profile. Test a narrower,
previously unmeasured hypothesis: the tuple IN (VALUES ...) deletion in
NumericTruthStore.apply may use a less efficient SQLite query plan than
individual primary-key deletes. Measure rather than assume a gain.

## What to build
- Inspect EXPLAIN QUERY PLAN for the existing deletion and a parameterized
  DELETE WHERE g=? AND x=? AND k=? executed with executemany, on the actual
  schema and SQLite version. Record plans and affected row counts.
- Compare the existing implementation with the candidate on identical
  fixtures, preserving the transaction, durability, missing-entry detection,
  Source writes, commit sequence and overflow behavior. Do not change schema.
- Keep the candidate only if repeatable end-to-end batch measurements improve
  overwrite/delete without material insert regression; otherwise retain the
  existing engine and publish the negative result.

## Tests that must exist
- New seeded mixed-batch tests against direct SQLite Source recomputation and
  a plain Python dict (at least 20 seeds); cover repeated keys, absent deletes,
  equal numeric values across keys, min/max removal, Unicode, signed limits,
  rollback and second-store writes, including reopen.
- Inject a missing value-index entry and verify the existing integrity failure
  and rollback are preserved. Existing tests must pass unchanged.

## Measurement
Use 10k and 100k initial rows, 1,000 operations per batch, insert/overwrite/
delete and mixed repeated keys, at least 30 batches per scenario and three
paired repetitions on one machine. Restore identical fixtures outside timing;
alternate baseline/candidate order. Record raw timings, median/p95, exact SHA,
CPU/RAM/OS/Python/SQLite, journal and synchronous settings. Report statement
and end-to-end costs separately. No million-row run required for this task.
Do not claim M2 complete without a comparable M1 baseline.

## Scope
opdb/numeric.py, experiments/, new tests and a short measurement document.
Standard library only, about 600 added lines including tests, one task PR.
No protected files, schema changes, weakened checks, deployment or paid models.
Acceptance follows AGENTS.md; negative measurements are valid.
