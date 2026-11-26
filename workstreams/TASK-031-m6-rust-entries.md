# TASK-031 — M6 Rust: list all live entries in key order

## Goal
Add a read-only way to list everything the experimental Rust store
(`rust/opdb-core`) holds, in a stable order. This is a small step needed by later
work (compaction, aggregates). It changes no file format and no existing
function.

## What to build
In `rust/opdb-core/src/lib.rs`, return the COMPLETE new file, add to `Store`:

`pub fn entries(&self) -> Vec<(Vec<u8>, Vec<u8>)>`

It returns every live key with its value, sorted by key in byte order (plain
`Vec<u8>` ordering). A deleted key is absent, an overwritten key shows its
latest value, an empty store gives an empty vector. It does not touch the file
and does not change the store. Do not edit any existing function.

## Notes checked against the crate
- `Store` keeps its live data in a `HashMap<Vec<u8>, Vec<u8>>` field `index`.
- Test helpers: copy the `tmp(name)` path helper and the xorshift `Rng` helper
  from `rust/opdb-core/tests/store_tests.rs`; use `wrapping_mul` when mixing a
  seed (a plain `*` overflows `u64` in a debug build and the test panics). Do
  not import from other test files and never edit an existing one.
- The model is a `BTreeMap<Vec<u8>, Vec<u8>>`; collecting it into a vector of
  pairs gives exactly the expected order.

## Tests that must exist
New file `rust/opdb-core/tests/task_031_entries.rs`, about 120 lines or fewer,
standard library only:
1. At least 20 seeds, 300 random operations each (put with short random keys of
   0 to 3 bytes so that keys repeat, and delete). After EVERY operation
   `store.entries()` equals the model vector. A new store gives an empty
   vector.
2. After the last operation close the store, reopen the file, and `entries()`
   still equals the model vector.
3. The result is sorted: for adjacent pairs the keys are strictly increasing.
- Existing tests must pass unchanged.

## Measurement
None.

## Scope
`rust/opdb-core/src/lib.rs` (complete file) and one new test file, about 600
lines or fewer together. Standard library only, no `Cargo.toml` change, no new
files outside `rust/opdb-core/`. One task PR. No protected files and no paid
models.
