# ADR-004 — OpDB Verification Standard

**Status:** PROPOSED — awaiting review in OpDB Headquarters; *not* adopted by Safety/Core.  
**Date:** 2026-11-08. **Owner:** OpDB Quality (independent verification). **Scope:** Verified Lens 0.1, Proof Gate, future core.

## 1. Decision

OpDB shall not publish a derived index/Lens as safe, or advertise acceleration, without replayable correctness evidence. The primary Source is authoritative; derived artifacts may be abandoned. Fallback to Source after invalid proof must be part of a verified operation contract, not a best-effort exception path.

This proposal must be reconciled with the **actual** ADR-001 (full text not obtained). It does not claim to supersede ADR-001. Current SQLite/Python test successes **do not** certify OpDB Core or Safety.

### Status semantics

- **PASS:** named implementation, exact commit and configuration, exact operations, tested in specified environment and within declared threat model, all applicable assertions passed; no extrapolation.
- **FAIL:** an observed counterexample or violated invariant for the **named tested target**. Reproducer and retained trace required.
- **NOT VERIFIED:** no target, no oracle, incomplete coverage, missing environment, unrun CI or insufficient evidence. This cannot be silently converted to PASS.
- A **negative control** must fail on the deliberately unsafe design; the lab harness passes only when it detects that failure. Reporting must preserve both statuses.

## 2. Non-negotiable invariants

**C1—Correctness:** exact SQL semantics for NULL, comparisons, aggregates, collation, overflow, and transaction-visible snapshot; compare multisets when ordering is unspecified. No silent wrong answer.  
**C2—Durability:** after confirmed COMMIT, Source is recoverable within the documented fsync, crash and storage guarantees; uncommitted operations absent. Uncertain acknowledgement documented and handled separately.  
**C3—Atomicity/Isolation:** no partial transaction visible; execution history respects advertised isolation model; serializability/linearizability only claimed if specifically checked.  
**C4—Derived structures:** any committed Source change not represented by a trustworthy Lens must prevent publishing or serving that Lens; external writers, DDL, schema epochs, prepared statement invalidation, failover and asynchronous replay must be tested.  
**C5—Proof Gate:** cutover to candidate requires coherent snapshot, catch-up boundaries, verification of candidate content, atomic publication and verifiable fallback; an epoch alone is insufficient.  
**C6—Rollback:** failed build/validation/cutover cannot change confirmed Source data or expose partial candidate.  
**C7—Resources:** untrusted optimizer work has explicit CPU, RAM, I/O and lock-budget limits; any mechanism with nonpositive demonstrated net benefit remains optional/off by default.  
**C8—Evidence:** test seeds, generated traces, exact build hashes, versions, host limits, oracles, results and failures are retained.

## 3. Verification pyramid

1. **Deterministic unit and mutation-sensitivity:** independent math model, boundary values, bad history rejection, deliberately corrupt Lens, stale Lens detection.
2. **Differential:** same action trace, same initial data and semantics, Python/reference model vs SQLite query paths; independent PostgreSQL and MySQL where portable, recording dialect exceptions.
3. **SQL metamorphic:** TLP TRUE/FALSE/NULL partition, NoREC counts, pivot checks, index/no-index, reorder-independent bag equivalence; run official SQLancer in a dedicated suite once target adapter exists. This lab currently runs a deliberately limited subset, **not SQLancer itself**.
4. **Property-based/state-machine:** seeded interleaving of insert/update/delete/reads, DDL, external commits, rollbacks, replay, duplicate/out-of-order events, and shrinkable counterexamples. Full Hypothesis-style shrinking is future work.
5. **Concurrency/history:** history with invocation/response intervals; model checker for linearizability or serializability matching documented isolation level. Reject histories that violate real-time precedence when linearizability is claimed. Start with bounded exhaustive checks; scale to Elle/Jepsen-style checkers later.
6. **Fault matrix:** before/after WAL append, fsync, acknowledgement, snapshot, candidate validation, catch-up and publication; kill process, truncate/corrupt WAL in a *copy*, suspend threads, fail I/O; physical power failures require dedicated hardware.
7. **Performance:** record per-operation p50/p95/p99/max and per-run end-to-end latency **including** DDL/build, journal maintenance, replay, validation, catch-up, clean-up and fallback. Record process CPU, peak RSS, cache hit, file bytes, OS I/O, physical device I/O where available, and background/foreground contention.

## 4. Required evidence for **any** speedup claim

A release claim is invalid unless all are present: exact OpDB and comparator versions/build flags/commit hashes; CPU model, cores, frequency/governor, RAM and limits, storage model/FS/mount/fsync settings; dataset sizes and SHA-256; identical generated actions/SQL semantics, isolation/durability modes and connection counts; index build/write maintenance/updates/cutover/recovery/cleanup charges; predeclared baseline algorithm and policy; repeated paired trials with randomized order; p50/p95/p99/max, total time, throughput, CPU/RAM/physical I/O; variability/confidence intervals; independent correctness oracle for every read and final database state; raw per-run traces; known limits. State clearly synthetic, production replay, or official benchmark; never conflate them. Aggregate p99 only from the **operation-level distribution** of the designated scope, not as the median of per-run p99 unless labeled as such.

