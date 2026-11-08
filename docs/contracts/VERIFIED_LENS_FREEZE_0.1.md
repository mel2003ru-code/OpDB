# Verified Lens 0.1 — integration checkpoint and contract freeze

- Date: 2026-11-08
- Status: PROPOSED; **not a frozen API**
- Coordinator: OpDB Headquarters
- Tracking: TASK-004 / Issue #5; TASK-001 / #2, TASK-002 / #3, TASK-003 / #4

## Roles and authority

| Role | Required document | May independently change | Must not declare |
| --- | --- | --- | --- |
| Safety | ADR-002, state machine and invariants | Safety experiment branch | Production durability based only on SQLite |
| Core | ADR-003, typed API and minimal implementation | Core feature branch | Independently durable OpDB or frozen interfaces |
| Quality | ADR-004, independent oracle and verification criteria | Quality test branch | Universal proof based on finitely many tests |
| Headquarters | Signed-off contract compatibility review | Coordination documents | Passing implementation without Quality gate |

## Shared vocabulary (provisional)

- **TruthStore:** SQLite-backed authoritative transactional records; commit boundaries define confirmed writes.
- **Snapshot:** a self-consistent observed state plus enough metadata to bind derived data to an exact source version.
- **ChangeLog:** transactionally accounted mutations sufficient to bring a derived representation forward, or evidence that catch-up is impossible.
- **Lens:** optional derived representation, disposable and never sole source of committed data.
- **Cutover:** one well-defined publication point after validating the candidate's snapshot and contiguous changes through that point.
- **Fallback:** reads bypass Lens and use authoritative TruthStore whenever required evidence is missing, corrupt or stale.

These are *draft semantic expectations*, not concrete class signatures, storage layout or an implemented protocol.

## Mandatory questions for contract owners

1. What exact SQLite transaction/isolation model and snapshot identity are used?
2. How are commit order, monotonic sequence and gaps determined with concurrent transactions?
3. How can a writer bypassing the OpDB API be detected or prevented? What is the safe failure mode?
4. Who owns the candidate's memory and lifecycle during concurrent reads/cutover?
5. How are cutover and fallback linearized relative to commits and active readers?
6. What happens on process crash at each transition and when the journal is incomplete?
7. What is the maximum allowed pause/lock budget and how is cancellation enforced?
8. How are schema changes and cached prepared statements invalidated?
9. How is transaction/log history cleaned without discarding an unconsumed change?
10. What is measured separately (build, verification, catch-up, steady-state requests, recovery)?

## First integration scenario

A fixed, independent sequence of KV insert/update/delete and aggregate operations with a reproducible seed and Oracle snapshot/state hashes. Build an optional Lens from a consistent snapshot. Apply all committed changes in order. Check candidate against TruthStore at publication. Demonstrate both accept and reject, including an external write and a deliberately missing log event. Simulate crashes before and after commit, rebuild candidate on reopening, and record limits of SQLite-backed evidence.

## Entry gate
- Safety publishes a reviewable ADR-002 proposal and relevant executable tests.
- Core publishes ADR-003 prototype API based on the *same* snapshot/journal definitions.
- Quality publishes ADR-004 with assertions that independently attempt to falsify both contracts.

## Exit gate
- Compatible and versioned semantics agreed in a Headquarters decision.
- No unresolved critical stale-read or lost-commit case accepted as PASS.
- Reproducible implementation and evidence at exact SHA on an isolated synthetic dataset.
- Independent Quality verdict PASS/FAIL/NOT VERIFIED for each claim.
- CI and code review success; manual merge decision.
- No performance-only claim used to override a safety failure.

## Present status
**NOT VERIFIED.** None of the three workstream outputs are approved by this document. The metadata CI checks only submission shape, not any of the above engine properties.
