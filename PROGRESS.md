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
- [ ] 5. CI: drop the duplicate `push` run on `main` (separate PR, needs the `owner-approved` label)
- [x] 6. Cycle report (already produced by the executor)
- [ ] 7. Check one real cycle on VPS1

## Open questions for the owner

- A second agent may exist on VPS2 (the GitHub App was moved from there). Not
  inspected: out of scope for this stage.
- AGENTS.md allows the author to merge after green checks, while the VPS
  controller is hard-coded to never merge. Which is intended?
