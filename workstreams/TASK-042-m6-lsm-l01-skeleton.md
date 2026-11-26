# TASK-042 — M6 Rust LSM L01: module skeleton and sync policy

## Goal
Create the empty frame all later LSM tasks fill: the module `lsm`, a `SyncPolicy` enum and one small
helper that every later file needs.

## What to build
- `rust/opdb-core/src/lib.rs`: return the COMPLETE file with exactly one added line, `pub mod lsm;`, placed after the
  `use` lines. Change nothing else.
- `rust/opdb-core/src/lsm/mod.rs`: a doc comment (EXPERIMENTAL, design in docs/LSM_DESIGN.md), and
  `#[derive(Debug, Clone, Copy, PartialEq, Eq)] pub enum SyncPolicy { EveryBatch, OnClose, Never }` plus
  `pub fn sync_policy_name(p: SyncPolicy) -> &'static str` returning `"every_batch"`, `"on_close"`, `"never"`.

## Tests that must exist
New file `rust/opdb-core/tests/task_042_lsm_skeleton.rs`, about 40 lines: the three names are exact and distinct;
`SyncPolicy` is `Copy` and comparable; `opdb_core::lsm::SyncPolicy::EveryBatch` is reachable from outside the crate.

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
- The crate library name is `opdb_core` (package `opdb-core`).

## Scope
Files named above only, about 450 lines or fewer together, one task PR. Standard library only, no `Cargo.toml` change,
no protected files, no paid models. Do not call the engine fast or correct beyond what the tests show.
