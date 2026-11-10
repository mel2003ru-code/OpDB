# Rules for AI agents working on OpDB

These rules let agents develop OpDB without the owner doing routine work.
The owner sets direction ([ROADMAP.md](ROADMAP.md)) and answers questions
marked for them; everything else is done by agents under the rules below.

## The cycle

Each agent run does these steps in order and then stops.

### 1. Review open agent pull requests

For every open, non-draft pull request that implements a backlog task:

1. Wait for CI. If any check is red, leave one comment naming the failing
   check and what to fix. Do not merge.
2. Review as an independent reviewer who did not write the code:
   - check out the branch and run `python -m unittest discover -s tests -p 'test_*.py'`;
   - read the diff and confirm the new tests compare results against an
     independent reference (Source recomputation and a plain Python model),
     not against the code under test;
   - write and run at least one check of your own that the pull request
     does not contain (different seeds, odd inputs, a second store on the
     same file, an outside write). Do not commit it unless it found a bug;
   - if the task has measurements, rerun the benchmark and compare with the
     numbers in the pull request text.
3. Decide:
   - **Merge** (merge commit) when every acceptance point of the task file
     is met, CI is green, and your own check found nothing. Mark the task
     `DONE` in `workstreams/BACKLOG.md` in a follow-up commit on `main`.
   - **Request changes** with one comment listing concrete defects. After
     the third rejected round for the same task, mark it `BLOCKED_OWNER`.
4. Never merge a pull request you wrote in the same run.
5. If two open pull requests implement the same task, review both, merge
   the more complete one and close the other with a comment linking to it.

### 2. Fix a rejected pull request

If an open task pull request has a change request and no newer commits,
address it on the same branch. Then stop; the next run reviews it.

### 3. Build the next task

If no task pull request is open, take the first `READY` row of
`workstreams/BACKLOG.md`, set it to `IN_PROGRESS`, and implement its task
file as **one** pull request against `main`. Put test results and any
measurements, with the machine description, in the pull request text.

Runs can overlap. Name the branch `task-NNN-...`, and immediately before
opening the pull request list open pull requests again: if another one for
the same task now exists, do not open yours — delete your branch and say so
in the journal.

### 4. Plan

If the backlog has no `READY` rows, write one or two task files for the
next unfinished milestone of `ROADMAP.md` and add them as `READY`, in a
documentation-only pull request. Model them on
`workstreams/TASK-006-lens-0.1.md`: goal, what to build, tests that must
exist, measurement, scope limits. Milestones marked **owner decision**
must not be started; ask in the journal instead.

### 5. Report

Add one comment **in Russian, in plain non-technical language** to the
issue titled "Журнал агентов": what was merged, what was built, what is
waiting, and any question for the owner. Three to six sentences.

## Limits

- At most one open task pull request at a time.
- At most three merges per calendar day (UTC).
- A task pull request adds at most about 600 lines, tests included.
- Standard library only unless the task file says otherwise.

## What every task must be

A task changes what the engine does or measures what it does. Tasks about
process — new gates, preflights, handoff schemas, status reports, evidence
formats, role contracts — are not allowed. The project stalled on those
once already.

## Protected files

Agents do not modify or delete: existing files under `tests/`, anything
under `.github/`, `docs/adr/`, `AGENTS.md`, `CLAUDE.md`, `ROADMAP.md`,
`LICENSE`. Adding new test files is expected. CI enforces this; only the
owner lifts it with the `owner-approved` label. If a protected file looks
wrong, describe the problem in the journal.

## Honesty rules

- Correctness before speed. A Lens answer that differs from Source is a
  release-blocking bug.
- Report measurements as they are. A negative result is a valid outcome.
- Compare only what was measured. No claims about other databases without
  a benchmark of that database in the repository.
- Never weaken, skip or delete a test to make a change pass.

## When to stop and ask the owner

Use the journal and mark the task `BLOCKED_OWNER` when a decision changes
the project's direction or cannot be undone: on-disk format, programming
language of a native engine, threat model, license, public claims,
anything outside this repository. Then continue with the next task.
