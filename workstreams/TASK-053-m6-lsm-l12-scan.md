# TASK-053 — M6 Rust LSM L12: prefix scan over memtable and SSTables

## Goal
`scan(prefix)` merges all sources, newest wins, tombstones hidden. Depends on TASK-052.

## What to build
Extend `db.rs` (COMPLETE file): `scan_all(&self, prefix: &[u8]) -> Result<Vec<(Vec<u8>, Vec<u8>)>>` (a Result because SSTable reads can fail). Merge the memtable
and all tables; for each key the newest source decides; tombstoned keys are omitted; result in byte order. Also
`scan_limit(&self, prefix: &[u8], limit: usize) -> Result<Vec<(Vec<u8>, Vec<u8>)>>` returning at most `limit` entries (do not
read the rest). The old `scan` keeps its signature and is documented as memtable-only; existing tests are not touched.

## Tests that must exist
`rust/opdb-core/tests/task_053_scan.rs`, about 200 lines: for 20 seeds with random batches and flushes, `scan("")` and scans with
several prefixes (empty, a key prefix, a prefix with no keys, one that is a full key) equal the model; `scan_limit` equals the first
`limit` entries of the model scan; a deleted-then-rewritten key appears once with the newest value.
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
