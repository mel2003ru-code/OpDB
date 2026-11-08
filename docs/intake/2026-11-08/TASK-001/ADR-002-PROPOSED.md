# ADR-002 — OpDB Safety Protocol / Proof Gate

- **Project:** OpDB Foundry / TASK-001 SAFETY
- **Date:** 2026-11-08
- **Status:** **PROPOSED / pending reconciliation with ADR-001 and Core/Quality**
- **Scope:** safe admission of optional derivative data structures (Lens, secondary indexes, materialized summaries, read accelerators)
- **Priority:** correct, reproducible query results > optimization benefit.
- **Authority:** research proposal, **not** a change to a production OpDB system.

## 0. Provenance and missing source material

Read directly: library reports `REPORT_R12.md` (98 lines), `REPORT_R13.md` (154 lines), code `opdb_r14_independent.py` (275 lines), accessible `opdb_research_lab_r15_results.json` excerpts and project-history summaries. R12 reported a stale prepared-statement result in its Python/SQLite environment, not a universally confirmed SQLite engine defect. R13 found a stale Lens after direct external SQL writes. R14 available independent code is an in-memory/SQLite research model, not a proof of industrial safety. R15 reports a same-version Lens content-tamper counterexample.

**Unavailable:** full authoritative text of ADR-001, full primary transcripts for Headquarters and all R7–R14, full canonical package `OpDB_R14_Research_Package.zip` (only separate accessible research code/report fragments were verified). Local searches in project/Library and connector searches in Drive and accessible GitHub installations did not reveal ADR-001. Therefore this proposal must be reconciled with ADR-001 before adoption. Historical summaries are secondary context, not authoritative ADR text.

## 1. Decision

### 1.1 Principle

An optimization cannot authorize its own correctness. Proof Gate controls the *right to use* a derivative structure, not the truth of the data.

1. **Source is authoritative.** No optional Lens may be the only durable copy of a committed state. An absent/stale/unproven Lens must not prevent queries against a healthy Source.
2. **A visible snapshot, not a wall clock, defines read correctness.** Read the fence tuple and the query data in the *same* transaction snapshot.
3. **Unverified journal provenance means Lens disabled.** Ordinary external DML may be supported only when the storage engine unavoidably captures its changes atomically. Privileged modification of the capture path, meta or journal is outside this trust model: capability isolation or source-only operation is mandatory.
4. **Publish immutable Lens only after verifying the initial snapshot and a contiguous committed delta stream.** A version alone or a sampled checksum is not a proof.
5. **Short cutover is policy-bounded.** Reject/cancel if tail size, lock acquisition time, validation budget or dependencies exceed limits. Do not move unbounded source scans into a writer-locked section.
6. **Fail closed by default.** A broken Lens means `SOURCE_ONLY`; a corrupt or unknowably durable Source means **error/quarantine**, not silent use of Lens.

### 1.2 Proposed certificate (logical interface, not a cryptographic proof)

```
ProofCertificate {
  protocol_version, source_generation, schema_epoch,
  source_snapshot_id, snapshot_seq,
  applied_seq, lens_generation, plan_epoch,
  lens_type, supported_query_semantics,
  source_snapshot_digest, lens_content_digest,
  journal_watermark, validation_method,
  immutable_lens_id, validated_at,
  capture_attestation, trust_domain
}
```

The certificate records checkable claims. Hashes only detect some accidental corruption; **neither a digest nor a version guarantees semantic equivalence** if Source, journal, verifier or catalog is malicious. The laboratory fingerprint (`XOR(SHA256(group,value))`) is an incremental non-authenticating consistency aid; it is explicitly **not** a tamper-resistant signature or full proof.

## 2. Consistency model: ACID, isolation, snapshots

- **Atomicity:** Source mutation and the corresponding before/after change record must be committed in the same storage transaction. A rolled-back transaction contributes no committed delta.
- **Consistency:** checked constraints and application invariants must hold for Source; index invariants are *additional* and cannot weaken Source constraints.
- **Isolation:** for transaction `T`, `read_source(T)` and `read_certificate_fence(T)` must observe the same visible snapshot. At `READ COMMITTED`, this may mean one statement snapshot; at `REPEATABLE READ`/snapshot isolation, the whole transaction's pinned snapshot. Serializable isolation must be provided by Core, not inferred from Proof Gate.
- **Durability:** after acknowledged commit, Source recovery follows the storage engine's real durable-commit contract; Lens is disposable. SQLite `WAL + synchronous=FULL` under a suitable VFS models a baseline, not OpDB power-loss durability.
- **Long readers:** release builder snapshots promptly, because long-lived WAL readers may prevent checkpoint completion; retention/pressure must be accounted for.

