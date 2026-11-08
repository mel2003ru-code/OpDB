# Interface request to OpDB Quality — TASK-001 SAFETY

**Status: PROPOSED; not yet accepted by Quality.** This is a hand-off specification. Runtime implementation is confined to the isolated Safety prototype.

## Test contract

- **Reference oracle:** compare each Lens answer against Source evaluated under exactly the same snapshot; comparing different SQL transactions is invalid during concurrent writes.
- **Functional schedules:** inserts/updates/deletes, same-row multiple updates, rollbacks, schema change, prepared statement reuse and invalidation, old pinned snapshots, delayed writer commits, several processes and transaction isolation levels.
- **Adversarial schedules:** duplicate/missing/reordered/corrupted events; wrong old images; wrong new images; stale candidate after quarantine; generation reset; forged/removed triggers; failed manifest sync; integer overflow; overlarge tail.
- **Recovery matrix:** process kill before/after log commit, before/after cutover, concurrent checkpoint, persistent Lens re-opening (when implemented), forced power-loss simulation and torn-write injection.
- **Resource controls:** watch cutover p50/p95/p99/max including acquisition, replay, pointer update, failed attempts and source fallback; include disk bytes, WAL pin/checkpoint, RAM and cumulative CPU/IO.
- **Formal verification:** small finite model with state assertions INV-01..INV-14; exhaustive interleavings for two writers/two readers + cutover; distinguish model checking from code testing.
- **Trust-negative test:** attacker with unrestricted journal modification can forge `new_v` and make Lens return a wrong answer while `rev/schema` match. This is **expected negative demonstration** in `test_21`, *not* acceptance of an insecure production mode. In production an attestation must prevent entry into this scenario.

## Evidence requirements

Every test report must contain: source SHA-256, environment and database versions, deterministic seed, exact command, scenario name, expected vs actual semantics, number of source/Lens reads, number of publications/rejections, p99/max, crash window and recovery evidence, and full exception log for any mismatch. Mark `TESTED`, `NEGATIVE COUNTEREXAMPLE`, `UNTESTED` and `FORMALLY VERIFIED` separately; no test counts as mathematical proof.

## Runnable local reference

```bash
python3 -W error::ResourceWarning -m unittest -v test_proof_gate.py
python3 experiment.py
```

These commands create **only temporary SQLite databases**; they do not connect to production databases or external services. The test uses `lab_assume_trusted_change_capture=True` as an explicitly *unverified* research assumption; default Proof Gate rejects publication without that flag. Do not reuse that boolean as a production authorization mechanism.

## Blocking release gate

Do not ship derived-index acceleration by default until Core provides audited trusted capture, safe manifest/recovery, correct plan invalidation, multi-process fault injection, log retention, and the agreed ADR-001/ADR-002 invariant contract. Quality must review both positive proofs of evidence and negative counterexamples. Confidence should be expressed relative to tested threat model and scope.

**Deliverable status:** this file is a review request, **not confirmed receipt by another research chat**.