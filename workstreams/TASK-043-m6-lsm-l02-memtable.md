# TASK-043 — M6 Rust LSM L02: memtable

## Goal
An in-memory sorted map with tombstones, the first real LSM part. No files.

## What to build
`rust/opdb-core/src/lsm/memtable.rs`:
- `pub struct Memtable`, `Memtable::new()`, `Default`.
- `put(&mut self, key: &[u8], value: &[u8])`, `delete(&mut self, key: &[u8])` (stores a tombstone, also for an unknown key),
  `apply(&mut self, ops: &[crate::Op])` (in order).
- `get(&self, key: &[u8]) -> Option<Option<&[u8]>>`: `None` = key unknown here, `Some(None)` = tombstone,
  `Some(Some(v))` = value.
- `iter(&self) -> impl Iterator<Item = (&[u8], Option<&[u8]>)>` in byte order of keys, tombstones included.
- `len(&self) -> usize` (entries including tombstones), `approx_bytes(&self) -> usize`: sum over entries of
  `key.len() + value.len() + 16` (a tombstone counts value length 0); it must go down when a value is overwritten by
  a shorter one.

## Tests that must exist
`rust/opdb-core/tests/task_043_memtable.rs`, about 150 lines: model equality against a `BTreeMap<Vec<u8>, Option<Vec<u8>>>`
for 20 seeds of 300 random operations (keys from a small set so overwrites and deletes happen): after every step
`get` agrees for all keys and `iter` equals the model; a delete of an unknown key creates a tombstone;
`approx_bytes` follows the formula exactly in two hand-computed cases; `apply` equals the same ops one by one.

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
