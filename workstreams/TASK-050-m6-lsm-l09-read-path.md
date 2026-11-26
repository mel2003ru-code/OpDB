# TASK-050 — M6 Rust LSM L09: reads across memtable and several SSTables

## Goal
Newest wins across the memtable and every SSTable, with tombstones shadowing older values. Depends on TASK-049.

## What to build
Extend `rust/opdb-core/src/lsm/db.rs` (COMPLETE file; add helper methods only): `get` searches the memtable, then the SSTables
from the newest sequence to the oldest; the first hit wins and a tombstone ends the search with `None`. Several flushes in a
row must work (each creates the next table); `Db::table_count(&self) -> usize` exposes how many tables are live.
`scan` keeps its signature and stays memtable-only (the merged scan is `scan_all`, L12); its doc comment says so.

## Tests that must exist
`rust/opdb-core/tests/task_050_read_path.rs`, about 200 lines: for 20 seeds, random batches with a flush every 40 to 80
operations; after every step `get` equals the model for all keys (including keys deleted after being flushed and keys
overwritten in a newer table); reopen at random points; `table_count` equals the number of flushes.

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
