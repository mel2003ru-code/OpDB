# OpDB Headquarters — Research Delivery: Foundry TASK-001 SAFETY

**Report date:** 2026-11-08  
**Research owner:** OpDB Safety  
**Status:** complete **initial isolated research iteration**, ADR-002 **PROPOSED**; not production ready.  
**Requested decision:** accept the invariant boundaries for review; do **not** enable acceleration in unrestricted-writer or unverified-journal modes.

## Executive findings

1. Drafted `ADR-002_OpDB_Safety_Protocol.md` and two explicit interface requests (`CORE_Safety_Interface_Contract.md`, `QUALITY_Safety_Test_Contract.md`). This is a document hand-off inside the downloadable package; **receipt by Core/Quality chats has not been verified**.
2. Implemented reproducible Python 3.13.5 + SQLite 3.46.1 proof-gate reference: Source/WAL, database-level transactional change capture, snapshot-consistent independent Source aggregation, candidate validation, bounded replay, cutover, immutable in-process Lens, schema/revision/plan fencing, safe Source fallback, quarantine and post-crash Source-only recovery.
3. Default constructor **refuses publication** without an explicit laboratory assumption of protected capture; source reads remain available. Real privilege enforcement **is not implemented**.
4. **24 unit tests passed** (including an expected negative demonstration, crash-before/after-publication processes, cross-process raw SQL writer, no silent errors for ordinary external DML, tampered candidates and log gaps). Test success is not proof of ACID or general DB correctness.
5. Standalone repeatable workload: **120 cutover attempts, 92 publications and 28 safe rejections** due to excessive journal tail. **960 same-snapshot oracle reads, zero mismatches** within this workload; SQLite `integrity_check=ok`. Of these, 736 used Lens and 224 used Source fallback.
6. Under the measured local environment, published cutovers had p50 ~0.08 ms, p95 ~0.15 ms and observed maximum below 1 ms. These figures are **not** a hard lock-duration bound and exclude background build and other real-world costs. See `results.json` for exact measurements of this run.
7. **Falsifying counterexample:** a privileged external SQL client that edits the change-log `new_v` while preserving its sequence and correct old-image can publish a semantically wrong Lens. The negative test demonstrates this intentionally. Therefore index correctness cannot be certified from a journal that the writer can forge. Source-only is the required production posture until Core provides capture trust evidence.

## Exact measurement details

- Host environment: Linux x86_64, Python 3.13.5, SQLite 3.46.1, transient local SQLite DB, `journal_mode=WAL`, `synchronous=FULL`.
- Seed: `20261108`, source rows = 2,400, final `rev`/change-log rows = 3,483.
- Nominal cutover budget: 25 ms; maximum accepted tail: 16 row-level events. This is a **lab configuration** only.
- `low_tail`: 80 attempts -> 80 publications, 0 rejects, 640 oracle reads.
- `heavy_tail`: 40 attempts -> 12 publications, 28 `tail_over_budget` rejects, 320 oracle reads.
- Check `results.json` for instrumented p50/p95/p99/max; those may change on rerun. Numbers are one synthetic run, not confidence intervals or real production workload evidence.
- Cost deliberately **not measured here**: total memory residency, storage wear, full CPU budget, genuine power failures, latency of arbitrary SQL, kernel tail / multi-process coordination.

## What is confirmed (narrowly)

| Finding | Evidence | Scope |
|---|---|---|
| Snapshot + same-transaction source oracle | `test_11`, `test_19`, benchmark read transaction oracle | SQLite WAL, supported SUM predicate only |
| Journal captures ordinary SQL bypass of application API | `test_02`, `test_03`, `test_23` | SQLite triggers must remain trusted |
| Missing event or mismatched old-image denies cutover | `test_06`, `test_07` | Exact recorded event sequence |
| Tail overflow and held writer lock reject cutover | `test_08`, `test_13`, benchmark | Best-effort time budget, not real-time bound |
| Candidate mutation is rejected | `test_04`, `test_05` | Mutation before publication/injection windows covered |
| DDL invalidates old Lens and plan epoch guards stale plans | `test_09`, `test_10`, `test_12` | Schema-version changes that SQLite reports |
| Source survives process exit before/after Lens publish | `test_17`, `test_16` | SQLite storage responsibility; no SSD/power fault |
| Unverified capture denies activation | `test_24` | Caller-asserted lab mode, not cryptographic attestation |
| Privileged journal editing defeats version/continuity guard | `test_21` (expected failure of unsafe assumption) | Demonstrated negative counterexample |

## What is not confirmed

