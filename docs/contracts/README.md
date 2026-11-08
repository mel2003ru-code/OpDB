# Shared contract registry

Normative interface contracts are reviewed across three teams:
- Safety / TASK-001: state machine, source-version invariants, publication and fallback.
- Core / TASK-002: API proposals, data types, transactions, resource and failure surface.
- Quality / TASK-003: independent assertions, oracles and integration gates.

Until ADR-002 and ADR-003 have been jointly reviewed, no interface is frozen. Proposed names TruthStore, ChangeLog, Lens, Snapshot, VersionManager, Cutover and Fallback are architectural placeholders, not declarations of implemented production functionality.

Contract revisions must be versioned, documented and reviewed before merge.
