# TASK-056 — M6 Rust: a key or value longer than u32 must be an error, not a silent truncation

## Goal
`rust/opdb-core/src/lib.rs` writes key and value lengths as `len() as u32`
(in `encode_ops` and in `Store::append`). A field of 4 GiB or more would be written with a wrong
length and the record would be unreadable or misread. Make that impossible: reject such a field
with an error before anything is written.

## What to build
In `rust/opdb-core/src/lib.rs`, return the COMPLETE new file:
- `pub const MAX_FIELD_LEN: usize = u32::MAX as usize;`
- `Error::TooLarge { len: usize }` (a new variant at the end of the enum).
- `pub fn check_field_len(len: usize) -> Result<()>`: `Ok` for `len <= MAX_FIELD_LEN`, else
  `Err(Error::TooLarge { len })`.
- `pub fn try_encode_ops(ops: &[Op]) -> Result<Vec<u8>>`: checks every key and value with
  `check_field_len` first, then returns exactly what `encode_ops` returns. `encode_ops` itself keeps
  its signature and behaviour; add a doc line that it truncates lengths above u32 and
  `try_encode_ops` is the checked variant.
- `Store::append` calls `check_field_len` for key and value BEFORE any change (nothing written,
  `valid_len` and the index untouched), so `put` and `delete` return `Err(Error::TooLarge { .. })`.
- Do not edit any other function.

## Notes checked against the crate
- `Error` has variants Io, Busy, BadMagic, UnsupportedVersion(u32), Corrupt { offset }, TailNotRepaired, Closed;
  existing tests match only on these names, so a new variant is safe.
- A 4 GiB buffer cannot be allocated in the sandbox (600 MiB memory limit): the check is tested through
  `check_field_len` with plain numbers, never with real huge data. On a 32-bit target `u32::MAX as usize`
  equals `usize::MAX`, so guard the over-limit cases with `#[cfg(target_pointer_width = "64")]`.
- Test helpers: copy the `tmp(name)` helper from `rust/opdb-core/tests/store_tests.rs`.

## Tests that must exist
New file `rust/opdb-core/tests/task_056_length_check.rs`, about 80 lines, standard library only:
1. `check_field_len(0)`, `check_field_len(1)` and `check_field_len(MAX_FIELD_LEN)` are `Ok`;
   on 64-bit `check_field_len(MAX_FIELD_LEN + 1)` is `Err(Error::TooLarge { len })` with that exact `len`.
2. `try_encode_ops` equals `encode_ops` on a batch with puts, deletes, empty keys and empty values.
3. A store with a few entries is unchanged after normal `put`/`delete` (file length and `len()` as before).
- Existing tests must pass unchanged.

## Measurement
None. This does not change speed.

## Scope
`rust/opdb-core/src/lib.rs` (complete file) and one new test file, about 450 lines or fewer together.
Standard library only, no `Cargo.toml` change. One task PR. No protected files and no paid models.
