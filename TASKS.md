# TASKS — small tasks for free models

Candidate pool of small engine tasks that a free OpenRouter model can finish
alone. The queue the agents actually follow is still
[workstreams/BACKLOG.md](workstreams/BACKLOG.md) (first `READY` row wins);
rules for agents are in [AGENTS.md](AGENTS.md). This file only feeds the queue.

## Rule: one task — one PR

- One task from this file becomes exactly one pull request against `main`.
- At most one task pull request is open at a time (AGENTS.md, "Limits").
- A PR touches only what the task names, about 150 lines or fewer including
  tests. If it needs more, split the task here first, in a docs-only PR.
- Standard library only. No protected files, no schema or on-disk format
  changes, no weakened or deleted tests.
- A task must change or measure what the engine does. Process tasks (new
  gates, schemas, reports) are not allowed (AGENTS.md, "What every task must be").
- Every task states its check: a new test compared with an independent
  reference (Source recomputation or a plain Python model), never with the
  code under test.
- To promote an item: a docs-only PR adds `workstreams/TASK-NNN-<slug>.md` in
  the existing format and a `READY` row in `BACKLOG.md`. Then delete the item
  here in the same PR.

## Why this file exists

A free model returned an empty `files` list for TASK-022 (measurement only,
no code to write), and the controller could not make progress. Tasks below
always end in a concrete new file or test that a model can write.

## Candidates

Milestones are from [ROADMAP.md](ROADMAP.md). M6 and M7 need an owner
decision and are not listed.

| ID | Milestone | Task | Done when |
| --- | --- | --- | --- |
| C-01 | M3 | Test: damage the stored Lens (change one value, delete one row) and reopen the database. | New test shows the damage is detected and the Lens is rebuilt equal to Source. |
| C-02 | M3 | Test: stale stored Lens (write to Source through a second connection, then reopen). | New test shows staleness is detected; answers equal Source recomputation. |
| C-03 | M3 | Script: time `open()` on a 100k-row database with a stored Lens, 30 repetitions. | `experiments/` script prints median and p95; one-page result file with machine description. |
| C-04 | M4 | Test: `min` and `max` after deleting the current extreme, with ties, negatives and Unicode keys. | New seeded test (20 or more seeds) equals a plain Python dict model. |
| C-05 | M4 | Test: caller-defined grouping, with groups appearing and disappearing in one batch. | New test equals a Python `defaultdict` model; empty groups are absent. |
| C-06 | M4 | Test: `sum` at signed 64-bit limits and on overflow. | New test checks the documented overflow behavior against Python integers. |
| C-07 | M5 | Script: plain SQLite baseline for `sum`, `min`, `max` with an index, 100k rows. | `experiments/` script with raw timings; no claim about OpDB speed in the same PR. |
| C-08 | M5 | Script: the same aggregate workload on OpDB, same fixture and machine as C-07. | Raw timings in the same format; needs C-07 merged first. |
| C-09 | M2 | Test: rollback of a mixed batch (insert, overwrite, delete) leaves Source and Lens unchanged. | New test with injected failure; compared with a copy of the store made before the batch. |

Items are independent unless a row says otherwise (C-08 needs C-07).
