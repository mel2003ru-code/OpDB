# OpDB roadmap

Set by the project owner. Agents plan tasks from the first unfinished
milestone and do not reorder or rewrite this file.

**Aim.** An open embedded database whose derived structures ("Lenses")
answer common questions far faster than recomputation and are checked
against the authoritative data, so a fast answer is never a wrong one.

| # | Milestone | Done when | Status |
| --- | --- | --- | --- |
| M1 | Lens 0.1: one engine-maintained aggregate | Lens equals Source in all tests; read speed-up measured | Done (TASK-006) |
| M2 | Cheaper writes with a Lens | 1,000-row batch overhead cut by at least a third; small defects from M1 fixed | In progress |
| M3 | Lens survives restart | Lens state stored in the same transaction as data; opening a 1M-row database does not rescan it; a damaged or stale stored Lens is detected and rebuilt | Next |
| M4 | More than one Lens | Aggregates over numeric values (sum, min, max) and caller-defined grouping, each with an oracle test | |
| M5 | Honest comparison harness | The same aggregate workload run against plain SQLite (index, triggers) and OpDB on one machine, scripts and raw numbers in the repository | |
| M6 | Native storage experiments | **Owner decision** on language and on-disk format first | Owner decision |
| M7 | Query surface (SQL or a subset) | **Owner decision** on approach first | Owner decision |
