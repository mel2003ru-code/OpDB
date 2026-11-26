# TASK-040 — M6: Rust LSM implementation tasks (L01..L15)

Status: WAITING (tasks are queued one at a time by the owner or the assistant). The task list is section 7 of
[docs/LSM_DESIGN.md](../docs/LSM_DESIGN.md).

## Where the code goes
Modules `rust/opdb-core/src/lsm/<name>.rs`, declared in `src/lib.rs`. Since the owner's decision of 2026-11-26 the sandbox
and the controller accept these paths; no second crate and no `.github/` change are needed.

## Rules (from the owner's decision of 2026-11-26)
- Do not call the Rust engine working until the benchmark with it has run and its results are published.
- Green CI is not proof of correctness: every task carries failure and recovery tests (see the design, section 6).
- The Lens stays as the correctness reference and is not changed.
