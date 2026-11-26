# TASK-045 — M6 Rust LSM L04: WAL reader, replay and torn-tail repair

## Goal
Read a WAL back, tell a torn tail from corruption, and cut a torn tail. Depends on TASK-044 (same file layout).

## What to build
Extend `rust/opdb-core/src/lsm/wal.rs` (return the COMPLETE file) with:
- `pub struct WalReplay { pub batches: Vec<Vec<Op>>, pub valid_end: u64, pub torn_tail: Option<u64> }`.
- `pub fn read_wal(path: impl AsRef<Path>) -> Result<WalReplay>`: checks magic (`BadMagic`) and version
  (`UnsupportedVersion`); reads records in order. A record that is INCOMPLETE at the end of the file (header or body or
  crc cut short) sets `torn_tail = Some(offset of that record)` and stops. A COMPLETE record with a wrong crc, a kind other
  than 3, a key length other than 0 or a value that `decode_ops` rejects is `Err(Error::Corrupt { offset })` with the record's
  start offset. `valid_end` is the end of the last good record (12 for an empty log).
- `pub fn repair_wal(path: impl AsRef<Path>) -> Result<()>`: truncates the file to `valid_end` (only when a torn tail
  exists) and syncs it; it never touches a corrupt log (returns the `Corrupt` error).

## Tests that must exist
`rust/opdb-core/tests/task_045_wal_reader.rs`, about 200 lines: round trip of 50 random batches written with `WalWriter`;
EVERY cut of the last record at every interior offset gives `torn_tail = Some(start of last record)`, the earlier batches
intact, and after `repair_wal` the file equals the bytes before that record and accepts new appends; flipping EVERY single
byte of a small three-batch log (one flip at a time, on a copy) never yields silently different batches: the result is either
`Err(Corrupt|BadMagic|UnsupportedVersion)` or `torn_tail` is set and the returned batches are a prefix of the original ones.

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
