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

## Queue (loaded 2026-11-26)
L01..L12 are TASK-042..TASK-053, L14 is TASK-054, L15 is TASK-055, each a READY row in BACKLOG.md in dependency order (the
controller takes the first READY row, so a later task never starts before the earlier one is merged or skipped).
L13 (the R-RUST-03 research template under `research/rust/`) is done by hand: the controller cannot add templates.
