# TASK-021 — M6 experiment: measured cost of Rust v0 (open time, writes, reads, file size)

- Milestone: M6 native storage experiment; approved experimental Rust direction in issues #53/#74.
- Depends on: TASK-018, TASK-019, TASK-020 (all DONE).
- Deliverable: **one separate task PR** against `main`.
- Format status: experimental and **not approved for durable user data**. Do not change the on-disk format.

## Goal

Measure, with raw numbers and no claims beyond what was run, what the append-only
Rust v0 store costs today. The log is replayed in full on `open`, and every key
is held in memory; this task finds out how large those costs are, so the owner
can decide on a WAL/compaction/format direction from data.

## What to build

1. A benchmark binary or `cargo test --release -- --ignored` target under
   `rust/opdb-core/` (e.g. `examples/bench_v0.rs`), standard library only,
   deterministic with a fixed seed.
2. **Required** workloads at 10,000 and 100,000 keys (values 16 B and 256 B).
   A 1,000,000-key workload is **optional future capacity testing**, not an
   acceptance criterion for TASK-021; do not label a skipped run as measured:
   - bulk `put` of N new keys (total time, per-op median/p95/p99 from sampled timings);
   - `get` of N random existing keys and of N missing keys;
   - overwrite of every key once, then `delete` of half the keys;
   - **cold `open` time** of the resulting file and file size on disk, before
     and after the overwrite/delete phase (the growth shows the cost of no compaction);
   - peak resident memory of the process after open (read from `/proc/self/status`).
3. An optional comparison column from a **separate plain-SQLite script**
   (`scripts/bench_sqlite_kv.py`, `sqlite3` from the Python standard library, same keys,
   same sizes, same machine, one table, `INSERT OR REPLACE`/`SELECT`, default
   journal mode, stated pragmas). Both sides report what they were configured to do,
   including whether each call syncs to disk. If sync behaviour differs, say so beside the numbers.
4. Raw output committed as `docs/bench/rust-v0-<date>.txt` (and the SQLite one beside it).
   A short factual section in `docs/RUST_STORAGE_V0.md`: table of results, machine, SHA, commands.

## Reproducibility and resource limits

- Each run uses its own temporary directory, created fresh and removed afterwards; no production
  or repository files are touched. Before a run the harness checks free disk space and refuses to start
  if the estimated need (append-only log after put + overwrite + delete, times 1.5) does not fit; it prints
  the estimate. Million-key runs are opt-in future work, not part of the default
  benchmark or required for this PR. If separately attempted, insufficient RAM,
  cgroup headroom or disk must cause an explicit SKIP before allocation/writes,
  not a false PASS or unsafe attempt. Peak RSS is recorded for each measured size.
- Rust and Python use one specified operation sequence: the same seed, the same key generator and the same
  order (put N, get all, get missing, overwrite all, delete every second key). The Python oracle
  generates the sequence independently of the Rust code; expected final contents are compared after
  put, after overwrite, after delete, and again after close and reopen.

## Tests that must exist

- Before timing anything, the benchmark verifies every value read back against an independent
  Python/`HashMap` model of the same seeded operations; a mismatch aborts the run and the numbers are not published.
- A small (N = 1,000) variant of the same workload runs as an ordinary `cargo test`, so correctness of the harness itself is in CI.
- All TASK-018/019/020 tests keep passing.

## Measurement and evidence

Publish SHA, `rustc`/`cargo`/Python/SQLite versions, OS/CPU/RAM, exact commands, raw logs,
and at least 3 repeated runs per **required** size (10k and 100k, at 16 B and
256 B; report each run plus the median). Million-key results may be collected
later with a suitable runner and independently verified limits, but absence or
resource SKIPs do not block TASK-021; explicitly state that 1M performance is
unmeasured. A negative result
(Rust v0 slower, memory-hungry, or file growth large) is a valid outcome and is stated as it is.
No statement about any other database is made unless it was measured by a script in the repository.

## Owner-approved measurement scope (2026-11-24)

The owner explicitly made million-key performance runs **optional** to avoid
blocking safe development on the small VPS. This changes measurement coverage
only: all existing and new Rust/Python correctness tests, independent models,
regression checks, CI, independent review and publication of reproducible raw
10k/100k results remain mandatory. Do not claim 1M scalability, durability or
correctness from smaller benchmarks. Million-key stress and container-aware
memory preflight are deferred to a separate, resource-appropriate follow-up.

## Scope limits

Only `rust/opdb-core/` (new files, no behaviour changes to `src/lib.rs`), `scripts/bench_sqlite_kv.py`,
`docs/bench/`, and an additive section of `docs/RUST_STORAGE_V0.md`. Standard library only, no changes to
`opdb/`, existing tests, `.github/`, protected files or production. About 600 changed lines or fewer.

## Not in this task (owner decision needed first)

A write-ahead log, compaction, fsync policy changes or any change to the record layout alter
the on-disk format. They are proposed only after these numbers exist and need the owner's decision.
