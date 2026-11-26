# TASK-051 — M6 Rust LSM L10: size-tiered compaction

## Goal
Merge all tables into one when 4 or more exist, dropping tombstones. Depends on TASK-050.

## What to build
`rust/opdb-core/src/lsm/compaction.rs` (+ `pub mod compaction;`): `pub fn merge_tables(tables: &[&SsTable]) -> Result<Vec<(Vec<u8>,
Vec<u8>)>>` (input ordered oldest to newest; newest wins; tombstones are dropped because nothing older remains).
Extend `db.rs` (COMPLETE file): `Db::compact(&mut self) -> Result<()>`: writes the merged table as a new sequence number, writes the
manifest listing ONLY it, then deletes the old tables, in that order. `flush` calls `compact` automatically when `table_count() >= 4`.
An empty merge result writes no table and an empty manifest.

## Tests that must exist
`rust/opdb-core/tests/task_051_compaction.rs`, about 200 lines: for 20 seeds the state equals the model before and after each
compaction and after reopen; the file count shrinks to one table; overwritten and deleted data are gone from disk (the total size
of tables after compaction is smaller than before in an overwrite-heavy case); `merge_tables` unit case written by hand.

## Notes checked against the crate
- Everything lives in `rust/opdb-core` (one crate, `Cargo.toml` unchanged, standard library only). LSM modules are
  `rust/opdb-core/src/lsm/<name>.rs`, declared in `rust/opdb-core/src/lsm/mod.rs`. `src/lib.rs` already contains
  `pub mod lsm;` after TASK-042 and is NOT returned again by later tasks.
- From a child module the private items of the crate root are reachable: `crate::crc32(&[u8]) -> u32`, `crate::Op`
  (`Put(Vec<u8>, Vec<u8>)` / `Delete(Vec<u8>)`), `crate::encode_ops(&[Op]) -> Vec<u8>`,
  `crate::decode_ops(&[u8]) -> Option<Vec<Op>>`, `crate::Error`, `crate::Result`. Error variants: `Io(io::Error)`,
  `Busy`, `BadMagic`, `UnsupportedVersion(u32)`, `Corrupt { offset: u64 }`, `TailNotRepaired`, `Closed`.
- Return COMPLETE files for every file you change: the new module, `src/lsm/mod.rs` (a few lines) and the test file.
- Test helpers: copy the `tmp(name)` path helper from `rust/opdb-core/tests/store_tests.rs`; never import from another
  test file and never edit an existing one. Model: `BTreeMap<Vec<u8>, Option<Vec<u8>>>` or `BTreeMap<Vec<u8>, Vec<u8>>`.
  Use a small deterministic generator (an LCG with a fixed seed) instead of a crate for random data.
- Keys are byte strings compared bytewise; empty values are allowed; empty keys are rejected by nothing here.
- Existing tests must pass unchanged. Design: `docs/LSM_DESIGN.md`. The on-disk format is EXPERIMENTAL.
## Scope
Files named above only, about 450 lines or fewer together, one task PR. Standard library only, no `Cargo.toml` change,
no protected files, no paid models. Do not call the engine fast or correct beyond what the tests show.
