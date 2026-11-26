# OpDB roadmap

Set by the project owner. Agents plan tasks from the first unfinished
milestone and do not reorder or rewrite this file.

**Aim.** An open embedded database whose derived structures ("Lenses")
answer common questions far faster than recomputation and are checked
against the authoritative data, so a fast answer is never a wrong one.

| # | Milestone | Done when | Status |
| --- | --- | --- | --- |
| M1 | Lens 0.1: one engine-maintained aggregate | Lens equals Source in all tests; read speed-up measured | Done (TASK-006) |
| M2 | Cheaper writes with a Lens | 1,000-row batch overhead cut by at least a third; small defects from M1 fixed | In progress (batch-overhead target not yet confirmed by numbers; TASK-034 open) |
| M3 | Lens survives restart | Lens state stored in the same transaction as data; opening a 1M-row database does not rescan it; a damaged or stale stored Lens is detected and rebuilt | Done except one known gap: a write made to the file by another program while OpDB is closed is not detected (owner decision pending) |
| M4 | More than one Lens | Aggregates over numeric values (sum, min, max) and caller-defined grouping, each with an oracle test | |
| M5 | Honest comparison harness | The same aggregate workload run against plain SQLite (index, triggers) and OpDB on one machine, scripts and raw numbers in the repository | Done (TASK-015); a wider harness against SQLite and the Rust engine is TASK-035..039 (`docs/benchmarks/README.md`) |
| M6 | Native storage experiments (Rust) | Language approved by the owner (issue #74, 2026-11-19); experimental storage v0 in `rust/opdb-core` (TASK-018..021). Owner decision of 2026-11-26: stage 1 is an LSM engine in Rust aimed at bulk inserts (`docs/LSM_DESIGN.md`, TASK-040); stage 2 is a paged B-tree aimed at reads, started only after stage 1 is benchmarked against SQLite (TASK-041). The Lens stays the working correctness reference. The Rust engine is not called working until its benchmark is published | In progress |
| M7 | Query surface (SQL or a subset) | **Owner decision** on approach first | Owner decision |
