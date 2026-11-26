# Task queue

Agents take the first `READY` row. Statuses: `READY`, `IN_PROGRESS`,
`DONE`, `BLOCKED_OWNER`. See [AGENTS.md](../AGENTS.md).

| Task | Milestone | Status | Pull request |
| --- | --- | --- | --- |
| [TASK-006 Lens 0.1](TASK-006-lens-0.1.md) | M1 | DONE | #41 |
| [TASK-007 Cheaper batch writes with a Lens](TASK-007-lens-batch-overhead.md) | M2 | DONE | #45 |
| [TASK-009 Cost of overwriting existing keys](TASK-009-lens-overwrite-cost.md) | M2 | DONE | #52 |
| [TASK-010 M2 batch write overhead verification](TASK-010-m2-batch-regression.md) | M2 | DONE | #56 |
| [TASK-011 Remaining Lens batch-write costs](TASK-011-lens-batch-hotspots.md) | M2 | DONE | #58 |
| [TASK-012 M3 atomic persistent Lens prototype](TASK-012-m3-persistent-lens.md) | M3 | DONE | #60 |
| [TASK-013 Reduce persisted Lens write cost](TASK-013-persistent-write-cost.md) | M3 | DONE | #62 |
| [TASK-014 Numeric Lens: sum, min, max](TASK-014-lens-sum-min-max.md) | M4 | DONE | #64 |
| [TASK-015 M5 comparison with plain SQLite](TASK-015-m5-sqlite-comparison.md) | M5 | DONE | #67 |
| [TASK-016 Reduce numeric Lens write cost](TASK-016-numeric-write-cost.md) | M2 | DONE | #70 |
| [TASK-017 Reduce numeric Lens rebuild time](TASK-017-numeric-rebuild-cost.md) | M3 | DONE | #73 |
| [TASK-018 Rust storage v0 (experimental)](TASK-018-rust-storage-v0.md) | M6 | DONE | #77 |
| [TASK-019 Rust exclusive store access](TASK-019-rust-exclusive-access.md) | M6 | DONE | #80 |
| [TASK-020 Rust crash/torn-write recovery](TASK-020-rust-crash-recovery.md) | M6 | DONE | #83 |
| [TASK-021 Measured cost of Rust v0](TASK-021-rust-v0-measurements.md) | M6 | DONE | #87 |
| [TASK-022 Numeric Lens value-index deletion](TASK-022-m2-value-index-delete.md) | M2 | BLOCKED_OWNER | closed #94 |
| [TASK-023 M4 min/max after deleting the current extreme](TASK-023-m4-minmax-after-extreme-delete.md) | M4 | BLOCKED_OWNER | abandoned, see PROGRESS.md |
| [TASK-026 M6 Rust: atomic write batches](TASK-026-m6-rust-atomic-batch.md) | M6 | BLOCKED_OWNER | abandoned, see PROGRESS.md |
| [TASK-024 M4 sum at signed 64-bit limits and on overflow](TASK-024-m4-sum-int64-limits.md) | M4 | DONE | #116 |
| [TASK-025 M2 failed mixed batch leaves Source and Lens unchanged](TASK-025-m2-mixed-batch-rollback.md) | M2 | DONE | #107 |
| [TASK-027 M3 damaged stored Lens metadata is detected at open and rebuilt](TASK-027-m3-stored-lens-damage.md) | M3 | READY | — |
| [TASK-028 M6 Rust: encode and decode a write batch](TASK-028-m6-rust-batch-codec.md) | M6 | DONE | #121 |
| [TASK-029 M4 caller-defined grouping, groups appearing and disappearing](TASK-029-m4-custom-grouping.md) | M4 | DONE | #122 |
| [TASK-031 M6 Rust: list all live entries in key order](TASK-031-m6-rust-entries.md) | M6 | DONE | #123 |
| [TASK-030 M2 order of operations inside one batch](TASK-030-m2-batch-semantics.md) | M2 | DONE | #125 |
| [TASK-033 M6 Rust: write a compacted copy of a store](TASK-033-m6-rust-compact-to.md) | M6 | IN_PROGRESS | — |
| [TASK-032 M3 rebuild and reopen keep the answers](TASK-032-m3-rebuild-reopen.md) | M3 | READY | — |
| [TASK-034 M2 an invalid batch is rejected and changes nothing](TASK-034-m2-input-validation.md) | M2 | READY | — |
| [TASK-035 M5 benchmark core: data, timing, SQLite contender](TASK-035-m5-bench-core.md) | M5 | READY | — |
| [TASK-036 M5 benchmark: OpDB Source and numeric Lens contenders](TASK-036-m5-bench-opdb-contenders.md) | M5 | WAITING (needs TASK-035) | — |
| [TASK-037 M5 benchmark: range scan and filter workloads](TASK-037-m5-bench-range-filter.md) | M5 | WAITING (needs TASK-036) | — |
| [TASK-038 M5 benchmark: transactions, rollback, crash recovery](TASK-038-m5-bench-transactions.md) | M5 | WAITING (needs TASK-037) | — |
| [TASK-039 M5 publish the first benchmark table (manual run on VPS1)](TASK-039-m5-publish-first-benchmark.md) | M5 | WAITING (manual; needs TASK-038) | — |
| [TASK-040 M6 Rust LSM implementation tasks L01..L15 (see docs/LSM_DESIGN.md)](TASK-040-m6-rust-lsm-tasks.md) | M6 | BLOCKED_OWNER | multi-file crate needs sandbox and CI support |
| [TASK-041 M6 stage 2: paged B-tree design](TASK-041-m6-btree-design.md) | M6 | WAITING (needs the first LSM benchmark) | — |
