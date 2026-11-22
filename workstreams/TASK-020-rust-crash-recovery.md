# TASK-020 — M6 experiment: crash/torn-write recovery evidence for Rust v0

- Milestone: M6 native storage experiment; approved experimental Rust direction in issues #53/#74.
- Depends on: TASK-019 (exclusive file access) and TASK-018 (DONE, PR #77).
- Deliverable: **one separate task PR** against `main`.
- Format status: experimental and **not approved for durable user data**. Do not choose a permanent on-disk format.

## Goal

Establish the actual recovery boundary of the append-only Rust v0 log under
interrupted writes. A truncated tail is currently reported by
`truncated_tail()` and requires explicit `repair()`; a complete corrupt
record returns `Error::Corrupt`. Confirm these guarantees with reproducible
fault injection, and fix demonstrable wrong-answer or unsafe-recovery bugs
without promising power-loss durability not actually implemented.

## What to build

1. Add deterministic, bounded test-only fault scenarios at every byte offset
   of short records, selected offsets of larger/binary records, and after
   sequences of put/overwrite/delete. Replay the resulting files from a
   *separate* `Store::open`. Keep the fault injector independent of the
   production record parser where practical.
2. For a partial final record, make sure no incomplete operation is applied;
   expose `truncated_tail()`, refuse mutations until explicit `repair()`,
   and preserve every verifiably complete preceding record. Never repair
   silently during `open` or discard healthy earlier records.
3. For wrong magic/version and complete CRC/opcode corruption, return a clear
   error and never present unverified values. Be explicit about outcomes when
   damaged length fields look like a partial tail: do not claim corruption
   detection where it cannot be proven.
4. Add one bounded Linux subprocess interruption scenario using an expendable
   temporary store. Compare outcomes to an independent record/model oracle.
   Do **not** equate process kill with sudden power loss or storage-device
   failure; document all untested durability boundaries.
5. Fix only bugs demonstrated by tests, and do not weaken checks, remove
   tests, change the approved language, or introduce a permanent file format.
   If an additional WAL/format decision would be required, stop and raise an
   owner decision rather than silently changing compatibility semantics.

## Tests that must exist (new Rust test files)

- Exhaustive every-byte truncation of representative short put and delete
  records, including empty/binary keys and values; no wrong reconstructed
  values, no hidden repair, no unexpected panic.
- Corrupt CRC, invalid operation, wrong magic/version, impossible lengths,
  damaged header, and extra trailing bytes: each must fail clearly or produce
  an explicitly reported incomplete-tail state with mutations denied.
- After explicit repair of a partial tail, reopen and compare each key against
  the last **verified complete record prefix** using an independent
  `HashMap` oracle. Run seeded mixed operations and multiple reopen cycles.
- Crash a writer subprocess at several bounded points; verify the returned
  state is **only a valid prefix**, never a silently fabricated or corrupted
  value. Record any ambiguous nondurable-write outcomes honestly.
- Keep all TASK-018 and TASK-019 tests passing, including the cross-process
  exclusive-lock tests.

## Measurement and evidence

Publish SHA, compiler/Cargo versions, OS/CPU/RAM, exact test commands, raw
`cargo test` and crash-harness logs, tested fault offsets, and a table of
observed outcomes. No benchmark or power-cut guarantee is required. Label
unverified fsync/directory-sync semantics as **not established**; a successful
`put` currently does not itself prove persistence across power failure.

## Scope limits

Only `rust/opdb-core/` and an additive experimental-limitations/recovery
section of `docs/RUST_STORAGE_V0.md`. Standard library only, no changes to
`opdb/`, existing tests, .github, protected files or production; no
permanent on-disk format approval. About 600 changed lines or fewer. Do not
merge until independent review, actual Rust tests and applicable CI are green.
