# OpDB Foundry — Safety Audit 0.5 and PR #32/#33/#34 review

**Date: 2026-11-08. Status: SCOPE-LIMITED ENGINEERING REVIEW, NOT independent external Safety/Quality sign-off.** All PRs remain DRAFT; no merge, deployment, model billing, untrusted AI-code execution or full launch.

## Review of the three PRs

| PR | Finding | Review disposition |
|---|---|---|
| [#32](https://github.com/mel2003ru-code/OpDB/pull/32) | Foundry preflight, fixed Docker trials, agent demo, patch quarantine. Its workflow runs PR-supplied Python on a Docker-enabled CI host. No protected-controller boundary for hostile PR authors. | CHANGES REQUIRED before permitting generated code |
| [#33](https://github.com/mel2003ru-code/OpDB/pull/33) | Source-only Python+SQLite TruthStore, 43/43 targeted Core tests on the last reviewed head. P0 #21 prevents admitting any Lens; fix from #34 is NOT yet in this branch. | LIMITED SOURCE-ONLY PROTOTYPE, not approved for verified Lens or production |
| [#34](https://github.com/mel2003ru-code/OpDB/pull/34) | Quality's stacked resource-control patch on top of #33, 9/9 adversarial tests and 77/77 full tests on its last reviewed head. Logical caps do not ensure bounded Python RSS or hostile-reader CPU time. | NARROW QUALITY TEST PASS, pending review and integration into #33 |

The GitHub mergeable flag and green CI are not independent release approval. PR #34 targets the Core branch of #33, not main. Never merge #33 independently of the pending #34 assessment.

## Reproduced code-execution trust defect in PR #32

**Root cause:** sandbox_policy.plan previously admitted any absolute non-symlink folder with the expected file names, and sandbox_smoke forwarded this caller-supplied fixture to a Docker bind mount. An attacker-supplied lookalike directory could therefore supply executable Python to an interface advertised as allowing only reviewed fixtures.

**RED:** Two new tests were committed first, covering three accepted lookalike probe directories plus one unexpected Docker invocation. [CI #42485397751](https://github.com/mel2003ru-code/OpDB/actions/runs/42485397751), source SHA 1cd66713f71d9652adad82b1b459d6b18f732b44: **4 failing test cases**, expected falsification.

**FIX:** Only the exact bundled fixture directory derived from the running module may be mounted by the policy. The policy rejects another path before accessing Docker. The fix is SHA 0a217a7d61c7c56722aaf4690428655790d9d5b3. [Full CI #42485476088](https://github.com/mel2003ru-code/OpDB/actions/runs/42485476088) 188/188 PASS; [Foundry #42485476111](https://github.com/mel2003ru-code/OpDB/actions/runs/42485476111) 130/130 PASS; [actual Docker #42485476334](https://github.com/mel2003ru-code/OpDB/actions/runs/42485476334) 46/46 Sandbox tests plus real fixed Docker checks PASS.

**Remaining limitation:** a fixed path is not trusted **content** attestation. Malicious PR changes could modify the reviewed fixture, tests or workflow in the branch itself. Branch-authored code running on a GitHub runner with Docker daemon access cannot be treated as an isolation boundary against a malicious PR author. Use a separately protected control plane and a no-secret, no-Docker-socket worker before any untrusted model code.

## Zero-cost model admission gate: Agent Brain 0.1

Module foundry/model_gate.py strictly admits only fixed synthetic task Issue #31, checkout SHA, and offline_mock with max_model_requests=0, max_total_tokens=0, max_cost_micro_usd=0. All non-mock providers, remote mode, fake owner approval and positive billing/token limits are BLOCKED. This module has no provider API implementation, no inference, no GitHub write, no code execution.

Unit tests in tests/test_model_gate.py cover malformed or injected policy, task/SHA mismatch, Boolean budget bypass, remote providers and zero-cost denial flags. Initial new CI at SHA 7a0a8cd04fa71f8fddeca745f79fcd6f50316ae3: [full #42485876618](https://github.com/mel2003ru-code/OpDB/actions/runs/42485876618) **201/201 PASS**, [Foundry #42485876759](https://github.com/mel2003ru-code/OpDB/actions/runs/42485876759) **143/143 PASS**, [real Docker #42485876902](https://github.com/mel2003ru-code/OpDB/actions/runs/42485876902) **46/46 Sandbox + real fixed probes PASS**.

**No model provider is connected or paid.** This is a policy boundary scaffold, NOT real cost enforcement for a future API client. It must remain separate from any future untrusted model output execution.

## Remaining non-negotiable blockers

1. Run all untrusted PR/generated code in an OS-isolated worker with a trusted controller, no host Docker daemon/socket, no secrets or write token and independently verified guest image integrity. The present code still executes branch-supplied Python on Docker-enabled CI, which is only acceptable for reviewed code.
2. Docker subprocess timeout bounds the host CLI wait but does not prove daemon child cleanup. Captured stdout/stderr has no measured byte limit. Need reliable guest cleanup, disk/CPU/RSS/output caps and hostile-fault injection, not just positive fixed probes.
3. Real model provider selection, pricing, approval, per-request token/cost enforcement, secret isolation and kill switches are all NOT CONFIGURED; do not spend money automatically.
4. Merge or manually reconcile #34 into #33 only after independent review, then test the combined exact SHA and resolve Safety P0 [#21](https://github.com/mel2003ru-code/OpDB/issues/21) before derivative Lens activation. True Core/Safety/Quality contract integration remains incomplete.
5. Staging, rollback, independent peer performance benchmarks, real secure release controller and human authorization remain unverified. The big green Start button must remain disabled. A first-start timestamp must NOT be recorded before the real owner click and confirmed start.

## Governance

This technical review is from the same assistant-mediated workflow and must **not** count as an external independent sign-off. Next: review #34 → #33, separately review #32, then build and adversarially test a genuinely isolated worker. No main merge or production deployment has occurred.


## Follow-up audit S-005 — reviewed-file bytes, not just directory identity

The S-004 finding closed the **external lookalike folder** bypass, but a separate
path-identity limitation was reproduced: when a directory has already been
accepted as `_REVIEWED_FIXTURE`, altering an executable fixture inside it was
not detected by `sandbox_policy.plan`.

- **RED, test first:** test commit
  `3a22342ff5ebd7beecaa26469bbef85d2ebbe095`, [Sandbox run #42487643863](https://github.com/mel2003ru-code/OpDB/actions/runs/42487643863),
  with **two expected subtest failures** for `confinement` and `adversarial`.
  The test uses a disposable directory and temporarily substitutes the policy's
  reviewed root to demonstrate that matching the directory alone is insufficient.
- **Fix:** exact reviewed fixture content is now pinned via four explicit SHA-256
  digests in `foundry/sandbox_policy.py`, with bounded reads and rejection of
  mismatched or oversized bytes, *before* returning a Docker execution plan.
  A new source edit must update both file content and manifest in a reviewable PR.
- **Verified commit:** `4292f2a497b68ba93db51e457b53ab7a188412ff`,
  [Sandbox CI #42487792183](https://github.com/mel2003ru-code/OpDB/actions/runs/42487792183)
  **47/47 unit PASS plus real fixed Docker positive/negative controls PASS**,
  [full CI #42487792375](https://github.com/mel2003ru-code/OpDB/actions/runs/42487792375)
  **215/215 PASS**, and
  [Foundry gate #42487792203](https://github.com/mel2003ru-code/OpDB/actions/runs/42487792203)
  **144/144 PASS**.

**Residual trust boundary:** The digest values are also stored in the PR's
modifiable source files. This is a consistency check against unreviewed fixture
changes, *not* an independent attestation. A malicious PR author who controls
the policy module can change both the fixtures and their hashes. Branch-authored
code is still executed on a Docker-enabled GitHub Actions runner; a separate
protected controller and an independently restricted worker are REQUIRED for
untrusted model-generated code.

## Consolidated PR review disposition at S-005

| PR | Evidence reviewed | Merge / safety verdict |
|---|---|---|
| #32 | CI on fixed SHA `4292f2a...`: 215 repository tests, 47 sandbox tests and real reviewed Docker probes PASS. Research policy, zero-cost offline Agent Brain, strict fixture SHA-256. | **CHANGES REQUIRED** for hostile-code support. Branch code is still not an independently trusted controller; no code execution approval, autonomous model, merge or production. |
| #33 | Exact SHA `14ad0415...`, [Core CI #42478875799](https://github.com/mel2003ru-code/OpDB/actions/runs/42478875799): 43/43 targeted and 68/68 repository tests PASS. | **SOURCE_ONLY RESEARCH PASS** within the tested scope; **NOT READY TO MERGE** without review/integration of #34 and P0 #21 Safety. |
| #34 | Stacked on #33, exact SHA `30f9ca7...`, [Quality CI #42479902129](https://github.com/mel2003ru-code/OpDB/actions/runs/42479902129): 9/9 resource tests and 77/77 full suite PASS. | **NARROW ADVERSARIAL QA PASS**, separate formal independent review and clean integration into #33 required. No Lens admission or production approval. |

This is an assistant-performed engineering review, **not a separate human or
independent external audit**. Green GitHub checks are verified observations of
these tests at specified SHAs, not a blanket release approval. Do not merge PRs
#32/#33/#34 into `main` or start the full Foundry based on this review.

**Integration order:** review and reconcile stacked #34 with #33; run combined
Core+Quality tests on the exact integrated SHA; independently review #32's
protected-controller boundary; keep P0 #21 open until trusted capture is
genuinely verified; then stage and rehearse recovery and launch authorization.
No first-launch date or success timestamp exists.
