# OpDB — Open Adaptive Database

OpDB (formerly MELDB) is an open research project aiming to create a reliable, accessible and adaptive database management system.

**Current milestone:** Verified Lens 0.1 — an experimental derived-index layer backed by SQLite as the authoritative transactional store.

> **Status: research, not production.** No independent production-grade database engine or broad speed advantage over PostgreSQL, MySQL or SQLite has been established.

## Mission

- Correctness and durability before speed.
- Source of truth independent of disposable indexes, caches and predicted views.
- Measure the full cost: builds, migrations, CPU, RAM, disk I/O, p95/p99 latency and recovery.
- Fail closed if a derived representation is stale or cannot be validated.
- Preserve failed experiments and reproducible evidence.

## Workstreams

- **TASK-001 / Safety:** Proof Gate, invariants, recovery, safe cutover (ADR-002 proposal).
- **TASK-002 / Core:** TruthStore, ChangeLog and Lens interfaces; minimal executable prototype (ADR-003 proposal).
- **TASK-003 / Quality:** independent oracles, failure injection, benchmarks and test-gated CI (ADR-004 proposal).
- Ten research streams explore broader DBMS limitations; results require written handoffs.

## Development rules

No direct changes to production servers or existing production databases. Core and Safety submit independent branches. Quality independently verifies claims. Nothing merges solely on a benchmark win.

The repository starts with coordination documents; the executable engine is not yet present. The project's architecture decisions and experiments are incorporated only after verifying their source and provenance.

Repository coordination: OpDB Headquarters.

## License

OpDB is released under the [Apache License 2.0](LICENSE).
