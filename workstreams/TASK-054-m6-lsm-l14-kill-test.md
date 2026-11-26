# TASK-054 — M6 Rust LSM L14: kill test under EveryBatch

## Goal
Prove with a real killed process that every acknowledged write under `SyncPolicy::EveryBatch` survives. Depends on TASK-053.

## What to build
Only a test (no library change expected; if a tiny helper is needed, put it in `src/lsm/db.rs` and return the complete file).
The test re-executes its own binary with `std::env::current_exe()` and an environment variable as a child: the child opens a Db in
a directory given by another variable, writes numbered batches (key `k<i>` -> value derived from `i`), and after each successful
`write_batch` prints `ACK <i>` and flushes stdout; the parent reads the acknowledgements, kills the child (`Child::kill`) after a
random number of them, reopens the Db and checks that every acknowledged batch is present with the right value and that nothing
beyond the last acknowledged batch plus one is present. Repeat for 10 rounds with different kill points. The child also flushes
and compacts at some rounds.

## Tests that must exist
`rust/opdb-core/tests/task_054_kill.rs`, about 150 lines (the child path is the same test function guarded by the variable).
If the child cannot be started in the sandbox the test must fail loudly, not skip.

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
