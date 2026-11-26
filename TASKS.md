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
| C-03 | M3 | Script: time `open()` on a 100k-row database with a stored Lens, 30 repetitions. | `experiments/` script prints median and p95; one-page result file with machine description. |
| C-07 | M5 | Script: plain SQLite baseline for `sum`, `min`, `max` with an index, 100k rows. | `experiments/` script with raw timings; no claim about OpDB speed in the same PR. |
| C-08 | M5 | Script: the same aggregate workload on OpDB, same fixture and machine as C-07. | Raw timings in the same format; needs C-07 merged first. |

Items are independent unless a row says otherwise (C-08 needs C-07).

## Removed after checking against the engine (2026-11-26)

- C-01 and C-02 ("a damaged or stale stored Lens is detected and rebuilt") were
  wrong as written. Metadata and group-table damage IS detected at open (now
  TASK-027); damage to the value index is not looked at while opening, and a
  write to `opdb_source_kv` behind OpDB's back while the file is closed is not
  detected at all: the Lens then answers from stale data. That gap is an engine
  change, not a test task, and an owner decision.
- C-05 became TASK-029.

## Next candidates

| ID | Milestone | Task | Done when |
| --- | --- | --- | --- |
| R-02 | M6 | Rust: `Store::apply(&[Op])` writing a batch as ONE record of kind 3 with an empty key and `encode_ops` as the value; needs TASK-028 merged. | Tests: model equality, every torn cut of the batch hides it completely, a corrupt batch is `Error::Corrupt`. |
| R-03 | M6 | Rust: `compact()` rewriting the log with live records only, atomically through a temporary file. | Tests: model equality after compaction, a leftover temporary file is harmless. |