**Do not conflate:** transaction serializability, statement snapshot consistency, pointer-cutover linearizability and power-failure durability. These are different proof obligations.

## 3. State machine

```
SOURCE_ONLY
  -> SNAPSHOT_PINNED -> BUILDING -> VERIFYING -> CATCHING_UP
  -> READY -> PUBLISHING -> ACTIVE

SNAPSHOT_PINNED|BUILDING|VERIFYING|CATCHING_UP|READY|PUBLISHING
  --error/cancel/budget/invalid journal--> ABORTED -> SOURCE_ONLY
ACTIVE --epoch change/schema change/log loss/health signal--> INVALIDATED -> SOURCE_ONLY
ANY --untrusted source or journal / corruption / operator safety stop--> QUARANTINED
QUARANTINED --documented source/journal audit + rearm + NEW build--> SOURCE_ONLY
PROCESS_RESTART -> RECOVERING -> SOURCE_ONLY (published Lens is ephemeral in v0)
```

**Modeled vs implemented:** the Python reference implements a restricted logical subset: `SOURCE_ONLY`, built/verified `Candidate`, attempted `PUBLISHING`, immutable `ACTIVE` and `QUARANTINED`. The complete state-machine diagram is a proposed Core contract; durable or distributed transitions are not implemented.

| Transition | Preconditions | Atomic commitment / action | On failure |
|---|---|---|---|
| Begin build | Source healthy, capture attested | Pin a consistent snapshot and record its generation/seq/schema | Abort |
| Verify candidate | Independent Source result at same snapshot, candidate digest | Record certificate for immutable candidate | Discard |
| Catch up | Every `seq` after snapshot present once in order, all before-images consistent | Deterministic replay with duplicate/gap checks | Discard |
| Publish | Tail and lock budget acceptable, same source generation/schema, not superseded | Commit cutover metadata then atomically expose versioned immutable pointer | Keep previous safe path; no partial Lens |
| Read | Query supports Lens semantics, certificate matches read snapshot and plan epoch | Use Lens | Read Source from same snapshot |
| Source unhealthy | Integrity/authentication/durability uncertain | Quarantine Source and Lens | Error; no false success |

## 4. Formal invariant proposals (NOT machine-checked)

Let `S(g,v)` be committed Source state in generation `g` at visible sequence `v`; `L` be a derivative structure; `F_q(S)` be the independent correct answer for supported query `q`; and `G_q(L)` its Lens evaluation.

- **INV-01 Single authority:** `Committed(T) => DurableAuthority(T)=Source` within the declared storage durability assumptions; Lens is never required for Source recovery.
- **INV-02 Transactional journal:** `Delta(e) <=> corresponding Source row mutation committed` with both in the same transaction; rollbacks create neither visible change nor visible increment.
- **INV-03 Order/continuity:** for a build from `v0` to `v1`, replay receives exactly `v0+1, ..., v1`, once and in committed order; no gaps or duplicates; generation unchanged.
- **INV-04 Snapshot equivalence:** `L0 = Derive(S(g,v0))` and independent exhaustive reference comparison for the explicitly supported query family passes on the same snapshot.
- **INV-05 Inductive replay:** if `L_i = Derive(S(g,i))` and `Delta(i+1)` is accurate and the updater respects `Derive`, then `Apply(L_i,Delta(i+1)) = Derive(S(g,i+1))`. This is a **proof obligation**, not an established theorem of OpDB.
- **INV-06 Admission guard:** `UseLens(q,T,L) => AttestedCapture AND TrustedLens AND HealthySource AND g_L=g_T AND v_L=v_T AND schema_L=schema_T AND plan_epoch_valid AND Supports(L,q)`.
- **INV-07 Semantic result:** `UseLens(q,T,L) => G_q(L)=F_q(Snapshot(T))`. This is the *target* correctness property, dependent on INV-02–06 and correct implementation.
- **INV-08 Atomic publication:** one versioned pointer is visible per read admission decision; concurrent publication and plan invalidation cannot create a partially initialized Lens.
- **INV-09 Immutability/retention:** published Lens and its metadata cannot change; old read leases retain their immutable version or fall back to their original Source snapshot.
- **INV-10 Budgeted cutover:** unbounded work is forbidden while holding writer locks. If tail > N, lease invalid, deadline exceeded, or log retention insufficient, no publication occurs. A software deadline is **not** a hard wall-clock guarantee under OS scheduling or storage stalls.
- **INV-11 Fail closed:** if any admission precondition is unknown/false, `UseLens=False`; if Source is also unsafe, report explicit failure.
- **INV-12 Crash recovery:** every recovered Lens must have a verified manifest and matching source generation/watermark, otherwise absent/invalidated. In reference v0 Lens is never persisted.
- **INV-13 No stale plan:** a compiled plan referencing a Lens generation cannot silently survive a cutover/schema generation change; refresh/replan or use Source.
- **INV-14 Trust separation:** writers permitted to change Source must not be able to forge change records/certificates independently of the storage engine. If such permissions exist, disable Lens.

