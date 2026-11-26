# TASK-034 — M2: an invalid batch is rejected and changes nothing

## Goal
Show that `NumericTruthStore.apply` rejects every invalid operation with a
`ValueError` before it writes anything, even when the invalid operation is the
last one of a batch whose earlier operations are valid. Test-only task: the
engine is not changed.

## What to build
- One new test file `tests/test_numeric_validation_034.py`. Follow the helpers
  of `tests/test_numeric_lens_014.py` (read it first); do not import from other
  test files.
- Start from a store with a few valid keys in two groups. Before each invalid
  batch read Source independently with `sqlite3`
  (`SELECT k, v FROM opdb_source_kv ORDER BY k`) and record `numeric_stats(g)`
  for every group. For each invalid batch below: `apply` raises `ValueError`
  (use `assertRaises(ValueError)`), Source read again is identical to before,
  and the recorded `numeric_stats` answers are unchanged.
- The invalid batches (each also in a variant where a valid put comes FIRST in
  the same batch):
  - a put whose value is not exactly 8 bytes (for example `b"abc"`);
  - an unknown operation name, `("upsert", "a/1", value)`;
  - an item that is not a tuple, for example the string `"put"`;
  - a put with too few elements, `("put", "a/1")`;
  - a delete with too many elements, `("delete", "a/1", b"x")`;
  - a key that is not a string, `("put", 5, value)`;
  - a key that contains a NUL character, `("put", "a\x00b", value)`.

## Tests that must exist
- The scenarios above, with the valid-first variants.
- After all the rejected batches a normal valid batch still works and the
  answers equal a plain Python dict model.
- Existing tests must pass unchanged. If a new check shows an engine defect,
  keep the failing test and describe the defect in the pull request text.

## Notes checked against the engine
- All of the invalid batches above raise `ValueError` today and leave Source
  byte for byte unchanged, including the valid-first variants.
- A group is the part of a key before the first `/`; `numeric_stats(g)` takes the
  group name.
- Values are 8-byte big-endian signed integers: `x.to_bytes(8, "big", signed=True)`.
- Open a fresh file for every scenario and `close()` every store before the
  temporary directory is removed (needed on Windows).

## Measurement
None.

## Scope
One new file under `tests/`, about 150 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
