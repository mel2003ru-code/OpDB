# TASK-014 — M4: numeric aggregates (sum, min, max) with caller-defined grouping

- Milestone: M4 — More than one Lens
- Depends on: TASK-012 (DONE); start after TASK-013 is merged or if its PR is not open

## Goal
Today the Lens answers one question: row count and value bytes per key prefix. Add a second Lens kind that answers `sum`, `min`, `max` (and count) over a numeric value, grouped by a caller-supplied grouping function, and answers every query identically to recomputation from Source.

## What to build
1. A numeric Lens on `TruthStore` (opt-in, existing Lens unchanged). Values are 8-byte big-endian signed integers; a value of any other length or type is rejected by the Lens with a clear error and never silently ignored. Grouping is a named, deterministic Python function registered when the store is opened and recorded by name in the file.
2. `sum` and `count` are maintained incrementally. `min`/`max` cannot be maintained on delete or overwrite of the current extreme without a lookup: implement a correct rule (e.g. per-group lookup of the new extreme from Source for only the affected group) and document its cost. A Lens answer that differs from Source is release-blocking.
3. Persisted variant stored in the same SQLite transaction, with the same bounded open validation as TASK-012; a changed grouping-function name or a stale generation means untrusted and rebuilt from Source.
4. Overflow: if a group sum leaves the signed 64-bit range the Lens must fall back to Source (which uses Python ints) rather than wrap.

## Tests that must exist (new files only)
- At least 20 seeds of put/overwrite/delete/reinsert/batch, comparing the Lens with (a) a SQL recomputation over Source and (b) a Python dict model, after each batch and after reopen; negative numbers, zero, ties for min/max, deleting the only extreme, empty groups.
- Overflow, wrong-width value, grouping-name mismatch, second store on the same file, raw write to Source while open.
- Existing tests unchanged and green.

## Measurement
Read of one group's sum/min/max versus recomputation from Source, and 1,000-row batch overhead, at 10k, 100k and 1M rows; medians over at least 15 runs, machine and SHA recorded. Report negative results as they are.

## Scope limits
`opdb/`, `experiments/`, new files in `tests/`, a short note under `docs/`. Standard library only; no protected files, native-engine or disk-format decisions. About 600 lines or fewer; if larger, split off the persisted variant as a follow-up and say so.
