# TASK-008 — Persist Lens 0.1 across reopen (M3 opt-in research)

- Milestone: M3 (research proposal, schema not approved)
- Depends on: TASK-007 (DONE as PR #45)
- Owner review: on-disk schema is an irreversible compatibility choice. **Do not merge this draft PR without explicit owner approval.**
- Context: Issue #49, P0 #21, LAB-001 #47/#48.

## Goal

Introduce an explicit opt-in experimental mode
`TruthStore(path, lens=True, persist_lens=True)`. Current defaults and
`TruthStore(path, lens=True)` remain ephemeral and unchanged. Do not
write persistent Lens tables when the new flag is false.

In the opt-in mode, a valid cache should reopen from small aggregate
tables without a full `opdb_source_kv` scan. Detect missing, stale,
or damaged persisted metadata and rebuild safely; a bad Source row
must disable Lens rather than return an untrusted fast answer.

## Proposed research-only disk schema

- `opdb_lens_groups_v1(grp TEXT PRIMARY KEY, row_count INTEGER, value_bytes INTEGER)`
- `opdb_lens_state_v1(singleton, format_version=1, source_seq, checksum)`
- Checksum authenticates **nothing**; it only detects accidental damage to
  derived rows. The accepted threat model allows only the trusted
  `TruthStore` process to mutate the Source.
- On every trusted `apply`, save Source + incremented `commit_seq`
  + derived aggregate in one SQLite `BEGIN IMMEDIATE` transaction.
  If any derived write fails, the entire Source write must rollback.
  Publish new in-memory Lens strictly after successful COMMIT.
- Reopen verifies version, Source sequence, counts, byte sums, checksum
  and typed data *within the derived tables*. It must NOT claim
  authenticated Source integrity without scanning or a protected writer.
- On missing/damaged/stale derived state, rebuild from authoritative
  Source inside a write transaction, then persist the new derived state.
- If an outside writer changes Source during an active connection,
  `data_version` invalidates Lens and forces a Source-based rebuild.
  **Outside writes while the database is closed are not authenticated
  and remain outside the supported trust model. P0 #21 stays open.**

## Acceptance tests

- Fixed seeds with overwrites, repeated keys, deletions and reinsertions:
  Lens vs Source vs independent Python dict, including reopen.
- Reopen with valid checkpoint: no `SELECT ... FROM opdb_source_kv`
  through Lens; no 1M Source full scan, measured separately.
- Damaged `source_seq`, checksum, metric type: rebuild from Source.
- A malformed Source row must not be masked on first opt-in build.
- Forced derived-state SQL failure before COMMIT: complete rollback.
- Simulated crash after Source+Lens COMMIT before memory publication:
  reopen observes committed state; crash before COMMIT keeps old state.
- Outside writer while connected: fallback to Source and rebuild.
- Existing test suite unchanged. New tests only.
- Benchmarks with 10k, 100k and 1M rows comparing ephemeral Lens
  cold-open, persisted Lens initial build, persisted reopen, and write
  overhead. Report machine, Python/SQLite, fixed seeds and exact SHA.

## Scope and restrictions

Change `opdb/`, new `tests/`, `experiments/`, this task document
and the status cell in `workstreams/BACKLOG.md`. No triggers, no
new dependencies, no changes to existing tests, protected files, or
production usage. No automatic migration or release. Stay **DRAFT** and
seek an independent Quality review and owner disk-format decision
before merging.
