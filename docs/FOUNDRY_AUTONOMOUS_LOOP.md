# OpDB Foundry: closed-loop automation, phase A (PROPOSED)

Date: 2026-11-08. Tracking: TASK-005 Issue #31; dependencies #2-#5 and P0 #21; ADR-001 and proposed ADR-005.

## Target cycle

Hypothesis -> isolated AI research/PR -> independent correctness and fault injection -> performance experiments with full cost -> staged deployment rehearsal -> owner-approved promotion policy -> canary, health checks and rollback -> next hypothesis.

Autonomous agent work must be bounded by runtime, financial budget, unique task identity and PR count. Error or missing evidence is an explicit denial, never automatic optimization. The fast 30-minute GitHub cycle tests only SQLite/Python references and must NOT be mistaken for an autonomous model runtime.

## What is actually implemented in phase A

- Pure read-only evaluation in foundry/control.py. It accepts an optional JSON evidence file; the default without evidence reports NOT_CONFIGURED.
- Fail-closed claims check: exact candidate SHA; independent Quality report metadata tied to that commit; explicit snapshot/commit/external writer/journal/DDL/crash invariant matrix; full benchmark comparison matrix.
- 22 unittest methods covering positive *synthetic report preflight* and negative cases including missing proofs, forged journal FAIL, wrong SHA, NaN, duplicate trials, incomplete peers and resource/tail regressions.
- GitHub pull-request CI with read-only token, no secrets or production write permissions.
- The gate always outputs production_allowed=false and automatic_merge_allowed=false. No installed staging/deploy workflow, no autonomous ChatGPT scheduler control and NO attestation of the report's claims.

## Decision states

- NOT_CONFIGURED: target engine/proof is absent. No promotion.
- NOT_VERIFIED: submitted report metadata is incomplete, inconsistent or cannot meet schema conditions. No promotion.
- BLOCKED: known critical failure or invalid evidence schema. No promotion.
- CONTINUE_RESEARCH: declared safety report is complete but benchmarks are missing, incomplete or show regressions. No promotion.
- PAUSE_FOR_REVIEW: strict self-reported comparator matrix passes a conservative preflight. This is only an advisory stop signal for *future optimization proposals* once authenticated scheduler integration exists. It is NOT a proof that OpDB is globally superior, production-ready, or correct.

## Conservative threshold for a candidate pause

Required peers: PostgreSQL, MySQL, SQLite.
Required synthetic workload labels: read_heavy, write_heavy, mixed_oltp, contention.
At least seven paired distinct trial seeds for all twelve combinations; source and baseline versions, same hardware identity, dataset SHA-256, raw evidence SHA-256, at least two claimed independent replications, a pinned protocol, and zero errors.
For every combination, median throughput ratio must reach 1.20 or greater and each paired throughput ratio must be at least 1.10. Median p99 latency, CPU time, peak memory and I/O consumption must be no worse. A single missing metric or regression prevents PAUSE_FOR_REVIEW.

All of these values are untrusted JSON metadata in the current prototype. The code does not verify who measured them, SHA-256 preimages, signed logs, the actual compiled candidate, benchmark independence, configuration equivalence or full operational costs. A real victory finding needs a pre-registered workload corpus, competitor versions pinned at test time, correct data/query results, build/maintenance/recovery and durability evidence, repeatable raw traces on multiple machines, statistics with confidence bounds, independent Quality verification and owner's review. Four selected workloads do not justify global superiority.

## Reproduce safely

    python -m unittest -v tests.test_foundry_control
    python -m unittest discover -s tests -p 'test_*.py' -v
    python -m foundry.control
    python -m foundry.control --evidence some-local-evidence.json --output decision.json

Last two commands only inspect a report and print/write a decision; they never deploy or merge. The synthetic all-green fixture exists exclusively inside unit tests, not as real evidence.

## Subsequent implementation gates

B. Import the exact executable Safety/Core/Quality original sources in independent PRs and prove Source-only behavior under Issue #21 adversarial cases on the actual combined adapter.
C. Extend research harness with pinned baseline benchmark executables, independent result checks, cold/warm runs, build and recovery cost, p50/p95/p99/max, CPU/RAM/I/O and reliable raw provenance. Baselines change over time and require recertification.
D. Set up isolated staging with reproducible packaged artifact, migration safety, automatic rollback rehearsal and explicit deployment authorization. Until this passes, no real production pipeline.
E. Integrate authenticated PAUSE_FOR_REVIEW into the autonomous orchestration loop so NEW change proposals halt for owner+Quality scientific review while monitoring and safety checks continue. No raw JSON flag may directly pause, approve releases or assert proof. The stop decision must remain auditable and reversible by owner decision.

The current OpDB is a research effort; there is no claimed native production DBMS. No users, VPS services, external databases, access control, paid inference APIs or production systems are modified by this phase.
