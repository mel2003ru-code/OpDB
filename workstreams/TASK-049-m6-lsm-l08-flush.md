# TASK-049 — M6 Rust LSM L08: flush memtable to SSTable with a manifest

## Goal
Make `Db` durable beyond the WAL: flush the memtable into an SSTable and record it in a manifest, then rotate the WAL.
Depends on TASK-046 and TASK-048.

## What to build
`rust/opdb-core/src/lsm/manifest.rs` (+ `pub mod manifest;`): `MANIFEST` file = magic `OPDBMAN\0`, version u32, entry count u32,
then per live table: file name length u32 + name, level u32, sequence u64; ends with crc32 over everything before. Functions:
`write_manifest(dir, &[ManifestEntry]) -> Result<()>` (writes `MANIFEST.tmp`, syncs, renames to `MANIFEST`, syncs the directory
by opening it and calling `sync_all` when the platform allows, ignoring that error on Windows), and `read_manifest(dir) ->
Result<Vec<ManifestEntry>>` (missing file = empty list; bad crc = `Corrupt`).
Extend `db.rs` (COMPLETE file): `Db::flush(&mut self) -> Result<()>`: sorted memtable entries (tombstones kept) to
`sst-<seq 8 digits>.sst`, then the manifest lists it, then a NEW WAL `wal-<seq+1>.log` starts, then the old WAL is deleted, in
that order. `Db::open` reads the manifest, opens listed tables and replays only the WAL segments newer than the manifest's
last flush. Reads still consult the memtable first, then the newest table: a read across more than one table is L09.

## Tests that must exist
`rust/opdb-core/tests/task_049_flush.rs`, about 200 lines: state equals the model before and after `flush`, and after close and
reopen; the files on disk after a flush are exactly `MANIFEST`, one `.sst`, one new `wal-*.log`; flush of an empty memtable is a
no-op; the manifest bit-flip test (every byte) never gives a silently different state: error or the exact state.

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
