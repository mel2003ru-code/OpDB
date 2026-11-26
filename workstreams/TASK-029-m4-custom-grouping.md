# TASK-029 — M4: caller-defined grouping, groups appearing and disappearing

## Goal
Show, against a plain Python model, that a `NumericTruthStore` with a
caller-defined grouping function answers correctly while groups appear and
disappear inside batches, and that the grouping name is honoured when the file
is reopened. Test-only task: the engine is not changed.

## What to build
- One new test file `tests/test_numeric_grouping_029.py`. Follow the helpers of
  `tests/test_numeric_lens_014.py` (read it first); do not import from other
  test files.
- Open stores with
  `NumericTruthStore(path, groupers={"first2": lambda k: k[:2]}, grouping="first2")`
  (a module-level function is better than a lambda, the store keeps a
  reference). The group of a key is then its first two characters; keys such as
  `"ab1"`, `"cd7"`, `"é9x"` and one-character keys such as `"a"` are valid.
- Scenarios, each compared with the model after every batch:
  - a batch that creates two new groups at once;
  - a batch that deletes the only key of a group (the group disappears:
    `count 0, total 0, minimum None, maximum None`, served from the Lens) and
    in the same batch creates a different group;
  - a batch that overwrites a key, deletes another key of the same group and
    adds a third one;
  - a group that disappears and later appears again.
- Reopen on the same file with the same grouping: `open_mode == "PERSISTED"`
  and answers still equal the model. Reopen with the default grouping
  (`NumericTruthStore(path)`): `open_mode == "REBUILT"`,
  `open_reason == "grouping function changed"`, and answers equal a model that
  groups by the part of the key before the first `/` (a key without `/` is its
  own group).

## Tests that must exist
- A seeded random test with at least 20 seeds mixing put, overwrite and delete
  batches over a small pool of keys; the model is a `defaultdict(list)` built
  with the same grouping function. Compare `numeric_stats(g)` and
  `numeric_stats_source(g)` for every group of the pool plus one unknown group
  after every batch (count, total, minimum, maximum), and `served_from ==
  "LENS"` for `numeric_stats`.
- The explicit scenarios above, then the two reopen checks.
- Existing tests must pass unchanged. If a new check shows an engine defect,
  keep the failing test and describe the defect in the pull request text.

## Notes checked against the engine
- `numeric_stats(g)` and `numeric_stats_source(g)` take the group name produced
  by the grouping function, never the full key.
- Values are 8-byte big-endian signed integers: `x.to_bytes(8, "big", signed=True)`.
- Open a fresh file for every scenario and `close()` every store before the
  temporary directory is removed (needed on Windows).

## Measurement
None.

## Scope
One new file under `tests/`, about 200 lines or fewer. Standard library only.
One task PR. No protected files, no source changes, no schema changes, no paid
models.
