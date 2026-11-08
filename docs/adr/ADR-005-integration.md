# ADR-005: Foundry workstreams and integration gate

- Date: 2026-11-08
- Status: PROPOSED (needs Headquarters approval)

## Problem
Safety, Core and Quality work independently. Previous research R12-R14 highlighted stale derived structures, schema/prepared-statement interaction, costly cutovers and incomplete durability evidence. Chat transcripts alone are insufficient for coordinating interface contracts.

## Proposed approach
- SQLite remains TruthStore's authoritative transactional store for Verified Lens 0.1.
- Derived Lens objects are optional, replaceable accelerators.
- Safety owns normative rules for snapshot identity, monotonic and gap-free ChangeLog sequences, cutover point and fallback semantics.
- Core owns draft typed interfaces and executable prototypes; claims require independent Quality assessment.
- Quality decisions are PASS, FAIL or NOT VERIFIED for explicitly stated test conditions.
- FAIL and NOT VERIFIED for critical safety guarantees block merge, not merely reduce confidence.
- All evaluated artifacts must be traceable to exact commit, seed, configuration, environment and checksum.
- No automatic writes to production systems, external databases or deployment.

## Required evaluation matrix
1. Consistent snapshot and version capture.
2. Concurrent writes during build, catch-up and cutover.
3. External writer avoiding API must not lead to trusted stale Lens answers.
4. Crash before/after commit and publication; replay.
5. ChangeLog gaps, duplicates, reordering and corruption.
6. Long backlog and long-running snapshots; bounded cutover lock time.
7. Prepared queries before/after DDL and connection reuse.
8. Differential reference results and final-state hashes.
9. Total construction, maintenance, verification, latency p50/p95/p99/max, CPU, RAM and I/O.
10. Explicitly record unresolved proof, portability and power-failure limitations.

## Merge checklist
One task owner and isolated branch; current shared contracts cited; independent correctness oracle; regression tests; reproducible evidence; Quality review; failure recovery plan; Headquarters approval for contracts and high-risk changes.

## Open questions
Formal isolation model; external write interception; journal garbage collection; overflow; snapshot lifetime; memory budget; platform fsync reliability and lock time budget.
