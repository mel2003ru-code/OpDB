# TASK-048 — M6 Rust LSM L07: SSTable reader and corruption detection

## Goal
Open and read the file TASK-047 writes; detect damage instead of returning a wrong answer. Depends on TASK-047.

## What to build
Extend `rust/opdb-core/src/lsm/sstable.rs` (COMPLETE file):
- `pub struct SsTable`; `SsTable::open(path) -> Result<SsTable>`: reads the footer (`BadMagic`, `UnsupportedVersion`, crc mismatch
  is `Corrupt { offset }` with the footer offset) and the index block (crc checked); keeps the index in memory.
- `get(&self, key: &[u8]) -> Result<Option<Option<Vec<u8>>>>`: binary search in the index, reads ONE block, verifies its crc,
  scans it; `None` = absent, `Some(None)` = tombstone, `Some(Some(v))`.
- `iter_all(&self) -> Result<Vec<(Vec<u8>, Option<Vec<u8>>)>>` all entries in order (reads and verifies every block).
- `len(&self) -> u64` entry count from the footer.

## Tests that must exist
`rust/opdb-core/tests/task_048_sstable_reader.rs`, about 200 lines: write 500 random sorted entries, `get` agrees with the model for
present, absent and tombstoned keys (also keys below the first and above the last); `iter_all` equals the input; EVERY single-byte
flip of a small file (one at a time, on a copy, 3 blocks) makes `open` or every full read return an error, or a read of an
UNAFFECTED key returns the right value, but it NEVER returns a wrong value for any key; a truncated file at every offset is an error.

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
