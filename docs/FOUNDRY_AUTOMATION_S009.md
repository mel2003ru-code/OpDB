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