### Proof sketch / gap

Under trusted atomic capture (INV-02), complete contiguous events (INV-03), correct initial derivation (INV-04), correct delta evaluator (INV-05), immutable publication (INV-08–09), and same-snapshot fencing (INV-06), induction from `v0` through `v1` implies the target semantic result (INV-07). **None of the trust axioms, updater semantics or concurrent implementation has been formally proven here.** The negative journal-forgery test falsifies the property when trusted capture is absent.

## 5. Cutover and linearization

1. Gather `(generation, seq=v0, schema)` and Source rows/reference aggregation under one consistent reader snapshot.
2. Release the read transaction. Build/verifiably seal a private candidate outside locks.
3. Prepare copies outside the writer-critical section. Acquire a short storage fence; confirm generation/schema; read current committed watermark `v1`.
4. Abort if `v1-v0 > MAX_TAIL`, log gap, old-row mismatch, timeout, superseded candidate, untrusted origin, or any verification failure.
5. Replay the bounded tail under the fence, preserving immutable publication.
6. Release the fence, then atomically publish a versioned pointer. A writer can commit between release and pointer publication; **reads still compare the Lens's `v1` against their own snapshot `v` and fall back if unequal**.
7. Increment plan generation and invalidate stale handles; a query already attached to an older transaction snapshot uses an appropriate immutable Lens or Source from that same snapshot.

The pointer assignment is the **candidate linearization point for the cutover operation**, not a proof of general database linearizability. A snapshot-isolated read may legitimately return the value of an older pinned transaction and is not a fresh linearizable read. Full linearizability and serializable histories for arbitrary OpDB transactions are **unproven**.

## 6. External writers, DDL, statement cache

- External `INSERT/UPDATE/DELETE` through regular SQLite SQL triggers are captured in the same database transaction in this prototype, even when the application `ProofGate` API is bypassed.
- `DROP TRIGGER` changes SQLite's schema cookie and causes Source fallback, **provided the schema cookie itself is trustworthy**.
- External privileged manipulation of `changes`, `meta`, `sqlite_schema` or unsafe recovery tools is **not supported**; the negative test shows forged journal payloads can fool the replay. A Boolean laboratory trust flag is not an attestation system.
- Recommended Core control: engine-owned immutable commit stream, protected capability-separated catalog/manifest, strict epoch invalidation, and deny Lens acceleration when independent raw writers cannot be captured reliably.
- After DDL or Lens generation change, invalidate and recompile prepared plans; do not assume a plan cache remains safe. The Python model uses `cached_statements=0` only as a conservative test isolation measure.

## 7. Crash, corruption and recovery matrix

| Fault window | Expected v0 behavior | Verified here? |
|---|---|---|
| Crash before candidate completion | discard candidate, Source untouched by builder | Simulated process exit |
| Crash during catch-up | same; no persistent partial Lens | Process exit before publish simulated |
| Crash immediately after publication | restart has no in-memory Lens; Source-only | Process exit after publish simulated |
| Crash during storage Source COMMIT | defer to storage/WAL guarantees | Not fully fault injected |
| Loss of power or torn write/fsync lie | quarantined/recover Source using trusted backups, don't assert durability | **Not tested** |
| Candidate corruption before publish | reject | Tested |
| Tamper after verification but before publication | reject via prepublication fingerprint | Tested in a limited injected window |
| Source corruption while still queryable | detect with application checksum/audit; quarantine if detectable | **Not verified** |
| Privileged journal forgery | must disable Lens at trust boundary | **Counterexample demonstrates unsafety** |
| Stalled lock holder | reject publication after short timeout; Source remains available | Tested locally, not hard real time |
| New schema/plan | invalidate Lens/plan, Source-only until renewed proof | Tested for schema; not all prepared SQL variants |

