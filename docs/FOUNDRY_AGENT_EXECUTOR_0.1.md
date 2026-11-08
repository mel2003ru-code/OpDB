# Agent Executor 0.1 — bounded OFFLINE RED→PATCH→GREEN demo

**Status:** isolated prototype only; it is **not an LLM coder** and it **does not make PRs**. Tracking: [Issue #31](https://github.com/mel2003ru-code/OpDB/issues/31), draft [Foundry PR #32](https://github.com/mel2003ru-code/OpDB/pull/32). Safety P0 #21 still blocks Lens; launch button remains disabled.

## Implemented and observable

This standard-library Python worker receives a strictly allowlisted synthetic work item, bound to the exact checked-out commit SHA. One fixed demonstration issue number (**31**) and one task kind (**demo-add-v1**) are permitted. A reviewed, intentionally incorrect arithmetic fixture exists in `foundry/fixtures/calculator.py`; an independently checked fixture oracle is `foundry/fixtures/quality_probe.py`.

A single run:
1. Validates exact task JSON field names, types, SHA, issue and kind. Rejects task-supplied commands, paths, patches, prompts, model URLs and extra fields. Exactly one patch attempt; 2–12-second monotonic execution budget.
2. Copies the **fixed checked-in fixture** to a new system temporary directory. The original checkout stays untouched. The test subprocess uses an absolute Python interpreter in isolated mode, no shell, only a fixed test file, limited inherited environment and a strict timeout.
3. Runs the initial test and demands **RED**. Baseline green means `NEEDS_INVESTIGATION`, not a successful change.
4. Applies exactly one hard-coded replacement in the scratch directory, re-runs the test and demands **GREEN**.
5. Prints a deterministic unified diff, its SHA256 and an explicit review-only decision. It does not write to tracked files, create a git branch, submit a PR, contact any model, merge, deploy, or enable the Launch Gate.

The structured report `DRAFT_PROPOSAL_READY` only means the fixed **synthetic** exercise passed. No model, open-ended agent, issue API, GitHub write, general patch intake or release action is attached.

## Reproduce

    python -m unittest -v tests.test_agent_executor
    python -m foundry.agent_executor --expected-sha "<40-hex-git-commit>" --demo-task --output executor-demo.json
    python -m foundry.agent_executor --expected-sha "<40-hex-git-commit>" --output executor-not-configured.json

The first command exercises unauthorized fields, SHA mismatch, budget tampering, synthetic negative control, patch failure, timeout and repository immutability. The second runs the sandbox demonstration, and the third returns `NOT_CONFIGURED` without executing a task. GitHub PR CI supplies its actual checkout SHA as `GITHUB_SHA`; all permissions are read-only.


## Real GitHub Issue intake (read-only integration)

In addition to the fixed offline demonstration, `foundry/issue_intake.py` verifies the **real private repository Issue #31** response obtained by `gh api repos/mel2003ru-code/OpDB/issues/31` in the GitHub Actions workflow. The workflow token grants `contents:read` and `issues:read` ONLY, and the token exists only in the GitHub API retrieval step environment.

The validator requires exact issue number, canonical GitHub issue URL, repository API URL, an open state and the exact checked-out SHA. Issue title/body/embedded instructions are **never** interpreted as code; they cannot alter task type, file path, attempts or budget. It produces the same narrowly predefined synthetic `demo-add-v1` task envelope. The executor then validates this envelope again before any subprocess, performs the scratch-only RED → one fixed patch → GREEN proof, and leaves the source checkout unmodified.

If GitHub API access fails, Issue #31 is closed, response URLs mismatch, inputs are malformed or a PR is presented instead of an Issue, the pipeline must fail closed. This is **real issue intake metadata**, not a general authorization to repair the user-authored issue text or to open PRs automatically. The current implementation uses no LLM and does not have GitHub write permissions.

The new tests `tests/test_issue_intake.py` cover prompt-injection fields, wrong issue, forged URLs/repository, wrong SHA, malformed data and CLI end-to-end intake. The PR workflow also fetches the actual private Issue #31 rather than relying only on mocks, contingent on repository API permissions.

## Trust boundaries, not promises

- Task JSON is only a **reviewed task envelope**, never a free-form instruction to run shell/SSH, access prod, fetch model weights, or modify a repository.
- The absolute source fixture paths cannot be chosen from task input. The public Python test helper may supply a synthetic temporary fixture directory, not exposed by the CLI. The fixture code is trusted and checked into this PR; this is **not a secure sandbox for adversarial arbitrary generated code**. Python `-I` is interpreter isolation only; GitHub runner is a normal VM with possible network, not a network-denied container, system call filter or OS security boundary.
- Any future model-generated patch must run in an independent, network-restricted disposable environment with filesystem path restrictions, secret-free credentials, CPU/RAM/time/patch-size and model-token limits, reviewable provenance and separate Quality/Safety validation.
- A future GitHub PR publishing step needs its **own narrowly scoped permission**, an allowed branch prefix, idempotent issue+SHA token, immutable evidence, human reviewers and duplicate-PR protection. None of those rights are granted in phase 0.1.
- Model provider, billing limits, repository author permissions, staging/deploy target, observability and rollback remain unconfigured. Do not claim full closed-loop autonomy or the world's best DBMS.

## Promotion path

1. **0.1 (this PR):** Proven synthetic task intake → isolated demo diff → failure/success feedback, no GitHub write. Validate real CI and deny cases.
2. **0.2:** A genuine constrained research task on a disposable copy of a real source file, with a separate untrusted patch admission layer (untrusted code MUST be isolated with OS-level resource and network limits).
3. **0.3:** Optional language model adapter with strict spending cap, secret-free compartment, no broad network or filesystem access, verifiable inputs/outputs.
4. **0.4:** GitHub draft-PR creation from approved safe changes only; branch guard, no direct main writes, no merges, Human/Safety/Quality gate.
5. **Later:** autonomous research orchestration, verified reproducible benchmarks, staging/recovery rehearsals and explicit owner-approved first launch. The large green `Запустить` button remains disabled until trusted readiness.

**Evidence policy:** this synthetic executor success never changes `production_allowed=false`, `automatic_merge_allowed=false`, `launch_authorized=false`. The launch timestamp remains unset.
