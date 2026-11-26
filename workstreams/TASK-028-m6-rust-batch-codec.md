# TASK-028 — M6 Rust: encode and decode a write batch (pure functions)

## Goal
First step towards atomic write batches in the experimental Rust store
(`rust/opdb-core`): a batch of operations can be turned into bytes and back
without any file access. This step touches no file, no `Store` method and no
existing function. The file format stays experimental.

## What to build
In `rust/opdb-core/src/lib.rs` add, and return the COMPLETE new file:
- `#[derive(Debug, Clone, PartialEq, Eq)] pub enum Op { Put(Vec<u8>, Vec<u8>), Delete(Vec<u8>) }`
- `pub fn encode_ops(ops: &[Op]) -> Vec<u8>`: the operations in order, each as
  `kind u8` (1 for put, 2 for delete; the constants `OP_PUT` and `OP_DELETE`
  already exist), `key length u32 LE`, `value length u32 LE` (0 for a delete),
  the key, the value. No count and no checksum.
- `pub fn decode_ops(bytes: &[u8]) -> Option<Vec<Op>>`: the inverse. Empty input
  is `Some(vec![])`. It returns `None` when an entry is cut short, when the kind
  is neither 1 nor 2, or when a delete carries a non-empty value. It must never
  panic, whatever lengths the bytes claim (use checked arithmetic, for example
  `checked_add` and `slice::get`; lengths are untrusted).
- Nothing else changes: do not edit `put`, `get`, `delete`, `open`, `create` or
  the file format.

## Notes checked against the crate
- `OP_PUT` is `1` and `OP_DELETE` is `2` (private constants in `lib.rs`).
- Test helpers: copy the xorshift `Rng` helper from
  `rust/opdb-core/tests/store_tests.rs`; do not import from other test files and
  never edit an existing one. Use `wrapping_mul` when mixing a seed, plain `*`
  overflows `u64` in a debug build and the test panics.
- The tests import with `use opdb_core::{decode_ops, encode_ops, Op};`.

## Tests that must exist
New file `rust/opdb-core/tests/task_028_codec.rs`, about 150 lines or fewer,
standard library only:
1. Exact layout: `Put(b"k", b"vv")` encodes to
   `[1, 1,0,0,0, 2,0,0,0, b'k', b'v', b'v']`, `Delete(b"k")` to
   `[2, 1,0,0,0, 0,0,0,0, b'k']`, and an empty list to an empty vector.
2. Empty input decodes to `Some(vec![])`.
3. Round trip: at least 30 seeds, at least 50 random batches per seed (0 to 8
   operations, keys up to 12 bytes, values up to 40 bytes, a mix of put and
   delete): `decode_ops(&encode_ops(&ops)) == Some(ops)`.
4. Binary and large: all 256 byte values as a key, an empty key, an empty value,
   a value of 1 MiB, a delete of an empty key.
5. A cut inside an entry is rejected: for one encoded put, every prefix of
   length `1..len` decodes to `None`; for a two-entry list every prefix longer
   than the first entry and shorter than the whole decodes to `None`.
6. Malformed input never panics and gives `None`: an unknown kind byte `3`, a
   delete that carries a value, lengths of `0xFF` bytes that claim far more than
   the buffer holds, and one stray byte `0xFF` after a valid entry.
- Existing tests must pass unchanged.

## Measurement
None.

## Scope
`rust/opdb-core/src/lib.rs` (complete file) and one new test file, about 600
lines or fewer together. Standard library only, no `Cargo.toml` change, no new
files outside `rust/opdb-core/`. One task PR. No protected files and no paid
models.