`PRAGMA integrity_check=ok` checks low-level storage invariants, not application meaning or acknowledged-transaction history; it must not be treated as proof of user data correctness.

## 8. Performance, constraints, and safe rejection

Policy defaults **for the laboratory only:** `MAX_TAIL=16`, nominal writer-lock budget 25 ms; this is a measurable policy target, not a universal SLO. Persisted snapshots and logs need bounded storage plus lease/retention protocol, absent from v0. Builders must be cancellable on memory pressure and avoid long-lived WAL snapshots; large tails, repeated failures, malformed events or unknown trusted capture must disable acceleration and preserve Source reads.

Strict admission is likely slower and more expensive than early index availability. Resource admission, ROI choice and predictive switching remain **out of scope** for Safety; Core/Cost Guard decides whether a *safe* optional structure is worth building.

## 9. Test acceptance conditions and rollout blockers

Mandatory Core+Quality acceptance, **not all met**:

- A contract-level test suite enumerates at least INV-01–INV-14 and traces every check to the owning API.
- Multi-process read/write/DDL schedules, rollback, duplicate/gap/malicious delta, large-tail cancellation, overflow, schema invalidation and prepared-plan races exhibit no silent wrong answer within declared threat model.
- Trusted change capture must be enforced by capabilities/storage design, not caller assertion.
- A real OpDB storage implementation must verify durable-commit acknowledgements, manifest recovery, fault injections including power loss and bit rot, replay retention/GC, exactly-once or idempotent replay.
- Formal state-machine model (TLA+/PlusCal or equivalent) with at least safety invariants and fairness/liveness assumptions must be explored; real implementation must be checked against model traces.
- Observe p50/p95/p99/max writer stalls for realistic heavy and multi-process traffic, including background snapshot CPU/RAM/I/O, and reject any optimization that violates latency budgets.
- ADR-001 MUST be obtained and reconciled; Core/Quality interfaces must be reviewed before merger.

## 10. Rejected approaches

- **Version-only proof:** R15 negative result shows content can be wrong despite matching epoch.
- **Sample queries under final writer lock:** not exhaustive and produced long cutover stalls in R13.
- **Unbounded replay under final lock:** latency hazard; abort and retry instead.
- **Trusting an in-process `Store` API:** external SQL bypasses its instrumentation; use engine-owned atomic capture or disable acceleration.
- **Assuming `integrity_check=ok` implies user-data durability:** checks a different property.
- **Publishing disk-persistent Lens in v0:** avoid until verified manifest/recovery protocol exists.

## 11. References — primary sources

- PostgreSQL, MVCC / concurrency control: https://www.postgresql.org/docs/current/mvcc.html
- PostgreSQL, transaction isolation: https://www.postgresql.org/docs/current/sql-set-transaction.html
- PostgreSQL, concurrent index builds: https://www.postgresql.org/docs/current/sql-createindex.html
- PostgreSQL, prepared plan invalidation: https://www.postgresql.org/docs/current/sql-prepare.html
- PostgreSQL, logical decoding, slots, exported snapshots: https://www.postgresql.org/docs/current/logicaldecoding-explanation.html
- SQLite, WAL snapshots/checkpoint pressure: https://www.sqlite.org/wal.html
- SQLite, isolation and `BEGIN IMMEDIATE`: https://www.sqlite.org/isolation.html
- SQLite, trigger behavior: https://www.sqlite.org/lang_createtrigger.html
- SQLite, durability settings: https://www.sqlite.org/pragma.html
- SQLite, prepared-statement lifecycle: https://www.sqlite.org/c3ref/prepare.html
- SQLite, integrity checks: https://www.sqlite.org/pragma.html#pragma_integrity_check
- RocksDB, MANIFEST/VersionEdit recovery: https://github.com/facebook/rocksdb/wiki/MANIFEST
- Herlihy, M. and Wing, J. (1990), *Linearizability: A Correctness Condition for Concurrent Objects*, ACM TOPLAS 12(3), 463–492, DOI 10.1145/78969.78972; author's PDF https://www.cs.cmu.edu/~wing/publications/HerlihyWing90.pdf

**Decision:** do not enable Proof Gate on production data; submit to ADR review. The test prototype is a correctness research instrument with a known counterexample for privileged journal manipulation.