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
| [TASK-023 M4 min/max after deleting the current extreme](TASK-023-m4-minmax-after-extreme-delete.md) | M4 | BLOCKED_OWNER | closed #99 |
| [TASK-024 M4 sum at signed 64-bit limits and on overflow](TASK-024-m4-sum-int64-limits.md) | M4 | BLOCKED_OWNER | closed #102 |
| [TASK-025 M2 failed mixed batch leaves Source and Lens unchanged](TASK-025-m2-mixed-batch-rollback.md) | M2 | DONE | #107 |
