# OpDB Foundry — bounded research probe catalog

**Status:** experimental, synthetic and SQLite-based only. The stand-alone Core/Safety implementation remains unintegrated and is **NOT VERIFIED**.

Each probe uses a fixed seed, an independent check where possible and a narrowly scoped label. A passing probe **does not** mean its named OpDB workstream is implemented or safe.

| Workstream | Probe | What it actually tests | What it does NOT prove |
|---|---|---|---|
| R01 redundant computation | SQLite SUM + Python oracle, conservative cache invalidation | cached results match authoritative rows across writes | faster OpDB aggregates or production cache policy |
| R02 physical I/O | SQLite file, page_count, WAL file size | logical storage accounting and row equality | physical SSD read/write amplification |
| R03 adaptive indexing | live CREATE/DROP INDEX, answer oracle | SQLite correctness during schema changes | actual OpDB adaptive index |
| R04 cache/memory | Python toy LRU/FIFO, capacity and misses | bounded simulated residency | official cache policies, RSS or I/O |
| R05 adaptive cost control | synthetic cost/benefit decision | decline costly, uncertain or oversized opportunities | actual learned policy or measured ROI |
| R06 concurrency | two SQLite WAL connections | pinned snapshot returns consistent data | native OpDB serializability or linearizability |
| R07 crash recovery | SQLite WAL + os._exit before/after commit | SQLite process-crash reopen | power-fail, fsync correctness, native OpDB WAL |
| R08 tail latency | SQLite selective queries + DDL, p50/p95/p99/max | basic timing including index create/drop | production p99 guarantees or SSD latency |
| R09 operational safety | fail-closed toy admission gate | unknown evidence blocks action | enforceable capture privileges |
| R10 SQL correctness | SQLite SUM metamorphic split + Python oracle | SQL arithmetic consistency | full SQL coverage or SQLancer itself |
| TASK-001 Safety | NOT_CONFIGURED | no imported independent executable | Proof Gate correctness |
| TASK-002 Core | NOT_CONFIGURED | no imported independent executable | integrated engine |
| TASK-003 Quality | NOT_CONFIGURED | no imported target adapter | independent safety certification |

## P0 negative control

Runs separately on each cycle: intentionally cache a SQLite-derived value, commit a change from a different SQL connection, and confirm the unguarded cache becomes stale while SQLite's integrity check passes.

**Expected result: EXPECTED_COUNTEREXAMPLE.** This is a deliberately insecure model, not a passing Safety gate or a discovered SQLite bug. A failure to reproduce the expected counterexample is reported as a test failure.

## Schedules and admission
- A lightweight run occurs twice per hour on main at :07/:37 UTC, subject to GitHub scheduling delays.
- A separate weekly cross-runtime matrix and manual dispatch exercise multiple pinned seeds on Linux and Windows / Python 3.11–3.13.
- **No model API requests, no paid inference, no external project access, no production data, no auto-merge or deployment.**
- Raw run JSON is stored as GitHub Actions artifact for a bounded retention period. To reproduce: `python -m research.cycle --seed 20261108 --output result.json`.
- New production-facing adapters must enter via explicit ADR-002/003/004 review, independent Quality assessment and a safety-gated PR, not by changing this probe registry alone.

## Capacity and costs

Private-repository GitHub Actions consume runner minutes; 48 scheduled lightweight runs/day plus one weekly matrix is intentionally bounded with workflow timeouts and short artifact retention. This is not equivalent to 48 autonomous AI research studies. Reduce cadence if GitHub minute consumption is excessive. A failed workflow may update one per-day alert comment on Issue #17.