SQLite/Python speed results may only be described as **SQLite/Python model results**. Raw and checked output paths cannot silently differ in semantics. An unmeasured dimension (e.g. device I/O, actual OpDB) must be shown **NOT VERIFIED**.

## 5. Acceptance and rejection gates

| Gate | Minimal acceptability for change | FAIL / NOT VERIFIED treatment |
|---|---|---|
| G0 source identity | Signed/tagged commit or SHA-256 source, versions, replay script and seed | NOT VERIFIED; no release claim |
| G1 data/results | Zero discrepancies on all defined deterministic, differential and metamorphic suites, including NULL/overflow/snapshot boundaries | Any mismatch: FAIL, block merge/release |
| G2 transaction history | Exact history attached, checker output matches documented isolation | Invalid history: FAIL; untested model: NOT VERIFIED |
| G3 durability | Process crash before/after COMMIT and reopen/integrity test PASS; storage-level tests required for stronger claims | No storage test => no power-loss guarantee |
| G4 derived Lens | External writer and DDL invalidation; candidate tamper and stale epoch blocked | Wrong answer or unsafe publication: FAIL |
| G5 concurrency | Multi-process writers/readers, lock contention and long catch-up logs with no confirmed data loss | Failing counterexample: FAIL |
| G6 performance | Minimum 5 independent paired runs per seed/profile for exploratory; predeclared number of seeds, 30+ pairs and controlled hardware for public performance claims | Missing cost/dispersion => NOT VERIFIED, no acceleration announcement |
| G7 regression | All prior counterexamples permanently covered; no test suppression or silent skip | Failure blocks change; flakiness tracked as defect |
| G8 CI | Mandatory independent SQLite tests + PG/MySQL suites executed, artifacts retained; OpDB integration gate must explicitly require target | Unrun workflow or absent adapter => NOT VERIFIED |

**No universal performance pass target is asserted.** Headquarters should define service-level latency/throughput budgets per workload before change evaluation. Proposed provisional review trigger: regression >10% of matched workload p99 **or** max latency vs selected baseline requires explicit documented disposition; this is **not** an SLO nor permission to suppress data.

## 6. CI architecture and independence

`verification.yml` runs Python 3.11–3.13 independent harness regression and SQLite suites; a separate mandatory PostgreSQL 17/MySQL 8.4 service job checks the portable SQL subset with a Python oracle. Driver/install/database errors **fail** the job; there is no `continue-on-error`. Artifacts are retained on pass/fail. All DB services are disposable and localhost-only. This is a **proposed, unexecuted GitHub workflow**, not evidence of successful CI.

The **OpDB engine release gate** shall require a target adapter with `reset/create_schema, execute_query, begin/commit/rollback, snapshot, recover, build_lens, publish_candidate, fallback, inspect_metrics`. It must fail closed when target is absent. Owns no writes to production systems; dedicated ephemeral volumes only. Quality controls seeds, oracle logic, metrics, baselines, and verdict; Core/Safety cannot edit baselines without recorded review.

CI levels: pull request (deterministic quick), nightly (randomized long-running and fault/concurrency), weekly (performance on pinned hardware), release candidate (complete certification and disaster recovery). Shared GitHub-hosted runners are for correctness, **not** authoritative speedup measurements.

## 7. Document known failures

- **Q-001 BLOCKER / unsafe design:** cached, untracked derived view returns 5 while Source after committed external UPDATE is 25; `integrity_check=ok`; expected negative-control failure, reproduced in this independent lab. Actual OpDB status remains NOT VERIFIED.
- **R12 warning:** prior report describes parameterized prepared expression returning 0 vs 8502 following partial-index DDL in one Python/SQLite stand. This lab has **not** reproduced/attributed it; must preserve `hot/seed203` counterexample and test with/without statement cache across builds.
- **R13 warning:** bypassing managed Store API causes stale Lens in earlier experiment; exact mechanism must be verified on actual OpDB code.
- **R15 warning:** matching epoch does not establish Lens integrity; source-based content verification is mandatory.
- **Resource risk:** a 6000-event journal and guarded full-aggregation cutover passed in this model, but long write-lock duration, log truncation, overflow and multi-process replay not proven safe.

## 8. Decision consequences

Correctness has veto over optimization. A performance improvement with a single confirmed wrong answer is a **FAIL**, not a weighted score. Negative, unstable and inconclusive experiments remain in the record. Promotion requires new evidence in the actual implementation plus an independent reviewer; the author of Safety/Core must not be the sole approver of Quality evidence.

### Reference methodology

- SQLancer methodology (TLP, NoREC, PQS, DQP): https://github.com/sqlancer/sqlancer
- SQLite isolation and WAL guarantees/limitations: https://www.sqlite.org/isolation.html , https://www.sqlite.org/wal.html
- GitHub Actions Python build/test documentation: https://docs.github.com/en/actions/tutorials/build-and-test-code/python