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


## S-009B: Durable review-only receipts (draft)

The module foundry/automation_ledger.py implements a bounded, append-only
state machine using only Python's standard library. Its **persisted** state is
foundry/automation_ledger.json in draft PR #32; no assumption is made
that the scheduled ChatGPT session retains local files across days.

Each event records the allowlisted task ID, bounded sequence number, exact
observed PR commit SHA, state (CLAIMED, DONE, BLOCKED), optional exact
repository commit URL as evidence (for DONE only), and a SHA-256 chain
link. A duplicate CLAIM returns ALREADY_CLAIMED with no new event.
A completed task returns ALREADY_DONE; a conflicting evidence URL is
HOLD_CONFLICT. A crash after CLAIM leaves the claim active until reviewed:
**there is no automatic timeout, lease takeover, or restart of code work.**

The first ledger record explicitly imports the preexisting FND-009A
draft-code commit b2bf62645528b1fa880cb1238a08064f27b9d638 as
*reviewable code*, not an independently verified CI or Safety success.
Further tasks need a CLAIM before COMPLETE; FND-009C cannot be claimed
until FND-009B is recorded DONE.

### Operator/scheduled assistant protocol

1. Read current live PR #32 HEAD, P0 #21 and Issue #31, worklist JSON
   **and** ledger JSON through the connected GitHub tool.
2. Validate the ledger hash chain, compare its latest task statuses
   with the worklist, and select the first eligible task. If either file
   changed, is missing or fails validation: HOLD; don't recreate it.
3. For a READY unclaimed task, append exactly one CLAIMED event,
   then update the ledger through GitHub's **contents API using the exact
   current blob SHA** (update_file / compare-and-swap). If another writer
   updated the file, **stop, refetch and reconcile; never overwrite**.
   Record the resulting commit SHA and independently read back the blob.
4. Make only a bounded human-reviewable change on the same draft branch.
   Never execute unknown model output or perform a deployment.
5. Append DONE with a real exact-repository commit URL, again using the
   latest ledger blob SHA. Update automation_worklist.json to DONE and
   the **same evidence URL**, again conditional on its blob SHA. **These
   are not an atomic two-file transaction.** If interrupted between them,
   the next scheduler must STOP on HOLD_SYNC and ask for reconciliation
   against GitHub history, not rerun the work.
6. If a task already says CLAIMED or DONE, do **not** perform it again.
   Existing CLAIMED with unknown outcome requires human examination.
   BLOCKED also stops the queue. Preserve all prior events.
7. Start the next ready task only after re-reading both files and
   confirming consistency against the actual GitHub branch.

### Offline reproducibility

The --output option creates a *new local file only*. It cannot push to
GitHub. The --ledger and --output paths must be different.

    python -m unittest -v tests.test_automation_ledger

    python -m foundry.automation_ledger \
      --ledger foundry/automation_ledger.json \
      --task-id FND-009C \
      --action CLAIM \
      --observed-sha <CURRENT_PR32_COMMIT_SHA> \
      --output /tmp/next-foundry-ledger.json

An offline CLAIM proposal **is not execution permission**. The scheduling
assistant must independently verify the GitHub HEAD and blob SHA and
use connected GitHub capabilities explicitly to store any authorized
draft-only changes. If no persistent per-blob conditional update is
available, stop instead of claiming durable idempotency.

### Trust and limitations

The hash chain detects accidental editing of an event or dropped prefix
*relative to a previously saved head*. Because both code and JSON live
in a mutable draft PR and main is not independently protected, anyone
able to rewrite the whole chain can forge it. SHA-256 is **not a signature**;
a commit URL is **not** evidence of Safety/Quality acceptance. The record
does not authenticate the worker, its commands, owner identity, GitHub CI
observations, or the correctness of an engineering change. CLAIMED,
DONE, CONSISTENT_ADVISORY and PASS never grant launch, GitHub write,
Docker, model invocation, merge or production privileges. P0 #21 and the
Foundry Launch Gate remain blocked.

In particular, a scheduled task configured to read/write GitHub is
**not a demonstrated independent trusted controller**. Its first real
unattended run and cross-run persistence remain to be observed. The
scheduler must not assume this description alone constitutes successful
autonomous execution.
