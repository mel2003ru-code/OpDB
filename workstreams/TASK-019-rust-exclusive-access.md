# TASK-019 — M6 experiment: prevent lost writes from concurrent Rust store handles

- Milestone: M6 native storage experiment; owner approved experimental Rust work in issues #53 and #74, and requested the reliability follow-up on 2026-11-22.
- Depends on: TASK-018 (DONE, PR #77).
- Deliverable: **one task PR** against `main`, separate from TASK-020.
- Status of the file format: **experimental and unstable**. No owner approval of a permanent on-disk format.

## Goal

The current `rust/opdb-core/` v0 can open the same file twice. Both instances
replay their own in-memory index and append without coordination; one may
overwrite another's records or return stale data. Make this failure mode
**impossible to silently accept** in the experimental prototype.

## What to build

1. Provide fail-fast, OS-backed exclusive access for every writable `Store`
   instance, acquired before replay/mutation and retained until close/drop.
   A second concurrent opener (including from another process) must receive a
   distinguishable busy/locked error, not block forever or succeed with a stale
   in-memory index. `create` must not clobber an existing file.
2. Use the Rust standard library only. If a correct cross-process lock cannot
   be provided in the available compiler/OS, report BLOCKED/negative evidence;
   **do not** substitute a process-local mutex, an unchecked lock-file scheme,
   or a sleep-and-retry loop.
3. Do not weaken existing CRC, tail checks, explicit repair, replay, or
   single-handle behavior. After `close` or `Drop`, exclusive access is
   released even on error, and a later opener replays the actual latest file.
   Do not add multi-writer concurrency or promise transactional isolation.

## Tests that must exist (new Rust tests; keep existing tests unchanged)

- Two independently opened handles for the same file, both in one process and
  in separate processes: the second fails clearly while the first is live;
  it cannot write, and the first store's data remains intact.
- A follow-up open succeeds after close/drop, sees all acknowledged records,
  and matches an independent `HashMap<Vec<u8>, Vec<u8>>` model after replay.
- A second attempt through an alias to the **same file identity** (hard link on
  platforms supporting it) cannot circumvent the lock. State OS restrictions.
- A denied/open-failed path does not leave a lock or partially change file
  bytes. Test empty and binary keys/values, overwrite and delete as in v0.
- Keep `cargo test` green, including TASK-018 corruption and truncation tests.
  An independently designed concurrency/alias check must be run at review.

## Measurement and evidence

Publish exact git SHA, Rust compiler/Cargo versions, OS, CPU/RAM, raw
`cargo test` output, and observed lock/open behavior for both processes.
No throughput or durability gain is claimed or required. A failed test is a
blocker; report it rather than weakening the test.

## Scope limits

`rust/opdb-core/` and an appended experimental-limitations section in
`docs/RUST_STORAGE_V0.md` only. No SQLite/Python engine changes, no
protected files, no production data, no stable-format decision, no new crates.
About 600 changed lines or fewer, tests included. No auto-merge.
