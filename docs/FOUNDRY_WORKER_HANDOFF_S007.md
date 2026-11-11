# Foundry S-007 / Controller–worker DATA contract 0.6

**Date:** 2026-11-08. **Status:** proven **offline/synthetic JSON data handoff only**. This is not a remote AI coder, authenticated IPC or independently attested controller/worker OS isolation. The big green owner "Запустить" button remains disabled; first-start time unset. All work belongs to existing DRAFT PR #32.

## Actual engineering steps

1. **Bound external GitHub Issue input:** `foundry/issue_intake.py` now reads a maximum of **32 KiB + 1 byte** before parsing. A valid-shaped Issue #31 JSON padded to 64 KiB must be rejected; a read-only GitHub token still cannot turn the issue body into commands.
2. **Bound original source reads:** `foundry/patch_admission.py` now reads at most **4096 + 1 bytes** of original source (previously `Path.read_bytes()` loaded an unknown-size file before checking limit). Existing 16 KiB input-proposal cap and 4096-byte candidate cap remain in effect.
3. **Introduce data-only handoff:** `foundry/worker_contract.py` has three explicit CLI phases:
   - `--prepare`: validate the pre-existing exact Issue #31 task against checked-out 40-hex SHA and `model_gate.offline_policy` (zero billed model requests, tokens and cost), emit a strictly typed **PROPOSE_TEXT_ONLY** request.
   - `--offline-mock`: produce exactly one fixed synthetic arithmetic text change using the reviewed fixture. It does not execute Python, call a model, contact the network or modify a checkout.
   - `--review`: accept bounded JSON reply as **untrusted data** and delegate to `patch_admission.admit`. Only a candidate diff and digest are returned, with `worker_reply_executed=false`, `model_invoked=false`, `github_write_allowed=false`, `production_allowed=false`, `launch_authorized=false`.
4. **Adversarial checks:** `tests/test_worker_contract.py` exercises injected fields, commands, fake release permission, changing path, wrong Issue/commit, missing fields, budgets, Boolean/int aliases, changed fixture bytes, duplicate JSON keys and oversized worker responses. Values must have **exact types**, because Python equality treats `True == 1` and `0 == False`.
5. **Real GitHub Issue → offline data handoff CI:** `.github/workflows/foundry-gate.yml` reads actual private GitHub Issue #31, prepares task data, emits an offline reply, validates SHA/path/review-only status, and attempts one response containing `"command":"deploy to production"`. The controller must reject that response and leave the working tree unchanged.

## Independent negative-control trace: RED → GREEN

| Scenario | Test-first failing evidence | Verified fix |
|---|---|---|
| Huge but valid-shaped Issue JSON and unbounded original source `read_bytes()` | SHA `3cbbc21043bb0cc8e1a630e788cd6a0bc902b555`, [Foundry RED CI #42489928647](https://github.com/mel2003ru-code/OpDB/actions/runs/42489928647), **two expected failures** | `foundry/issue_intake.py` at `4517e1e75431b0b48bbf9549ef6834ea7fe90776` and `foundry/patch_admission.py` at `9f464affe928c8209cf6e2abdb8197df33bb7ab2`, three workflows green on this code |
| JSON Boolean values impersonate numeric/Boolean fields | New protocol SHA `80bdc1db52e50004e3af2df4ef510ef469c13dc9`, [full RED CI #42490223656](https://github.com/mel2003ru-code/OpDB/actions/runs/42490223656), **four expected failed subtests** | Exact `type(value)` checks in the request validator, SHA `8a1213f0a39ed605dfeca156b2aa9f4fb85b39ac` |
| Lookalike checkout path and ambiguous duplicate JSON fields | SHA `3f9833fb3dbf785d18ebe908a51be58276cc0fc7`, [full RED CI #42490368703](https://github.com/mel2003ru-code/OpDB/actions/runs/42490368703), **two expected failures** | Canonical controller-owned checkout path, SHA256 of reviewed calculator source, and duplicate-key rejection, SHA `35a2d8cef84bbbb512db843fddf9768b055acb74` |

**Final integrated source SHA before this report:** `b7cc6f50714da4c0198ae9b74a5176d88cbc4853`.

- [Full repository CI #42490566362](https://github.com/mel2003ru-code/OpDB/actions/runs/42490566362): **237/237 PASS**.
- [Foundry gated preflight #42490566289](https://github.com/mel2003ru-code/OpDB/actions/runs/42490566289): **163/163 PASS**, actual private Issue API intake, offline request/reply/review and injected-command rejection.
- [Fixed Docker sandbox CI #42490566288](https://github.com/mel2003ru-code/OpDB/actions/runs/42490566288): **47/47 base sandbox policy tests + 16/16 runner tests PASS**, plus previously reviewed actual Docker positive/negative observations.

Check exact newer PR HEAD CI after this documentation commit before referring to it as final evidence.

## What remains BLOCKED

**This is a contract proof, not an independent security boundary.** The trusted-controller Python code and the synthetic worker code still come from the same modifiable PR checkout in GitHub Actions. A malicious PR author with workflow-writing power can edit fixture source, its SHA pins, tests, policy and GitHub workflow. The source hash proves *consistency* under the authored policy, not external trust, message origin or immunity to a compromised controller.

**A future general worker needs separate security authority**: protected controller code on an independently approved immutable revision, verified isolated no-secret/no-Docker-socket/no-network worker, host resource quotas (CPU, RSS, disk, output, time), bounded transport/message size, authenticated task provenance and replay/duplicate protection, no GitHub write capability in the guest, rejection of code modifications to CI/proofs and explicit external Safety/Quality approval. Even after isolated code execution, a worker's result should be rechecked against independent test oracles before an owner-reviewed draft PR.

The large research automation **"Запустить"** must stay disabled until actual external readiness and an explicit owner action. Never infer an official readiness percentage from the green test count. Neither OpDB Core nor Proof Gate is production ready. Core #33 requires stacked Quality #34 review/integration; Safety P0 #21 is OPEN and Lens admission must remain denied.

**Governance:** synthetic CI PASS never authorizes autonomous merge, GitHub write, AI provider spend, source Lens publication, staging/deployment or production operations. No start time exists.
