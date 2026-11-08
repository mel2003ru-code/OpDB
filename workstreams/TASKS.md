# Task register

Snapshot: 2026-11-08. Workstream chats were created and tasks were assigned; their execution outcomes have NOT been independently checked.

| ID | Workstream | Status | Dependency | Expected handoff |
| --- | --- | --- | --- | --- |
| TASK-001 | Safety | Assigned / NOT VERIFIED | ADR-001 | ADR-002; state machine; invariants; adversarial tests; risks |
| TASK-002 | Core | Assigned / NOT VERIFIED | Safety's publishing contract | ADR-003; API; executable prototype; tests; reproduction |
| TASK-003 | Quality | Assigned / NOT VERIFIED | Draft Safety + Core contracts | ADR-004; independent oracles; CI; evidence verdict |

## Rules
- A chat message is not an implementation result; use a traceable PR or handoff.
- No cross-workstream interface may silently change.
- Record each decision with date, originating task, issue/PR, affected version, evidence, reviewer, open risks and rollback.
- Headquarters is the integration authority. Quality independently evaluates correctness.
