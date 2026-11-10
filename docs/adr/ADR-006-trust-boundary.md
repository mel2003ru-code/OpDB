# ADR-006: Trust boundary — OpDB is the only writer of its database file

- Date: 2026-11-10
- Status: **ACCEPTED** by the project owner
- Resolves: [P0 #21](https://github.com/mel2003ru-code/OpDB/issues/21)
- Amends: ADR-001 requirement 5; `docs/contracts/VERIFIED_LENS_FREEZE_0.1.md` question 3

## Problem

P0 #21 showed that a privileged external program writing directly into the
SQLite file can forge change-capture data and make a derived Lens return a
wrong answer. The resulting policy — "no Lens until capture can be
authenticated against privileged external writers" — cannot be satisfied.
Any process that can write the database file can also corrupt the source
rows themselves. SQLite, RocksDB, DuckDB and LMDB give no guarantee in
that situation either. The policy therefore blocked the project's first
milestone permanently and work shifted to gates instead of the engine.

## Decision

1. **Single writer.** Committed data is changed only through the OpDB API
   (`TruthStore.apply` and what is built on it). The database file belongs
   to the engine.
2. **Out of scope.** A process that modifies the database file, its WAL,
   its schema or its triggers without going through the OpDB API is outside
   the threat model. OpDB does not promise correct answers after such
   modification, exactly as other embedded databases do not.
3. **Engine-owned capture.** Change capture is performed by OpDB's own code
   inside the same transaction as the write. SQLite triggers are not used
   as a capture mechanism.
4. **Best-effort detection stays.** Where an outside change is cheap to
   notice (commit sequence mismatch, `PRAGMA data_version`, type or format
   violations already checked by `SourceIntegrityError`), OpDB must drop the
   Lens, answer from Source and rebuild. This is a safety net, not a
   security guarantee.
5. **Lens admission is allowed** under the conditions in TASK-006. The
   unconditional refusal `UNTRUSTED_CAPTURE_P0_21` is retired once TASK-006
   merges.

## What does not change

- SQLite remains the authoritative store for milestone 0.1.
- A Lens is disposable and is never the only copy of committed data.
- If the Lens cannot be shown to match the Source version it was built for,
  reads fall back to Source (fail closed).
- Correctness before speed; negative results are kept.

## Consequences

- P0 #21 is closed as "out of threat model", with its forged-journal test
  kept as documentation of the boundary, not as a blocker.
- Deployment note for README: do not open an OpDB file for writing with
  other tools while OpDB uses it.
- No new gate, preflight or evidence-schema work is required by this ADR.
