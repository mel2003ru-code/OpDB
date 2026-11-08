# OpDB Headquarters — canonical checkpoint

**Snapshot date:** 2026-11-08 UTC  
**Repository:** [mel2003ru-code/OpDB](https://github.com/mel2003ru-code/OpDB) (private)  
**Baseline inspected:** `e52f5a538d89c16f691a599fbb759f491af64698`; use **live main**, not this snapshot SHA, for subsequent changes.  
**Status:** active Foundry research; native production DBMS **NOT VERIFIED**.

## One-paragraph context
OpDB, formerly MELDB, is intended to become a free, open, reliable, high-performance adaptive DBMS. Correctness, user data, repeatability and full optimization cost outrank benchmark speed. Long-term ideas include Microshards, Dense/Sorted/Fenwick/Tiles, Reflex PRIME, Cost Guard, Adaptive Indexing and Proof-Carrying Lens. R1–R14 and later experiments provide experimental evidence, not a finished production engine. The immediate milestone is **Verified Lens 0.1**, with SQLite as the authoritative durable Source, optional disposable Lens views, and a fail-closed Proof Gate.

## Engineering tracks
- **TASK-001 Safety / [#2](https://github.com/mel2003ru-code/OpDB/issues/2)**: ADR-002 **PROPOSED**; reported 24 lab tests; invented/forged journal counterexample shows incorrect Lens answers are possible without trustworthy capture. NOT independently re-executed by Headquarters.
- **TASK-002 Core / [#3](https://github.com/mel2003ru-code/OpDB/issues/3)**: ADR-003 **PROPOSED**; reported 29 local tests; minimal Python/SQLite `str -> bytes` KV Lens research implementation. No native OpDB WAL or full SQL; source ZIP not yet imported into GitHub.
- **TASK-003 Quality / [#4](https://github.com/mel2003ru-code/OpDB/issues/4)**: ADR-004 **PROPOSED**, isolated differential/metamorphic lab; independent combined Safety+Core code is NOT VERIFIED.
- **TASK-004 Integration / [#5](https://github.com/mel2003ru-code/OpDB/issues/5)**: reconcile semantics; request executable, traceable PRs with original source, tests, seeds, environment and risk notes.
- **P0 / [#21](https://github.com/mel2003ru-code/OpDB/issues/21)**: **BLOCK** derived acceleration when source/journal capture is untrusted or privileged writes can forge evidence. Source-only remains safe mode under available SQLite guarantees. Never treat a boolean “trust me” flag as real attestation.

## Active automation and limits
- [10 research probes R01–R10](https://github.com/mel2003ru-code/OpDB/issues/17) execute via GitHub Actions at UTC :07/:37 and after main pushes (7 SQLite reference probes + 3 pure Python models). All tests are bounded synthetic sanity checks, not the ten research chats running autonomously.
- Daily GitHub progress status and rolling per-day research summary use Issue #17; cross-runtime CI and Crossref literature radar also exist.
- GitHub Actions storage quota previously prevented artifact uploads; raw JSON is retained in run logs and run summaries.
- TASK-001/002/003 still report NOT_CONFIGURED in the 30-minute runner until admitted executable implementations are imported.
- Full autonomous ChatGPT/LLM coding and cross-chat synchronization are **not installed** in Actions. No paid API, automatic merging, production access or deployment has been enabled.

## Authoritative docs, branches and PRs
- [ADR-001](../adr/ADR-001.md): accepted direction, not proof.
- [ADR-005](../adr/ADR-005-integration.md): proposed integration gates.
- [PR #20](https://github.com/mel2003ru-code/OpDB/pull/20): **DRAFT** documentary intake of proposed ADR-002/003/004, no original runnable ZIP bytes (Library file materialization was denied in Headquarters).
- [PR #6](https://github.com/mel2003ru-code/OpDB/pull/6): earlier **DRAFT** evidence gate / protocol proposal; may be superseded by a rebased replacement. Do not assume merged.

## Required next engineering experiment
1. Require a trusted source mutation stream or explicitly deny accelerated reads. Document threat model and externally writable SQLite journal/trigger metadata (#21).
2. Reconcile Safety's source generation / schema epoch / *commit* sequence / plan epoch / capture attestation with Core's `source_id`, `schema_version`, row-level `revision`, in-process pointer. Do not equate row-event revision with a native globally ordered commit sequence.
3. Obtain runnable original Safety+Core code and run Quality's independent oracle *on target implementation*, with external DML, PK rename, DDL, forged journal, gaps/duplicates, crashes, long log, memory, cutover latency. Report PASS/FAIL/NOT VERIFIED **per invariant**.
4. Review and merge only independently validated safe changes. Keep P0 open until direct adapter tests demonstrate fail-closed behavior and enforceable capture assumptions.

## Ready-to-paste mini-context for a new OpDB workstream
> We work on private GitHub mel2003ru-code/OpDB. Read docs/HEADQUARTERS_CHECKPOINT.md, ADR-001, ADR-005 and Issues #2–#5/#21 first. OpDB Verified Lens 0.1 is Python/SQLite research, not production. Safety ADR-002, Core ADR-003 and Quality ADR-004 are PROPOSED. P0: external privileged journal forgery invalidates proof; Source-only until trusted capture. Preserve independent Quality checks, source SHA, seeds, results and negative counterexamples; do not alter production or auto-merge.
