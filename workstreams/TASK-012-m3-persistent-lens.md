# TASK-012 — M3: atomic persistent Lens research prototype

- Date: 2026-11-12
- Milestone: M3 — Lens survives restart
- Depends on: M2 TASK-006/007/009/010/011 completed; owner decisions in Issue #53 and Issue #43 comment 6820381645
- Deliverable: one implementation PR after this planning PR is independently reviewed and merged

## Goal

Persist Source and the derived Lens in versioned internal tables in **one SQLite database file** and **one atomic transaction**, so reopening a healthy 1,000,000-row database does not rescan all Source rows. This is an SQLite-backed research prototype only: it does not decide the native OpDB storage format or programming language.

## What to build

1. Opt-in persisted Lens mode in the existing TruthStore API. Keep the current non-persistent path available for comparison and rollback. Do not enable the persisted mode by default until safety evidence exists.
2. Store Source, Lens aggregates, generation/schema metadata and a commit sequence in one SQLite file. Apply Source mutations and matching Lens changes in the **same SQLite transaction**; a failed transaction must not advance either state. Avoid triggers unless independently justified.
3. On open, validate the persisted Lens using bounded metadata/schema/generation checks without scanning the Source table in the healthy case. Treat incompatible versions, missing metadata, stale generations, or corrupt Lens rows as untrusted; never answer from an unverified Lens.
4. Rebuild a stale/damaged Lens from a consistent Source snapshot, publish it atomically, and make repeated interrupted rebuilds safe. If a safe rebuild is not possible, fall back to Source or fail closed; never return a knowingly stale Lens result.
5. Preserve external-write detection and the Source oracle behavior of M1/M2. State precisely which external SQLite writes can be detected by metadata checks and which require fail-closed behavior; do not claim cryptographic corruption detection.

## Tests that must exist

- New independent oracle tests: at least 20 deterministic seeds of put/overwrite/delete/reinsert/batch, including empty values and repeated keys; compare persisted Lens with Source recomputation and a separate Python dict model across close/reopen.
- Atomicity: process termination before commit and after commit, injected SQLite errors, rollback and retry; after reopen Source and Lens are either both old or both new, never mixed.
- Stale/damage: second connection changes Source, tampered Lens aggregate, missing row, changed metadata/schema version, interrupted rebuild, and repeated rebuild; each must detect and repair or fail closed without returning an incorrect Lens answer.
- 1,000,000-row healthy cold open: verify with SQLite trace/progress instrumentation that no full Source table scan occurs, and check Lens results against an independently computed reference after open. Record a separate rebuild path that may scan Source.
- Run all existing tests unchanged with `python -m unittest discover -s tests -p 'test_*.py'`. Add new tests only; do not modify existing test files.

## Measurements and acceptance

- On the same machine and exact code SHA, record 10k/100k/1M rows, Python/SQLite versions, CPU, RAM, filesystem and commands.
- Measure healthy cold-open latency (median and p95), rebuild latency, SQLite file size and 1,000-row batch write overhead versus the current non-persistent Lens. Include raw results and repeated runs.
- **Acceptance gates:** (a) independent Source and Python oracle equality in all cases; (b) no mixed Source/Lens state across tested crashes; (c) stale/damaged states do not yield wrong Lens answers; (d) instrumented healthy 1M-row open performs no full Source scan; (e) full existing test suite and CI green. Performance regressions must be reported honestly, not hidden.
- If arbitrary out-of-band tampering cannot be detected without a full scan, document the precise threat boundary and ask the owner before broadening the guarantee.

## Scope limits

- Allowed implementation paths: `opdb/`, new `tests/test_*.py`, `experiments/`, and a short new research note under `docs/`; do not touch protected files or existing tests.
- Python standard library only; keep each task PR around 600 added lines including tests. If necessary, propose a smaller separately reviewed follow-up rather than weakening safety gates.
- No Foundry, PR #38 integration, deployment, native engine language/disk-format decisions, or changes to `ROADMAP.md`.
- Do not begin implementation until this planning PR has passed independent review and is accepted.
