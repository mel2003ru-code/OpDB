# Interface request to OpDB Core — TASK-001 SAFETY

**Status: PROPOSED; no acceptance by Core yet.** ADR-001 unavailable at time of writing. Owner of final implementation: Core. Owner of admission invariants: Safety.

## Required capabilities from Core

| API / guarantee | Semantics | Safety reason |
|---|---|---|
| `begin_snapshot() -> SnapshotHandle` | pins source `generation`, `schema_epoch`, `visible_commit_seq`, retention lease and isolation identifier; all reads under handle see one consistent version | INV-02/04/06 |
| `scan_source(handle, query_spec)` | deterministic result for that same snapshot; typed queries + explicit semantics | INV-04/07 |
| `subscribe_commits(from_seq, lease) -> DeltaStream` | atomically committed deltas with precise commit order, old/new images, rollback excluded, replay cursor, duplicate/gap reporting | INV-02/03 |
| `capture_attestation(handle) -> TrustEvidence` | engine-owned attestation that no writer can modify Source without journal record, or explicit `UNVERIFIED` | INV-14 |
| `begin_short_fence(deadline) -> CutoverFence` | bounded acquisition or explicit timeout; exposes final `(generation,schema,seq)` | INV-08/10 |
| `publish_lens_if_valid(cert, pointer, expected_epoch)` | compare-and-swap publication of immutable Lens with generation plan epoch; fail without partial exposure | INV-08/09/13 |
| `read_admission(snapshot, query, plan)` | validate certificate against *same query snapshot*; return `LENS`, `SOURCE` or `ERROR_SOURCE_UNSAFE` with reason | INV-06/07/11 |
| `invalidate_source_generation(reason)` | deny older Lens after recovery, restore, schema/data migration, write-channel loss | INV-06/12 |
| `invalidate_plan_epoch(new_epoch)` | invalidate or replan prepared queries and leases | INV-13 |
| `source_health() -> HealthEvidence` | clear reliable `HEALTHY / UNKNOWN / CORRUPT` decision; UNKNOWN cannot be treated as healthy | INV-11 |
| `retain_log(min_cursor, lease)` | prevent GC before all registered builders finish, report retention loss | INV-03/12 |

## Proposed data formats (logical fields)

```
SourceSnapshotHandle {
  source_generation: UUID,
  schema_epoch: u64,
  visible_commit_seq: u128,
  isolation: IsolationLevel,
  txn_snapshot_id: Opaque,
  retention_lease: Opaque
}
CommittedDelta {
  source_generation: UUID,
  commit_seq: u128,
  transaction_id: UUID,
  ordinal_in_transaction: u32,
  before_image: TypedRow|None,
  after_image: TypedRow|None,
  checksum_or_authenticated_frame: Bytes,
  schema_epoch: u64
}
AdmissionResult = LENS(LensHandle, Certificate)
                | SOURCE(SourceSnapshotHandle, reason_code)
                | ERROR_SOURCE_UNSAFE(reason_code)
```

The lab's `rev` increases per changed row. **Do not blindly map row sequence to a production commit LSN.** Core must define commit-order grouping, intra-transaction ordinal, visibility and replay boundary. Aborted transaction IDs may leave numeric gaps if allocated early; the continuity guarantee must be defined over committed stream positions, not naive consecutive raw WAL bytes.

## Semantic and security responsibilities

- Core enforces immutable Lens bytes/manifest after publish; Safety cannot verify memory arbitrary actors can mutate.
- Core cannot claim attested capture merely because all official calls used one API; external DML, import tools and migrations are part of the surface.
- If raw privileged writers can edit journal/catalog, return `UNVERIFIED` and no acceleration; don't make the operator-entered Boolean a security control.
- On every new transaction snapshot, bind read plan to `visible_commit_seq`. An older pinned transaction must not be forced to read a newer-only Lens.
- Plan cache and schema generation require explicit invalidation; references must be safe under concurrent reclamation (lease/hazard pointer/epoch reclamation).
- Integer overflow, expression predicate semantics, collation, nullability, collation version and schema migration must be included in `supported_query_semantics`.
- Core owns durability and transaction isolation; Proof Gate cannot assert these on its behalf.

## Interface review questions (blocking)

1. What exact `commit_seq` is guaranteed across multi-shard and multi-process commits?
2. How is log generation separated from tenant-controlled writes and from alternate import/recovery paths?
3. How are older snapshots retained across cutovers without starving retention/GC?
4. What is the crash-atomic manifest publication primitive, including disk sync semantics?
5. How can Core attest source integrity rather than infer it from `integrity_check`?
6. Can Core revoke all old compiled Lens-plan handles and safely reclaim old Lens memory?

**Deliverable status:** this file is a review request, **not an accepted interface or confirmed communication to another chat**.