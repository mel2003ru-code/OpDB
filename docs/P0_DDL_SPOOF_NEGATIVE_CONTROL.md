# P0 negative control: privileged DDL + schema cookie spoof

Status: **RESEARCH NEGATIVE CONTROL / NOT an OpDB Core+Safety acceptance test**. Related: #21, #5, ADR-001, ADR-005.

## Threat model and reproduction

An attacker with SQLite DDL/write privileges can drop the AFTER UPDATE capture trigger and then explicitly set PRAGMA schema_version back to the prior value. Subsequent writes update the authoritative kv row without changing the trigger journal or the schema cookie. PRAGMA integrity_check still returns ok. Therefore, **matching journal sequence and SQLite schema_version alone do not establish trusted capture**.

Fixture uses a temporary SQLite file, one ordinary external committed write (captured), then a privileged attack transaction (uncaptured). It asserts that an intentionally unsafe delta replay is wrong while a fresh Source-only read returns the correct committed value.

Run from repository root:

    python -m unittest -v tests.test_p0_ddl_spoof_control
    python -m unittest discover -s tests -p 'test_*.py' -v

Seeds: 203, 901, 20261108. Standard library only. Temporary fixture databases are deleted. EXPECTED_COUNTEREXAMPLE means **expected failure of an insecure design**, not PASS of the actual OpDB Proof Gate.

## Limits / engineering action

This fixture cannot demonstrate that a real Core adapter fails closed because original runnable Core/Safety code is not in GitHub main. A caller-provided trusted=True flag is not evidence of authorization or tamper resistance. For non-enforceable capture, **Lens admission remains BLOCKED / Source-only**. No production use, no automatic switching, no merge based solely on this negative control.

Next: Core supplies executable adapter source and exact commit SHA; Safety specifies enforcement and invalidation scope; Quality repeats this scenario against the actual read-admission path and records PASS/FAIL/NOT VERIFIED per invariant. Keep Issue #21 open until then.
