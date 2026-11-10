# Task register (historical)

The live queue is [BACKLOG.md](BACKLOG.md). This table is kept as a record of the first workstream setup.

Snapshot: 2026-11-08. Workstream chats were created and tasks were assigned; their execution outcomes have NOT been independently checked.

| ID | Workstream | Status | Dependency | Expected handoff |
| --- | --- | --- | --- | --- |
| [TASK-001](https://github.com/mel2003ru-code/OpDB/issues/2) | Safety | Assigned / NOT VERIFIED | ADR-001 | ADR-002; state machine; invariants; adversarial tests; risks |
| [TASK-002](https://github.com/mel2003ru-code/OpDB/issues/3) | Core | Assigned / NOT VERIFIED | Safety's publishing contract | ADR-003; API; executable prototype; tests; reproduction |
| [TASK-003](https://github.com/mel2003ru-code/OpDB/issues/4) | Quality | Assigned / NOT VERIFIED | Draft Safety + Core contracts | ADR-004; independent oracles; CI; evidence verdict |
| [TASK-006](TASK-006-lens-0.1.md) | Core | Ready to start | PR #39 merged; [ADR-006](../docs/adr/ADR-006-trust-boundary.md) | One PR: engine-maintained group aggregate, oracle tests, Lens-vs-Source measurements |

## Rules
- A chat message is not an implementation result; use a traceable PR or handoff.
- No cross-workstream interface may silently change.
- Record each decision with date, originating task, issue/PR, affected version, evidence, reviewer, open risks and rollback.
- Headquarters is the integration authority. Quality independently evaluates correctness.
