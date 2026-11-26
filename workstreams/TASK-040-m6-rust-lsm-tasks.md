# TASK-040 — M6: Rust LSM implementation tasks (L01..L15)

Status: BLOCKED_OWNER. The task list is section 7 of [docs/LSM_DESIGN.md](../docs/LSM_DESIGN.md).

## Why blocked
The controller and its Rust sandbox accept only `rust/opdb-core/{src/lib.rs, tests/*.rs, examples/*.rs}` with a fixed
`Cargo.toml`, and one PR may return at most 600 lines. The LSM is a second, multi-file crate (`rust/opdb-lsm/`). Running it
through the free-model pipeline needs an extension of the sandbox runner (trusted code), of `admit_files`, and a CI line for
the new crate (a protected `.github/` change). These need the owner's explicit decision. Nothing is done about it until then.

## What may start without it
L01..L02 are pure Rust with no file access and could be written by hand in a normal pull request; the benchmark tasks
TASK-035..038 do not depend on it.

## Rules (from the owner's decision of 2026-11-26)
- Do not call the Rust engine working until the benchmark with it has run and its results are published.
- Green CI is not proof of correctness: every task carries failure and recovery tests (see the design, section 6).
- The Lens stays as the correctness reference and is not changed.
