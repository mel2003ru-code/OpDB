# TASK-033 — M6 Rust: write a compacted copy of a store

## Goal
Add compaction to the experimental Rust store (`rust/opdb-core`) in its simplest
safe form: write a NEW file that holds only the live entries, leaving the
original untouched. An append-only log grows with every overwrite and delete;
this copy is the smaller log. No file format change.

## What to build
In `rust/opdb-core/src/lib.rs`, return the COMPLETE new file, add to `Store`:

`pub fn compact_to(&self, path: impl AsRef<Path>) -> Result<()>`

- Create a new store at `path` with `Store::create` (it fails if the path
  already exists; return that error as it is, never overwrite a file).
- Write every live entry of this store once, in key order (byte order), with
  `put`, then `close` the new store and return `Ok(())`.
- This store is not changed in any way: no write to its file, no change to its
  index, it stays usable afterwards.
- Do not edit any existing function. You may add a private helper; a public
  `entries()` may or may not exist, do not rely on it.

## Notes checked against the crate
- `Store` keeps its live data in a `HashMap<Vec<u8>, Vec<u8>>` field `index`;
  collect and sort the pairs by key before writing.
- `Store::create(path)` returns `Err(Error::Io(_))` when the path exists. An
  empty store compacts to a file that is only the 12-byte header.
- Test helpers: copy the `tmp(name)` path helper from
  `rust/opdb-core/tests/store_tests.rs`; do not import from other test files and
  never edit an existing one. The model is a `BTreeMap<Vec<u8>, Vec<u8>>`.
- `Store::truncated_tail()` is `None` for a clean file; `Store::len()` and
  `Store::get(key)` read the live data.

## Tests that must exist
New file `rust/opdb-core/tests/task_033_compact.rs`, about 150 lines or fewer,
standard library only:
1. Many overwrites and some deletes (for example 20 keys written 50 times each,
   then 10 of them deleted), then `compact_to`. The new file is strictly smaller
   than the original, reopens with `truncated_tail() == None`, and holds exactly
   the live data: `len()` equals the model and `get` of every model key returns
   the model value, and a deleted key is absent.
2. The original store is unchanged: its file length is the same as before the
   call, it still returns the same data, and it accepts a new `put` afterwards.
3. `compact_to` to a path that already exists returns `Err(Error::Io(_))` and
   leaves that file's content untouched.
4. An empty store (or one whose keys were all deleted) compacts to a file of
   exactly 12 bytes that opens as an empty store.
- Existing tests must pass unchanged.

## Measurement
None.

## Scope
`rust/opdb-core/src/lib.rs` (complete file) and one new test file, about 600
lines or fewer together. Standard library only, no `Cargo.toml` change, no new
files outside `rust/opdb-core/`. One task PR. No protected files and no paid
models.
