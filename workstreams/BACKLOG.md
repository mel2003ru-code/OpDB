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
