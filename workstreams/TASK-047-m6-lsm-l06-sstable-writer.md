# TASK-047 — M6 Rust LSM L06: SSTable writer

## Goal
Write an immutable sorted file with an index and a footer. Pure function of its input; no reader yet in this task except
a minimal test-side parser.

## What to build
`rust/opdb-core/src/lsm/sstable.rs` (+ `pub mod sstable;`). Layout (LE): data blocks, each holding entries until it reaches
about 4096 bytes; entry = flag u8 (1 value, 0 tombstone), key length u32, value length u32, key, value; after the data blocks
an index block: count u32 then per block (first key length u32, first key, block offset u64, block length u32); then a footer
of exactly 36 bytes: magic 8 bytes `OPDBSST\0`, version u32 (0), index offset u64, index length u32, entry count u64, then a crc32 u32
over those 32 bytes. Every data block and the index block end with their own crc32 u32 over their bytes (the block length includes it).
- `pub fn write_sstable(path: impl AsRef<Path>, entries: &[(Vec<u8>, Option<Vec<u8>>)]) -> Result<u64>`: entries must be strictly
  ascending by key (else `Error::Io` with `InvalidInput`); writes to `<path>.tmp`, syncs, renames to `path`, returns the file length.
  An existing target is replaced only through the rename; an empty input gives a valid file with an empty index.

## Tests that must exist
`rust/opdb-core/tests/task_047_sstable_writer.rs`, about 200 lines: a test-side parser written independently in the test
(parse footer, index, blocks, check every crc) recovers exactly the input for 300 sorted random entries including tombstones
and empty values; the footer is exactly 36 bytes; no `.tmp` file remains; unsorted or duplicate keys are rejected and leave
no file; an entry larger than a block still works (a block may exceed 4096 for a single entry).

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
