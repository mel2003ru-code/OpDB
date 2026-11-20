# TASK-018 — M6 experiment: Rust storage v0 (no SQLite, no stable format)

- Milestone: M6 (owner decision of 2026-11-19 in issue #74: Rust is approved in #53, the experiment may start; **no permanent on-disk format is approved**)
- Depends on: nothing in the Python engine; this task is isolated from it
- Deliverable: **one pull request** against `main`

## Goal
Show that a small key-value store written in Rust, without SQLite, can create,
open, write, read, delete, close and reopen a file and never return a value
that differs from an independent model. The file format is experimental,
versioned (a magic string and a format version in the header) and carries
**no compatibility promise**; it may be changed or deleted at any time.

## What to build
1. A new directory `rust/opdb-core/` with a cargo package that uses only the
   Rust standard library (no external crates). Public API: `create(path)`,
   `open(path)`, `put(key, value)`, `get(key)`, `delete(key)`, `close()`.
   Keys and values are arbitrary byte strings, including empty ones.
2. An append-only record log with a header (magic, format version) and a
   checksum per record; on open the log is replayed into an in-memory index.
   A truncated or corrupt tail is detected and reported, never silently
   accepted. No WAL, compaction or concurrency in this task.
3. Nothing in `opdb/` (the Python engine) is changed or called.

## Tests that must exist (`cargo test`, new files only)
- Binary keys and values (all 256 byte values, embedded zero bytes), empty key,
  empty value, a value of about 1 MiB.
- Overwrite of an existing key and delete of a missing key.
- Close and reopen: contents identical; reopen after many operations.
- Random operations (at least 20 seeds, 10,000 operations each, a small
  hand-written PRNG so the seeds are reproducible) compared with a plain
  `HashMap` model; the model must not share code with the store. Reopen the
  file at random points and compare every key.
- Damaged file: wrong magic, unknown format version, flipped byte inside a
  record, file cut in the middle of a record. Each must give a clear error
  or a reported truncated tail, never wrong data.

## Measurement
Publish the git SHA, the exact `cargo --version`, `rustc --version`, the
machine description and the raw `cargo test` log in the pull request text.
No speed comparison with any other database is part of this task.

## Scope limits
`rust/opdb-core/` and a short `docs/RUST_STORAGE_V0.md` stating that the
format is experimental and unstable. Not touched: `opdb/`, existing tests,
`.github/`, protected files, production. At most about 600 lines, tests included.
Follow-up tasks (not started here): WAL, crash and fault injection,
recovery, honest benchmarks with raw data.
