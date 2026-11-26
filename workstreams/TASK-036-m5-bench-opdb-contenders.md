# TASK-036 — M5: benchmark OpDB contenders (Source and numeric Lens)

## Goal
Add the OpDB participants to the benchmark of TASK-035 so that SQLite, OpDB Source
(`TruthStore`) and the OpDB numeric Lens run the same workloads on the same data.
The result is measurement code, not a speed claim.

## What to build
Depends on TASK-035 being merged. Add or change:
- `experiments/bench/opdb_contenders.py` with two classes that have the same
  interface as `SqliteContender` (`name`, `bulk_insert(rows, batch=1000)`, `get`,
  `count`, `close`, plus a class method `applicable(value_bytes)`):
  - `OpdbSourceContender` (`name = "opdb_source"`): `TruthStore(path)`;
    `bulk_insert` calls `apply` with batches of `("put", key, value)`; `get` calls
    `store.get`; `count()` reads `SELECT count(*) FROM opdb_source_kv` through an
    independent `sqlite3` connection. Applicable for every value size.
  - `OpdbNumericContender` (`name = "opdb_numeric_lens"`): `NumericTruthStore(path)`;
    applicable only when `value_bytes == 8` (the numeric Lens stores 8-byte
    big-endian signed integers).
- `experiments/bench/data.py` (complete file): `make_rows(n, seed, value_bytes,
  numeric=False)`; when `numeric` is true and `value_bytes == 8` the value of row
  `n` is `random.Random(seed * 1000003 + n).randint(-2**40, 2**40).to_bytes(8,
  "big", signed=True)`. Values near the 64-bit limits would overflow group sums
  and silently switch the Lens off, so the range must stay at +-2^40.
- `experiments/bench/run.py` (complete file): a registry of contenders, a
  `--contenders` option (default all), `numeric=True` is used when the numeric
  contender takes part and `--value-bytes` is 8. A contender that is not
  applicable gets one result row `{"contender", "status": "NOT_APPLICABLE",
  "reason": ...}` and is never timed. Every other row keeps the TASK-035 shape.

## Tests that must exist
New file `tests/test_bench_opdb_036.py`, about 120 lines or fewer:
1. For each applicable contender: insert 2,000 rows, every `get` equals the
   generated value, `count()` is 2,000.
2. `applicable(16)` is false for the numeric contender and true for the source
   contender; with `--value-bytes 16` the JSON has a `NOT_APPLICABLE` row for the
   numeric contender and verified rows for SQLite and `opdb_source`.
3. With `--value-bytes 8` the JSON has verified rows for all three contenders.
4. `make_rows(..., numeric=True)` gives 8-byte values that decode into
   +-2^40, deterministic for a seed.
- Close every store before the temporary directory is removed. Existing tests
  must pass unchanged.

## Notes checked against the engine
- `from opdb import TruthStore, NumericTruthStore`. `TruthStore.apply` takes up to
  10,000 operations per call; `TruthStore.get` returns the stored bytes or `None`.
- A group is the part of a key before the first `/`.

## Measurement
None.

## Scope
Three files plus one test file, about 600 lines or fewer together. Standard
library only. One task PR. No protected files, no changes to `opdb/`, no paid
models.
