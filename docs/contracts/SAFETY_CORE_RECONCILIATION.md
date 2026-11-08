# Safety ↔ Core interface reconciliation — review proposal v0.1

**Status:** PROPOSED / non-normative.  
**References:** [ADR-001](../adr/ADR-001.md), [TASK-004](https://github.com/mel2003ru-code/OpDB/issues/5), [P0 trusted capture](https://github.com/mel2003ru-code/OpDB/issues/21), [intake PR #20](https://github.com/mel2003ru-code/OpDB/pull/20).  
**Authority:** Headquarters coordination. These are questions for independent teams, not a declaration of implemented or formally proved guarantees.

| Topic | Safety ADR-002 requires | Core ADR-003 implements in isolated Python/SQLite lab | Proposed integration decision |
|---|---|---|---|
| Source identity | Immutable source generation + schema epoch | SQLite `source_id` UUID + PRAGMA schema_version | Specify generation invalidation on restore/DDL; require same-snapshot capture |
| Commit watermark | Committed change stream, transaction boundaries and intra-transaction order | Trigger-generated row-event `revision` | Keep row-event revision as **SQLite-only**; require explicit mapping to commit group, never pretend it is a native commit LSN |
| Trusted capture | Storage-owned, unforgeable write capture or no Lens admission | SQLite triggers capture ordinary DML; privileged journal and catalog edits unsupported | **P0:** no unrestricted external-writer acceleration; explicit Source-only on unknown trust |
| Snapshot | One source transaction for version stamp and data | WAL consistent SQLite read transaction | Define common handle and read-snapshot identity |
| Cutover | Candidate proof + contiguous replay, short fence, fail closed | Full comparison, `BEGIN IMMEDIATE`, replay max-events, process-local pointer | Specify event cap and measured writer-lock duration separately; do not claim hard real-time deadline |
| Read admission | Version/schema/plan epoch/health/certification checks against same snapshot | Source ID, schema, revision, per-read snapshot guard | Include plan epoch and trust verification before new accelerated query |
| External writes | Engine capture or Source-only | Normal SQL DML captured via SQLite triggers | Quality tests ordinary DML, privilege changes, trigger drop, forged log, PK rename |
| Journal retention | No gaps from producer through consumed cursor, leases before GC | No GC; potential unbounded log | Document explicit no-GC 0.1 research limit; prevent production use |
| Publication | Atomic immutable version pointer; old-reader safety | In-process immutable pointer | Single-process scope only; multi-process sharing unverified |
| Recovery | Candidate disposable, source survives crash under stated storage assumptions | SQLite WAL, restart with Source only | Test process exits; do not claim physical power-failure durability |
| Query semantics | Exact defined predicate/type/collation | Minimal UTF-8 keys and bytes, ordered bounded `get/scan` | Keep KV-only semantics; do not generalize to SQL |
| Evidence | Independent oracle and reproducible fault matrix | Reported Core unit tests, not rerun by Quality | Import source before claiming any combined PASS |

## Next artifact from each team
- **Safety:** sign off on expected `capture_attestation`, `SnapshotHandle`, `CommittedDelta`, cutover/plan fencing semantics. Provide runnable test proving denial when capture is forgeable.
- **Core:** submit executable exact source in a branch, propose typed adapter for snapshot/change stream/reads; record mode `TRUSTED | UNKNOWN | UNTRUSTED` as *evidence*, not arbitrary caller assertion.
- **Quality:** independently test Core + Safety adapter with a fresh SQLite oracle, seeded concurrency histories and privileged forged-event negative control. Distinguish observation from assumption.
- **Headquarters:** record remaining conflicts and approve a **versioned** contract only after review; P0 remains open until measurable trust boundary exists.

**Current verdict:** combined Verified Lens 0.1 = NOT VERIFIED; production deployment and unrestricted-writer Lens = BLOCKED.
