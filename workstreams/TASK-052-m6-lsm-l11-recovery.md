# TASK-052 — M6 Rust LSM L11: recovery of orphans and half-finished flush or compaction

## Goal
`Db::open` cleans up after a crash at every step of flush and compaction. Depends on TASK-051.

## What to build
Extend `rust/opdb-core/src/lsm/db.rs` (COMPLETE file): `open` deletes `*.tmp` files and SSTables that the manifest does not list,
and removes WAL segments older than the manifest's flush point; `Db::recovered_orphans(&self) -> Vec<String>` lists names removed
by the last `open`. Add a test hook, `#[doc(hidden)] pub fn set_crash_point(&mut self, p: Option<CrashPoint>)` with
`pub enum CrashPoint { AfterSstWritten, AfterManifestWritten, AfterOldFilesDeleted }`: when set, the next `flush` or `compact`
returns `Err(Error::Closed)` right after that step WITHOUT doing the later steps (simulating a kill).

## Tests that must exist
`rust/opdb-core/tests/task_052_recovery.rs`, about 200 lines: for flush and for compaction and for each crash point, drop the Db
without `close`, reopen: the state equals either the state before the operation or the state after it (the test knows which one
each crash point must give: `AfterSstWritten` gives the pre-operation state and the SSTable is reported as an orphan;
`AfterManifestWritten` gives the post-operation state and the old files are reported/removed), never a mix, and writes work afterwards.

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
