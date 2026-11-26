# TASK-055 — M6 Rust LSM L15: bulk-insert example for the benchmark

## Goal
An example binary the benchmark runs: it reads generated rows from a file, writes them into the LSM (and, for comparison,
into the v0 store), and prints verifiable numbers. It makes no speed claim by itself. Depends on TASK-053.

## What to build
`rust/opdb-core/examples/lsm_bulk.rs`: arguments `rows_file dir batch sync` where `rows_file` is lines of `hexkey hexvalue`,
`batch` a count, `sync` one of `every_batch|on_close|never`. It inserts all rows with `Db::write_batch` in batches (one batch =
`batch` rows), times the insert with `std::time::Instant`, closes the Db, REOPENS it, verifies every row with `get`, and prints
one line of JSON: `{"engine":"opdb-lsm","rows":N,"batch":B,"sync":"...","insert_ms":X,"verified":true}`. A verification failure
prints `"verified":false` and exits with status 1. Also `rust/opdb-core/tests/task_055_bulk_example.rs` (about 80 lines): runs the
library path the example uses on 2,000 generated rows and checks the same verification, without spawning a process.

## Notes checked against the crate
- Everything lives in `rust/opdb-core` (one crate, `Cargo.toml` unchanged, standard library only). LSM modules are
  `rust/opdb-core/src/lsm/<name>.rs`, declared in `rust/opdb-core/src/lsm/mod.rs`. `src/lib.rs` already contains
  `pub mod lsm;` after TASK-042 and is NOT returned again by later tasks.
- From a child module the private items of the crate root are reachable: `crate::crc32(&[u8]) -> u32`, `crate::Op`
  (`Put(Vec<u8>, Vec<u8>)` / `Delete(Vec<u8>)`), `crate::encode_ops(&[Op]) -> Vec<u8>`,
  `crate::decode_ops(&[u8]) -> Option<Vec<Op>>`, `crate::Error`, `crate::Result`. Error variants: `Io(io::Error)`,
  `Busy`, `BadMagic`, `UnsupportedVersion(u32)`, `Corrupt { offset: u64 }`, `TailNotRepaired`, `Closed`.
- `src/lsm/mod.rs` already declares every module (memtable, wal, sstable, manifest, compaction, db) and the `SyncPolicy` enum: DO NOT return or edit `mod.rs` or `lib.rs`; an existing empty stub file for your module already exists: return its COMPLETE new content. Return COMPLETE files for the module file(s) and the test file only.
- Test helpers: copy the `tmp(name)` path helper from `rust/opdb-core/tests/store_tests.rs`; never import from another
  test file and never edit an existing one. Model: `BTreeMap<Vec<u8>, Option<Vec<u8>>>` or `BTreeMap<Vec<u8>, Vec<u8>>`.
  Use a small deterministic generator (an LCG with a fixed seed) instead of a crate for random data.
- Keys are byte strings compared bytewise; empty values are allowed; empty keys are rejected by nothing here.
- Existing tests must pass unchanged. Design: `docs/LSM_DESIGN.md`. The on-disk format is EXPERIMENTAL.
## Scope
Files named above only, about 450 lines or fewer together, one task PR. Standard library only, no `Cargo.toml` change,
no protected files, no paid models. Do not call the engine fast or correct beyond what the tests show.
