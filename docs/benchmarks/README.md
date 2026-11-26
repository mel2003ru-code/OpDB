# Benchmarks: protocol

One reproducible set for SQLite, the OpDB Source / numeric Lens and, later, the Rust LSM: the same generated data, the same
machine, the same durability. Code: `experiments/bench/` (tasks TASK-035..038). Results are published in this directory only
by a run that has really finished; a number that was not measured is `NOT_IMPLEMENTED` or `NOT_APPLICABLE`, never a guess.

## Fairness rules
1. Same rows for every contender: `make_rows(n, seed, value_bytes)`, the data digest is stored with the result.
2. Same durability: SQLite runs `journal_mode=WAL`, `synchronous=FULL`; the Rust LSM runs `SyncPolicy::EveryBatch`
   (see `docs/LSM_DESIGN.md`). A row that uses a weaker setting is labelled and reported separately.
3. Same call granularity: bulk inserts in batches of 1,000 rows, point reads one call per key. Python call overhead differs
   from native Rust; every result states which side is Python and the table is not read as a language comparison.
4. At least 15 runs per cell, a fresh file for every run; the table shows the median and min/max of the runs.
5. Every contender is verified against an independent model before the numbers count.
6. Each result file carries: commit SHA, seed, the exact command, machine, Python, SQLite and rustc versions.

## Where it runs (owner decision 2026-11-26: VPS1)
VPS1 is a SHARED production server (bots, shop, one CPU, about 1 GB RAM). Numbers from it are indicative and are published
with that caveat. Run only throttled and outside busy periods, for example
`systemd-run --scope -p CPUQuota=25% nice -n 19 python3 experiments/bench/run.py ...`, never several runs in parallel,
never with sizes that need more than about 300 MB of free memory. Record `uptime` and the free memory next to the result.

## Workloads
`bulk_insert`, `point_read` (TASK-035), `range_scan`, `filter` (TASK-037), `txn_commit`, `txn_rollback`, `txn_crash`
(TASK-038). A workload a contender cannot do is reported as `NOT_IMPLEMENTED`.
