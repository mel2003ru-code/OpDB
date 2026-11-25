# PROGRESS

Journal of the automation cleanup. Updated after each stage.

## Goal

One conductor of the agent cycle (the executor on VPS1), GitHub Actions as CI
only, merge only on green checks, nothing else starting the cycle.

## Inventory (2026-11-25)

- VPS1: `opdb-executor.service` is the only conductor. It is a daemon that polls
  about every 15 minutes, holds an exclusive lock (`executor.lock`, `flock`)
  and has a daily model budget. No OpDB entries in crontab. Timer
  `opdb-test-queue-worker.timer` is disabled.
- GitHub Actions: no `schedule` triggers. Four workflows are paused
  (`workflow_dispatch` only). Five run on pull requests, and `handoff-schema`
  also runs on push to `main` (build, Python tests, `cargo test --offline`).
- `main` protection: checks `validate-handoff-metadata` and `protected-files`
  are required, branches must be up to date, admins are not exempt.

## Decisions

- Keep the executor as a daemon, not cron (owner choice). It already has a lock
  and a single loop, so a second scheduler would only add a second conductor.
- Cycle report stays as is: a Russian comment in the agent journal issue
  (AGENTS.md step 5) plus the machine status comment in issue #43.
- No agent-side changes to `agent.py` in this stage.
- `.github/` is a protected path: changes there need the `owner-approved`
  label, so they go in a separate PR.

## Findings

- Cycle failures are rare (4 in two days) and recover through backoff. The
  recorded cause for the latest model call: the model returned an empty `files`
  list for TASK-022, a measurement-only task. Hence `TASKS.md`.

## Stages

- [x] 1. Inventory of everything that starts the cycle
- [x] 2. Single conductor (nothing to disable: no competing scheduler on VPS1)
- [x] 3. Lock against parallel runs (already present in the executor)
- [x] 4. `TASKS.md` with small tasks and the one-task-one-PR rule
- [x] 5. CI: drop the duplicate `push` run on `main` (separate PR, needs the `owner-approved` label; PR `ci/drop-duplicate-push-run`)
- [x] 6. Cycle report (already produced by the executor)
- [x] 7. Check one real cycle on VPS1 (2026-11-25 15:54 MSK: executor restarted, cycle finished in about 5 s, `failed_tests: 0`, `open_prs: 1`, `automatic_merge: false`; blocker: open task PR #94 awaits CI/review)

## Open questions for the owner

- VPS2: the docs on VPS1 mention an older agent there (the GitHub App was moved
  from it). Owner decision: the project lives on one server, VPS2 is not
  touched or inspected.
- Merge policy: decided by the owner on 2026-11-25 (see "Merge gate" below).

## Merge gate (owner decision 2026-11-25)

- VPS1 controller now merges its own task PR (`task-NNN-vps1`) only when, on the
  exact HEAD: the independent model review approved it, both required checks
  (`validate-handoff-metadata`, `protected-files`) are green, `unittest` and
  `cargo test --offline --locked` pass in the isolated sandboxes, no protected
  path is touched and `main` has not moved. HEAD is re-read right before the
  merge and passed as `sha`. No GitHub auto-merge, no bypass of branch protection.
- Code lives outside the repository: `/opt/opdb-agent/merge_gate.py` plus a
  3-line hook in `agent.py`. Backup before the change:
  `/root/opdb-backups/premerge-20261125T1304Z`. Switch off without a restart:
  create `/var/lib/opdb-agent/merge.disabled`. Rollback: restore `agent.py`
  from the backup, delete `merge_gate.py`, restart `opdb-executor`.
- `rust_runner.py` now accepts `examples/*.rs`; before that every
  `cargo test` run on the current `rust/opdb-core` would have been refused.
- PR #94 (TASK-022) closed, TASK-022 is `BLOCKED_OWNER`; TASK-023..025 are `READY`.

## Three cycles (2026-11-25)

All three cycles took TASK-023. `main` stayed at `0eebc9e`. Nothing was merged.

| # | Time (server) | Task | PR | CI on the PR | Result |
| --- | --- | --- | --- | --- | --- |
| 1 | 16:25 | TASK-023, attempt 1 | #99 (draft, reservation only) | `protected-files` pass; `validate-handoff-metadata` running | `independent_candidate_review_rejected`: file of repeated imports, truncated |
| 2 | 16:41 | TASK-023, attempt 2 | #99 | unchanged | rejected: one line of imports, no tests |
| 3 | 16:56 | TASK-023, attempt 3 | #99 | unchanged | rejected: repeated `io` imports, placeholder text |

- Cause: the free author model (`nvidia/nemotron-3.5-lightning:free`) degenerates
  into repetition instead of writing the test file. The independent reviewer
  caught every attempt, so the review gate works. The merge gate itself was not
  exercised on a real PR: there was nothing to merge.
- Controller state after the cycles: TASK-023 has used 3 of 3 attempts; the
  next tick marks it `blocked_owner`. PR #99 stays open and blocks new tasks
  until it is closed. Calls to models in the last 24 h: 19 of 36, all free.
- The backoff was shortened once by hand (`next_cycle` set to now) at the owner's request.

## Controller fixes after the first cycles (2026-11-25, all on VPS1, outside the repository)

Each change was made with a backup in `/root/opdb-backups/` (`premerge`, `preroles`, `preraw`, `pretemp`, `pretext`, `prerev`, `prectx`)
and restoring that `agent.py` plus a restart of `opdb-executor` reverts it.

| Change | Why |
| --- | --- |
| Author model: `nemotron-3.5-super-vl` first, then `ultra`, `lightning` (plain-text mode only) | `lightning` and `ultra` never produced a test file |
| Author protocol: plain text blocks (`=== FILE: path ===` ... `=== END ===`) instead of a file inside tool-call JSON (`author_text.py`) | models looped on imports or broke JSON escaping; with blocks `super-vl` writes complete test files |
| Raw author replies kept (last 12, `raw-*.json`) | diagnosis; this is how the cause was found |
| Review prompt: findings only for real defects, no praise | praise in `findings` made the controller reject good code |
| Reviewer context 15 000 -> about 56 000 chars (author 48 000 -> 56 000) | the reviewer saw one third of `opdb/numeric.py`, invented API facts and contradicted itself |
| Author temperature 0.7 for file-writing calls | no effect on the failure; harmless, may be reverted |

## State at the end of the day

- `main` = `cad0bd9`. No task PR merged yet: the merge gate (`merge_gate.py`) has never run against a real candidate.
- TASK-023 and TASK-024: cancelled after three rejected attempts each (PR #99, #102 closed).
- TASK-025: the spec was wrong (it assumed `apply()` raises when a row of `opdb_nlens_val` is missing; the engine does not). Fixed to a trigger-based failure injection verified by hand. Two of three attempts were spent on the broken spec, the counter must be reset before the next run. Draft PR #104 is still open.
- Model-call budget: 35 of 36 used until 00:00 UTC (03:00 Moscow time).
- GitHub had an open incident during these runs (App token HTTP 500, PR and merge API 502): a `gh pr merge --delete-branch` during it closed PR #103 instead of merging it, fixed by restoring the branch; merges now go through the REST API with the exact head SHA.
- Review runs before the sandbox, so a flawed test is rejected by the model before it is ever executed. Running the candidate's tests in the sandbox first and giving the real failures to the author is the next improvement (needs an owner decision).
