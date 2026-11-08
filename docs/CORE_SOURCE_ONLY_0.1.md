# Core TruthStore 0.1 — independent source-only engineering baseline

**Status: RESEARCH / NEW independent implementation / NOT VERIFIED by Quality yet.**

Relates to [TASK-002 #3](https://github.com/mel2003ru-code/OpDB/issues/3), [Safety #2](https://github.com/mel2003ru-code/OpDB/issues/2), [Quality #4](https://github.com/mel2003ru-code/OpDB/issues/4), [integration #5](https://github.com/mel2003ru-code/OpDB/issues/5), [P0 #21](https://github.com/mel2003ru-code/OpDB/issues/21) and [ADR-001](../adr/ADR-001.md).

## Provenance and scope

This is a **new, minimal executable research adapter** written for OpDB Headquarters from the public repository coordination contract. It is **not a recovered import** of the separate Safety/Core/Quality teams' earlier working packages, nor an implementation of their proposed full interfaces. The historical original Core work is not silently attributed to this adapter.

- Python 3.11+ and SQLite standard-library driver. SQLite is the only authoritative transaction store.
- Typed UTF-8 keys (1..512 bytes), opaque values (0..1 MiB bytes), bounded batches (up to 10,000 operations **and 8 MiB of total key/value payload**). An unbounded input iterator is capped before opening a transaction.
- `put`, `get`, `delete`, `apply`, prefix `scan`, consistent SQLite `snapshot`, a disposable `build_lens_candidate`.
- Source-only SQL queries and experimental `check_candidate_against_source`. On reads, external SQLite rows with INTEGER/TEXT/REAL instead of BLOB, BLOB values >1 MiB or malformed keys raise `SourceIntegrityError` rather than coercing values into invented byte strings. SQL read projections avoid materializing oversized external BLOBs. This is format checking, **not** an authenticated source or anti-tamper mechanism. Publication `admit_lens` ALWAYS refuses with `UNTRUSTED_CAPTURE_P0_21`. `read_mode` is always `SOURCE_ONLY`; no code path serves users from candidate memory.
- SQLite transactions (`BEGIN IMMEDIATE` with full rollback on failure) and WAL for file-backed databases. `PRAGMA synchronous=FULL`; this is not evidence of power-loss guarantees outside SQLite's documented environment.
- Candidate content SHA256 is diagnostic; it is **not** a trusted commit identifier. A→B→A can reproduce the same digest, and privileged attackers can alter catalog/journals. No interface grants a caller authority to set `capture_trusted=true`.
- No journal replay, version-manager publication, async lens activation, change-capture trust boundary, independent WAL, SQL parser, distributed features, general production concurrency or release authorization.

## Correctness experiments

`tests/test_core_source_only.py` uses two independent oracles: direct raw SQLite query from a separate connection and a seeded Python dictionary. Scenarios include insert/update/delete; binary and Unicode boundaries; SQL injection through keys; atomic batched writes; bounded streaming batches and memory budget; trigger-induced abort; external writes/deletes/inserts; type-confusion from INTEGER (including zero), TEXT, oversized BLOB and NUL-containing keys; synthetic journal forgery; DDL trigger deletion plus schema cookie restoration; source table deletion; ABA candidate equality **never admitting Lens**; concurrent external writers; uncommitted transactions; abrupt `os._exit` before and after commit; reopen; reproducible random sequence.

These are finitely many SQLite-level experiments **not** formal linearizability proofs, storage fault injection, crash-stop cutover, verified Lens publication, or SQLite-vs-OpDB benchmarks. Positive Source-only tests do **not** close P0 #21.

## Reproduce on synthetic disposable files

    python -m unittest -v tests.test_core_source_only
    python -m unittest discover -s tests -p 'test_*.py' -v

GitHub Actions performs a separate CI run on PRs changing `opdb/**`, `tests/test_core_source_only.py`, or the workflow. Only repository checkout and read permissions are granted, no production, no external secrets, no models, no deployment.

## Next needed independent work

1. Quality review and falsification of this exact PR SHA, including external journal/trigger tampering and crash/recovery.
2. Safety and Core reconcile the full interface signatures and type/ownership restrictions; do not assume this minimal adapter is the original code.
3. Propose an enforceable capture trust boundary. If privileged external writes remain allowed, keep Source-only, no Lens publication.
4. Extend real snapshot, committed deltas, GC, cutover and tracing **only after** trust and regression evidence are established.
5. Measure construction, verification, steady-state and fault costs; qualify performance claims against independent baselines and hardware.

This prototype cannot be deployed as a stand-alone production DBMS.
