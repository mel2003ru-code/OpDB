# OpDB Foundry S-009 — limited scheduled engineering autopilot

**Scope:** real recurring *reviewable draft development* with NO general
worker execution or autonomous release. Existing task:
`OpDB Foundry — инженерный автопилот` (daily 03:00; ChatGPT Automations,
not a trusted OpDB launch service).

## What changed

The scheduled engineering task now prioritizes useful changes to existing
draft PR #32, records evidence in Issue #31, avoids duplicate PRs, and
does not repeatedly re-run CI when GitHub assigns no runner. This is a
**bounded developer assistant automation**. It is NOT the owner's green-button
activation of full autonomous OpDB Foundry.

`foundry/automation_worklist.json` is the machine-readable stage queue.
`foundry/automation_queue.py` is a deterministic **read-only, plan-only**
selector. It does not read GitHub itself, call an AI API, execute a patch,
issue a commit, dispatch a job, or publish PRs. The external scheduled task
has separate access through connected tools to read GitHub and propose bounded
edits; those edits remain inside draft PR and require human review.

## Work order

| Key | Reviewable next capability | Dependency |
|---|---|---|
| FND-009A | Read-only bounded GitHub snapshot (PR #32/#33/#34, P0 #21, Issue #31, CI runner classification and exact HEAD SHA) | none |
| FND-009B | Idempotency ledger for the scheduled engineering task, tied to issue/task identifier and verifiable GitHub evidence | FND-009A |
| FND-009C | Human/Safety/Quality review handoff and minimal evidence manifest, never execution authority | FND-009B |

The queue has only `READY`, `DONE`, `BLOCKED`. The automated iteration
selects the first READY task whose predecessor is DONE. Move a task to DONE
**only** after a real reviewable GitHub commit or PR discussion entry exists,
and set its `evidence_url` accordingly. Task progress is advisory, cannot
prove independent Quality review and is NOT a cryptographic log. If a task is
BLOCKED, report the concrete reason instead of silently skipping it.

## Offline use

```bash
python -m foundry.automation_queue \
  --queue foundry/automation_worklist.json \
  --expected-sha <ACTUAL_40_HEX_PR32_HEAD> \
  --ci-state NO_RUNNER \
  --output next-safe-task.json

python -m unittest -v tests.test_automation_queue
```

CI state is one of `PASS`, `FAIL_EXECUTED`, `NO_RUNNER`, `UNKNOWN`.
All inputs are advisory and must be independently checked against the real
GitHub API. `PASS` does NOT mean independently verified evidence.

**Exit 0** means a review-only plan was produced or the queue claims
completion, NOT that code was executed or a task passed tests.
`NO_RUNNER` may still produce a bounded reviewable next step, but never
claims CI GREEN. `FAIL_EXECUTED` recommends investigation instead.
The scheduler must never treat a QUEUE_COMPLETE or synthetic PASS as
production readiness, worker admission, merge, or launch permission.

## Hard boundaries

- Current `main` is not a protected independent trust root.
- All files in draft PR #32, including this selector and worklist, are mutable
  by the PR author. Neither is an independent controller.
- GitHub write actions, if performed by the separately scheduled assistant,
  must use the connected GitHub tool only on a verified existing draft
  branch after checking current HEAD and blob SHA, no force push or merge.
- No guest credentials, Docker socket, paid inference, deployment, production
  changes, unapproved infrastructure, arbitrary LLM-code execution, or Lens
  activation while P0 #21 is OPEN.
- Any CI runner_id=0 with steps=[] is **NOT EXECUTED**; its FAILURE is not
  an observed test failure. Do not burn additional Actions cycles to obtain
  another identical unexecuted run.
- Independent Safety/Quality and owner-governed trust root remain required.
  Full Foundry Launch Gate stays NOT_READY; first start timestamp remains null.

This stage establishes a work-selection mechanism; it does not certify the
security or functional quality of later automated edits.


## S-009A: GitHub snapshot reader (reviewable draft)

`foundry/github_snapshot.py` now consumes one bounded JSON export (<=256 KiB)
of live GitHub REST responses, using `--expected-sha` to pin PR #32. The
format is `schema_version: 1`, `repository: {full_name}`, `main` (branch
metadata), `pulls` (#32, #33, #34), `issues` (#21, #31), `runs` (up to 30
workflow-run summaries), and `jobs` (mapping of string run IDs to job arrays
with their `runner_id`, `conclusion`, `steps`, `run_id`). Only these
read-only data fields are accepted; no issue text becomes executable instructions.

The separate scheduled assistant retrieves **current** data using its connected
GitHub integration, without supplying a GitHub credential to this PR-controlled
parser. This parser does **not** itself log in, access network, or fetch GitHub.
The input is untrusted and its SHA-256 digest is only an equality fingerprint,
NOT a signed attestation.

The parser rejects mismatched main/base/PR-head SHAs and stale or unstacked
PR #34. It distinguishes a completed failed GitHub job with zero steps and
`runner_id=0` (`NO_RUNNER`) from a job that actually ran and failed
(`FAIL_EXECUTED`). A reported PASS is *still unauthenticated* and cannot grant
worker, GitHub write, Lens, launch, or merge authority.

```bash
python -m foundry.github_snapshot \
  --input exported-github-rest.json \
  --expected-sha <CURRENT_PR32_HEAD_SHA> \
  --output untrusted-advisory-snapshot.json
python -m unittest -v tests.test_github_snapshot
```

S-009A is **implemented in draft form**, NOT independently accepted; the work
queue's `DONE` means *reviewable code exists*, not CI GREEN or signed review.
The actual GitHub Actions runner allocation is currently blocked: check
individual job logs/steps rather than treating a failure-with-no-runner as
evidence of a test failing. No alternate or additional expensive CI workflow
is permitted merely to produce a green badge.

Next: FND-009B must use this bounded snapshot and a durable idempotency record
to avoid repeating already-completed engineering tasks; it must not promote
unauthenticated review results into an execution capability.
