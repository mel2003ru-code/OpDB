# TASK-046 — M6 Rust LSM L05: Db over memtable and WAL

## Goal
The first working database: batches go to the WAL then the memtable; reopening replays the WAL. No SSTables yet.
Depends on TASK-043 and TASK-045.

## What to build
`rust/opdb-core/src/lsm/db.rs`:
- `pub struct Db`; `Db::open(dir: impl AsRef<Path>, policy: SyncPolicy) -> Result<Db>`: creates the directory when it does not
  exist; the WAL is the single file `wal-00000001.log` in it; an existing WAL is replayed into the memtable. A torn tail is
  NOT cut automatically: `torn_tail()` reports it and writes return `Error::TailNotRepaired` until `repair()`.
- `write_batch(&mut self, ops: &[Op]) -> Result<()>`: WAL append first, then memtable apply. A failed WAL append leaves the
  memtable unchanged.
- `get(&self, key: &[u8]) -> Option<Vec<u8>>` (a tombstone gives `None`), `put`/`delete` as one-op batches,
  `scan(&self, prefix: &[u8]) -> Vec<(Vec<u8>, Vec<u8>)>` (live entries, byte order), `repair(&mut self) -> Result<()>`,
  `torn_tail(&self) -> Option<u64>`, `close(&mut self) -> Result<()>`.

## Tests that must exist
`rust/opdb-core/tests/task_046_db_wal.rs`, about 200 lines: for 20 seeds, random batches (puts, deletes, overwrites), after each
batch compare `get` of all keys and `scan("")` with a `BTreeMap` model; close and reopen at random points and compare again;
a torn tail made by cutting the WAL at several offsets: `open` succeeds, `torn_tail()` is `Some`, `write_batch` gives
`TailNotRepaired`, after `repair` the data equals the model up to the last whole batch and writes work; a directory that is a
file gives `Error::Io`.

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
