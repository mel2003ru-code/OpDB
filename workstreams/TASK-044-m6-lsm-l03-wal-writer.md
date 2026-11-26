# TASK-044 — M6 Rust LSM L03: WAL writer

## Goal
Append one write batch as one checksummed record to a WAL file, with a sync policy.

## What to build
`rust/opdb-core/src/lsm/wal.rs`. File layout (all integers little-endian):
header = 8 bytes magic `OPDBWAL\0` + u32 version 0 (12 bytes). Record = kind u8 (=3), key length u32 (=0),
value length u32 (=N), value = `encode_ops(ops)`, crc32 u32 over everything before it in the record.
- `pub const WAL_MAGIC: &[u8; 8]`, `pub const WAL_HEADER_LEN: u64 = 12`.
- `pub struct WalWriter`; `WalWriter::create(path: impl AsRef<Path>, policy: SyncPolicy) -> Result<WalWriter>` creates a new
  file with `create_new` (fails with `Error::Io` when it exists) and writes the header.
- `append_batch(&mut self, ops: &[Op]) -> Result<()>`: writes ONE record; with `EveryBatch` calls `sync_data` before
  returning; `OnClose` and `Never` do not. An empty batch is written as a record too.
- `close(&mut self) -> Result<()>`: syncs under `EveryBatch` and `OnClose`, then drops the file; later appends return
  `Error::Closed`.
- `bytes_written(&self) -> u64` (file length including header).

## Tests that must exist
`rust/opdb-core/tests/task_044_wal_writer.rs`, about 150 lines: the exact bytes of a file with two known batches (build
the expected bytes by hand in the test with its own crc32 copy, never by calling the code under test); the CRC covers
kind, lengths and value; `create` on an existing path fails and leaves the file untouched; append after `close` gives
`Error::Closed`; `bytes_written` equals the real file length after every append; all three policies write identical bytes.

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
