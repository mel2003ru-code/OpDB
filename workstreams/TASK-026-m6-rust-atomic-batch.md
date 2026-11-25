# TASK-026 — M6 Rust: atomic write batches in the experimental store

## Goal
Add an atomic multi-operation write to the experimental Rust store
(`rust/opdb-core`): a batch of puts and deletes is either fully visible after a
crash or not visible at all. The file format stays experimental (no
compatibility promise, `FORMAT_VERSION` unchanged).

## What to build
- In `rust/opdb-core/src/lib.rs` add
  `pub enum Op { Put(Vec<u8>, Vec<u8>), Delete(Vec<u8>) }` and
  `pub fn apply(&mut self, ops: &[Op]) -> Result<()>` on `Store`. Return the
  COMPLETE new `lib.rs`. Change nothing else in how existing functions behave.
- On disk a batch is ONE record of a new kind `OP_BATCH = 3`: kind byte, key
  length `0` (u32 LE), value length (u32 LE), the value, CRC-32 (u32 LE) over
  everything before it. This is exactly the existing record layout with an
  empty key, so the existing length framing and checksum protect the batch as a
  unit and an incomplete batch is found by the existing truncated-tail logic.
  The value holds the operations in order; each is `kind u8` (1 put, 2 delete),
  `key length u32 LE`, `value length u32 LE`, key, value (empty for delete).
- Replay in `open`: a complete batch record applies its operations in order. A
  batch whose checksum is valid but whose value does not decode exactly
  (an entry cut short, trailing bytes, an unknown kind) is
  `Error::Corrupt { offset }` with the offset of the batch record.
- `apply(&[])` returns `Ok(())` and writes nothing. `apply` on a store with an
  unrepaired tail returns `Err(Error::TailNotRepaired)` and on a closed store
  `Err(Error::Closed)`, like `put`.
- The in-memory index is changed only after the record is written; inside one
  batch later operations win (put then delete leaves the key absent, delete
  then put leaves it present).

## Notes checked against the crate
- Existing API: `Store::create/open/put/get/delete/len/close/repair`,
  `truncated_tail() -> Option<u64>`, `Error::{Io, Busy, BadMagic,
  UnsupportedVersion, Corrupt { offset }, TailNotRepaired, Closed}`.
- The file header is 12 bytes; a record starts right after the previous one.
  `truncated_tail()` returns the offset where an incomplete last record starts.
- Test helpers: copy the `tmp(name)` path helper and the `Rng` xorshift helper
  from `rust/opdb-core/tests/store_tests.rs`, and the idea of a hand-built
  record with CRC-32 (reflected, polynomial `0xEDB88320`, start and final XOR
  `0xFFFFFFFF`) from `tests/task_020_recovery.rs`. Do not import from other test
  files and never edit an existing one.

## Tests that must exist
New file `rust/opdb-core/tests/task_026_batch.rs`, about 250 lines or fewer,
standard library only:
1. Model test: at least 20 seeds, at least 200 random batches per seed (1 to 8
   operations, keys from a small pool so keys repeat inside a batch), mixed
   with single `put` and `delete`. Compare with a `HashMap` model after every
   batch (`len` and `get` for every pool key), then close, reopen and compare.
2. Torn batch: a store with some single records, note the file length `L0`,
   apply one batch of at least 4 operations (new length `L1`). For every cut
   length `c` from `L0 + 1` to `L1 - 1` copy the file truncated to `c`: open
   succeeds, `truncated_tail() == Some(L0)` and the contents equal the model
   from before the batch (no part of the batch is visible); after `repair()` a
   new `put` works and survives a reopen. At `c == L1` the whole batch is
   visible and `truncated_tail()` is `None`.
3. Damage: flip one byte inside the value of a complete batch record, so the
   open fails with `Error::Corrupt { offset: L0 }`; build by hand a batch
   record with a valid CRC-32 and a value cut mid-entry, expect
   `Error::Corrupt`.
4. `apply(&[])` leaves the file length unchanged.
5. `apply` after `close` is `Err(Error::Closed)`; with an unrepaired tail it is
   `Err(Error::TailNotRepaired)`.
- Existing tests must pass unchanged. If a check shows a defect in existing
  behaviour, keep the failing test and describe it in the pull request text.

## Measurement
None.

## Scope
`rust/opdb-core/src/lib.rs` and one new test file, about 600 lines or fewer
together. Standard library only, no `Cargo.toml` change, no new files outside
`rust/opdb-core/`. One task PR. No protected files and no paid models.