- Full ACID / serializable execution of a native OpDB engine; only SQLite transactions were executed.
- Formal correctness of Proof Gate or its state machine, or general linearizability of all database operations. Pointer publication has a candidate linearization point under the model's lock/epoch assumptions, but no model checker/TLA+/implementation refinement proof was run.
- Security when arbitrary clients can edit the log, metadata or `sqlite_schema`; source-only is required in such deployments.
- Persistent or replicated Lens recovery; all published Lens objects are process-local and intentionally discarded on restart.
- Real power-loss, torn-write, disk-controller cache, fsync lying, checksum collision, stealthy data corruption, acknowledged commit history after disk failure.
- Cost/latency SLO under realistic multishard, read-mostly, write-heavy, adversarial and long-running transactions; block time depends on scheduler/OS even with a configured timeout.
- Safe log pruning, retention leases, manifest crash-atomicity, cross-shard ordering, WAL corruption and application-level data checksum design.
- Safe use of every expression/predicate/collation, general SQL optimizer plans and all prepared-statement implementations.
- Compliance with ADR-001: authoritative full text was unavailable in inspected sources.

## Ten requested topics: findings and next test

| Topic | Proposed invariant / mitigation | Next blocking question |
|---|---|---|
| 1. ACID / isolation | Same transaction for Source+delta; same read snapshot for certificate check and answer | Native engine's isolation and WAL proof |
| 2. Versions | `(source_generation,schema_epoch,commit_seq,plan_epoch,lens_generation)` | Is production commit seq consistent across shards? |
| 3. Journal | Gap-free committed change stream with pre-/post-images and retention leases | Authenticity and atomicity of capture |
| 4. Linearization | Immutable atomic pointer with snapshot-revision fencing | Formal concurrent histories under Core |
| 5. Concurrency | Old readers pin old Source snapshots; fresh reads fallback after write | Memory reclamation and long snapshot pressure |
| 6. External writers | DB/engine-owned capture, never per-API capture alone | How to deny journal/meta forgery? |
| 7. Faults / corruption | Lens disposable; Source health errors stop, not silently fallback | Power-failure/fault-injection battery |
| 8. Lock time | Small tail and deadline rejection; precompute outside critical section | Worst-case OS/FS hold time, real p99 |
| 9. Safe refusal | Unverified capture -> Source-only; Source corruption -> explicit error | Source health attestation design |
| 10. Invariants | INV-01 through INV-14 in ADR-002 | TLA+ model and refinement tests |

## Interfaces and ownership boundaries

**Safety -> Core:** minimal reliable `SnapshotHandle`, `CommittedDelta`, `CaptureAttestation`, `CutoverFence`, `PublishCAS`, `ReadAdmission`, `SourceHealth`, `RetainLog` and plan invalidation. Core owns transaction correctness, storage durability and enforceable capture privileges, not Safety's local prototype.

**Safety -> Quality:** independent same-snapshot oracle; multi-process DDL, prepared statement caches, concurrency/fault matrix and both positive/negative tests. Quality owns fuzzing, exhaustive model checking, CI and real engine validation; Safety documents invariants and known counterexamples.

**Safety -> Research/Cost Guard:** no requests for index selection, caching strategy, policy tuning or CPU optimization. Gate provides only safety decision, failure codes and bounded publication; economics remains another research direction.

## Risks ranked by impact

| Rank | Risk | Status / mitigation |
|---|---|---|
| P0 | Forged/missing journal with direct writer privileges | **Demonstrated incorrect Lens.** Require protected stream or Source-only |
| P0 | Source acknowledged commit lost/corrupted | Unverified; require storage + hardware fault testing, end-to-end checks, backups |
| P0 | Incorrect expression semantics or stale prepared plans | R12 documented reproduction in one stack; require plan epoch invalidation + cross-version C API regression |
| P1 | Journal retention gaps / long WAL snapshots | Abort build and Source fallback; lease policy needed |
| P1 | Multi-shard or multi-writer commit order | Not modeled; define global/per-shard transaction cut and join conditions |
| P1 | Lock tail and stalled writer | Conservative deadlines/abort; OS cannot guarantee strict timing here |
| P1 | Lens published/persisted across crash | Explicitly disabled in v0; manifest/recovery later |
| P1 | Accidental in-memory mutation after publication | Immutable by API, not protected against hostile process/memory corruption |
| P2 | Log accumulation and redo work | No GC in v0; storage limits and retention leases needed |
| P2 | False confidence from digests/integrity checks | Distinguish integrity check, business semantics, durability and proof |

## Requested Headquarters decision

1. Record ADR-002 as **PROPOSED**; reconcile exact text against ADR-001 before merge.
2. Block production activation of optional Lens unless Core certifies protected change capture and query-snapshot fencing. Keep Source as default.
3. Assign Core the implementation of trust and storage boundaries, Quality the state-model/fault matrix and admissibility acceptance, Safety the invariant/protocol review.
4. The current package is suitable for a research review and local reproduction only.

## Reproduce and inventory

```bash
python3 -W error::ResourceWarning -m unittest -v test_proof_gate.py
python3 experiment.py
```

`proof_gate.py`, `test_proof_gate.py`, `experiment.py`, `results.json`, `test_results.log`, `ADR-002_OpDB_Safety_Protocol.md`, both interface contracts, `README.md`, this Headquarters report, `MANIFEST_SHA256.txt`.

No production/VPS, GitHub repository, hosted database or current user's data were changed. The documents are created locally; other project chats cannot be said to have read or accepted them until explicitly handed off.