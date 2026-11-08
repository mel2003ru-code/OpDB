# Quality Q-Core-001: bounded Core Source-only adversarial review

**Date:** 2026-11-08. **Scope:** experimental Python/SQLite TruthStore (Core draft PR #33). This is NOT the historical original Core handoff, independent native database engine, or industrial verification.

## Reproducible evidence and negative controls

- Core baseline: SHA 14ad0415db0a9fdf6dc3a68fe4c858b08cf467d5.
- Separate Quality test-only change: SHA 2bf4af5c362441937c778a57a081136ea7d4a0de (draft PR #34, based on Core branch, not main).
- [Negative-control run 42479550886](https://github.com/mel2003ru-code/OpDB/actions/runs/42479550886): 7 of 9 independently designed tests **FAIL** as expected, 2 PASS. Reproduces an eager input materialization/resource-control defect on the real adapter.
- Minimal implementation fix: SHA 3b44f93cf08e366827b9c2f8837dae56b7214141.
- [Quality CI 42479671148](https://github.com/mel2003ru-code/OpDB/actions/runs/42479671148): 9/9 Quality cases and 77/77 all repo cases PASS. [Core CI 42479671170](https://github.com/mel2003ru-code/OpDB/actions/runs/42479671170): 43/43 Core cases and 77/77 full PASS. Current final PR head may differ; check exact CI on final SHA before approval.

Reproduce in a disposable Python 3.11 environment:
- python -m unittest -v tests.test_quality_core_boundaries
- python -m unittest discover -s tests -p 'test_*.py' -v

## Independently designed adversarial cases

| Claim | Before | After fix and limitations |
|---|---|---|
| Bad first operation stops generator immediately | FAIL: read 10,001 entries and misreported batch cap | PASS: incremental validation; user-supplied generator side effects are outside database control |
| 8 MiB batch payload budget stops excess input consumption | FAIL: eager materialization allowed expensive generator work | PASS: stops at first over-limit record; measured logical bytes, not Python RSS |
| Closed store does not consume generator | FAIL: consumed before checking open state | PASS for store already closed; concurrent close race is not proven linearizable |
| Snapshot maximum rows | FAIL: no bound | PASS: reject above 50,000 rows, never return incomplete snapshot |
| Snapshot maximum bytes | FAIL: no bound | PASS: reject above 64 MiB key/value payload |
| Scan maximum bytes | FAIL: row limit could permit 1 GiB of values | PASS: reject above 8 MiB key/value payload |
| Under-budget content matches separate SQLite oracle | PASS | PASS on synthetic cases only |
| Resource violation never activates Lens | FAIL because cap was missing | PASS for tested cases; Lens admission is unconditionally denied |

## Proposed Safety/Core compatibility boundary — NOT a frozen contract

Only Source-only access is admitted. SQLite is the durable TruthStore. Core validates writes before BEGIN IMMEDIATE and fetches typed source rows; source reads reject type confusion and malformed rows. A snapshot SHA256 digest is only content identity: A→B→A restores the same digest without proving commit identity. A LensCandidate is disposable diagnostic data. admit_lens ALWAYS returns accepted=False; no caller-set trusted-capture flag is sufficient for admission.

Safety must define enforceable writer restriction or trustworthy committed change capture before any future publication. Actual Core+Safety interface cutover, snapshot identity, committed delta continuity, concurrent writer fencing, journal forgery, DDL/prepared plan invalidation, crash/reopen, storage/GC and cost model remain unresolved under ADR-005 and P0 #21. The resource limits do not make the system a finished SQL DBMS.

## Quality decision

- **PASS (narrow):** these 9 resource-bound tests after the fix, existing 43 synthetic Core tests, and Source-only refusal, restricted to specified CI environments/conditions.
- **FAIL on baseline:** eager batch materialization, missing scan and snapshot resource budgets. Negative control preserved in CI logs.
- **NOT VERIFIED:** independent Safety/Core integration, trusted capture, verified Lens cutover, native WAL/durability, true power-loss fault model, production release or universal superiority.
- **Review independence:** These tests were authored separately from Core tests on a distinct Quality branch, but the analysis still originates in the same assistant-mediated project workflow. It is NOT an external accountable human Quality sign-off.

**Governance:** draft PR #34 is stacked on Core draft PR #33. Review and merge Quality findings into Core only after independent review; do NOT merge into main or production solely because CI is green. The owner launch button remains disabled, and no launch timestamp has been recorded.
