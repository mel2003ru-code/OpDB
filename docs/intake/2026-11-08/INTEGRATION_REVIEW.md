# Intake review — Safety + Core + independent Quality (2026-11-08)

**Status:** DOCUMENTS RECEIVED / CODE NOT YET INDEPENDENTLY VERIFIED  
**Project:** OpDB Foundry, TASK-001 (#2), TASK-002 (#3), TASK-003 (#4), integration TASK-004 (#5)

## Source and provenance

The Markdown documents in this directory were copied as-is from the accessible OpDB project Library text on 2026-11-08. **No executable Safety/Core/Quality ZIP bytes were accessible** for materialization into the current runner. The full original packages remain in the Library but could not be independently executed here.

Their authors reported local test results. These reports were **not rerun on the target code by Headquarters**; no "PASS" verdict on the combined OpDB implementation is implied.

## Reported results (not re-executed here)

| Workstream | Reported lab evidence | Scope |
|---|---|---|
| Safety TASK-001 | 24 tests, 120 cutover attempts: 92 publish / 28 reject, 960 matching reads | Python 3.13.5 + SQLite 3.46.1, single isolated synthetic test |
| Core TASK-002 | 29 tests, 750-step state machine, tiny 400-row / 300-read smoke run | Disposable Python+SQLite KV Lens; no proven speedup |
| Quality TASK-003 | 6 unittest checks, independent SQLite-only model with stale-Lens negative control | Target Core/Safety integration: NOT VERIFIED |

## Contract reconciliation: blocking issues

### P0 — Trusted capture / forged journal
- Safety's ADR-002 INV-14 requires change capture that ordinary/privileged writers cannot forge, otherwise Lens must be disabled.
- The Safety reference uses an explicitly untrusted laboratory flag and **demonstrates a privileged journal-forgery counterexample**; this is a correct negative finding, not production security.
- Core's ADR-003 relies on SQLite DML triggers and version/schema checks; privileged actors altering triggers, metadata or journal are excluded.
- **Result:** capability enforcement / capture attestation is not implemented. Any unrestricted writer or untrusted journal => Source-only. Do not mark integrated Proof Gate PASS.

### P0 — Version identity / API contract mismatch
- Safety requests source generation, schema epoch, committed change sequence (with transaction grouping), plan epoch, health and log-retention lease.
- Core exposes source_id, PRAGMA schema_version and row-level revision, per-process Lens pointer, and same-snapshot read guard.
- Row-level trigger revisions are not a proof of native transaction commit-order stream or multi-shard ordering. A versioned adapter/semantics reconciliation is required.

### P1 — Cutover time and journal retention
- Safety proposes conservative wall-clock abort and a small tail budget, without claiming hard real-time deadlines.
- Core caps tail by event count only and cannot guarantee a time deadline; journal is not garbage-collected and WAL reader pins can delay checkpoints.
- Require adversarial writer-latency tests and bounded-retention rules before admission under performance SLOs.

### P1 — Proof independence and semantic scope
- Core's candidate proof compares against SQLite using a consistent snapshot; that is useful but no independent third-party check of the combined implementation has yet happened.
- Quality must execute its own oracle against the actual imported Safety+Core source (not just a separate Python model), including forged metadata, external DML, PK rename, DDL, prepared-statement churn and crash/reopen.

### P1 — Publication concurrency
- Both proposals use immutable in-process publication with version guards; neither establishes multiprocess Lens sharing or general SQL linearizability. Require a precise publication/read history model.

## Immediate handoffs
1. **Safety** supplies original ZIP, exact code SHA-256/commit SHA and reproduction command in PR linked to #2.
2. **Core** supplies original ZIP, tests, benchmark raw JSON and commit SHA in PR linked to #3.
3. **Quality** receives both executable sources and implements direct adapter tests; add fail-closed journal-forgery case to independent acceptance criteria (#4).
4. **Headquarters** approves or rejects a reconciled ADR-002/003/004 contract, never on documentation alone (#5).

## Admission decision
- ADR-002: PROPOSED — received for review.
- ADR-003: PROPOSED — received for review.
- ADR-004: PROPOSED — received for review.
- Combined Verified Lens 0.1: **NOT VERIFIED**.
- Safety-critical acceleration in unrestricted-writer mode: **BLOCKED**.
- GitHub main and production services: unchanged by this document intake.
