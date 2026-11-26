# TASK-027 — M3: damaged stored Lens metadata is detected at open and rebuilt

## Goal
Show that `NumericTruthStore` notices damage to the stored Lens metadata and
group table when the file is opened, rebuilds the Lens from Source, and then
answers exactly like a plain Python model. Test-only task: the engine is not
changed.

## What to build
- One new test file `tests/test_numeric_stored_lens_027.py`. Follow the helpers
  and constructor arguments of `tests/test_numeric_lens_014.py` (read it first);
  do not import from other test files.
- For every scenario build a fresh store file with seeded random content (at
  least 50 keys in at least 3 groups, keys of the form `group/name`), `close()`
  it, damage the file through a separate `sqlite3` connection, then open it
  again with `NumericTruthStore(path)`.
- The damage statements and the exact `open_reason` the engine reports:

  | Damage (SQL) | `open_reason` |
  | --- | --- |
  | `UPDATE opdb_nlens_group SET n = -1 WHERE g = '<existing group>'` | `corrupt Lens row` |
  | `UPDATE opdb_nlens_group SET n = n + 1 WHERE g = '<existing group>'` | `Lens rows disagree with stored totals` |
  | `DELETE FROM opdb_nlens_meta` | `missing metadata` |
  | `UPDATE opdb_nlens_meta SET schema_version = 99` | `incompatible schema version` |
  | `UPDATE opdb_nlens_meta SET lens_seq = lens_seq + 5` | `stale generation` |
  | `UPDATE opdb_nlens_meta SET grouping = 'other'` | `grouping function changed` |

## Tests that must exist
- Undamaged file: reopening gives `open_mode == "PERSISTED"` and
  `open_reason == ""`.
- For each damage in the table: after reopening `open_mode == "REBUILT"` and
  `open_reason` equals the table value; for every group (and one group that
  does not exist) `numeric_stats(g)` and `numeric_stats_source(g)` equal a plain
  Python dict model (count, total, minimum, maximum), and
  `numeric_stats(g).served_from == "LENS"`. Close, open once more: now
  `open_mode == "PERSISTED"`.
- Damage to the value index only, `UPDATE opdb_nlens_val SET x = x + 1000 WHERE
  k = '<existing key>'`, is not looked at while opening: `open_mode` stays
  `"PERSISTED"`, and `numeric_stats(g)` still returns numbers equal to the
  model (do not assert which of `"LENS"` or `"SOURCE"` serves it).
- Existing tests must pass unchanged. If a new check shows an engine defect,
  keep the failing test and describe the defect in the pull request text.

## Notes checked against the engine
- A group is the part of a key before the first `/`. `numeric_stats(g)` and
  `numeric_stats_source(g)` take the group name, never the full key.
- Values are 8-byte big-endian signed integers: `x.to_bytes(8, "big", signed=True)`.
- `open_mode` is one of `PERSISTED`, `REBUILT`, `SOURCE_FALLBACK`; `open_reason`
  is a string, empty when nothing was wrong.
- Open a fresh file for every scenario and `close()` every store before the
  temporary directory is removed (needed on Windows).
- Do NOT write to `opdb_source_kv` behind the store's back: such a write is not
  noticed at open today, so no test may rely on it.

## Measurement
None.

## Scope
One new file under `tests/`, about 200 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
