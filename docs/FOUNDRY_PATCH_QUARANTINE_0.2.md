# Foundry 0.2 — untrusted patch quarantine + container confinement policy

Status **RESEARCH / NOT CONFIGURED FOR UNTRUSTED EXECUTION**. Issue #31, draft PR #32. This is an incremental engineering step after the fixed offline Executor 0.1 demo and real read-only intake of GitHub Issue #31.

## What is actually implemented

- `foundry/patch_admission.py`: accept a small, strongly typed *text proposal* only for the checked-in synthetic `foundry/fixtures/calculator.py`. Bound the raw JSON input (16 KiB), UTF-8 candidate content (4096 bytes), canonical relative target path, issue #31, task kind `demo-add-v1`, exact checkout SHA, original file SHA256 and candidate SHA256. Deny extra JSON keys, path traversal, unapproved files, unexpected version, invalid encoding, symlinks, and unchanged proposals. Return an ordinary reviewable unified diff and its SHA256. **Do not write to the repository and never run the candidate.**
- `foundry/sandbox_policy.py`: return a deterministic Docker argument **plan** with pinned-image format, `--pull=never`, `--network=none`, read-only filesystem and bind mount, `--cap-drop=ALL`, no-new-privileges, unprivileged uid/gid, bounded memory, CPU and process count, no executable tmp and a hard-coded reviewed probe. It performs NO Docker call, image pull, attestation or OS sandbox execution.
- `tests/test_patch_admission.py` and `tests/test_sandbox_policy.py` attempt prompt/command/path injection, forged digests and SHAs, malicious but syntactically valid code, oversized JSON, missing fixtures, symbolic links and fake image tags. Successful quarantine is still untrusted data. Even when a syntactically pinned container plan can be produced, the flags `runtime_verified=false`, `container_started=false`, `candidate_executed=false`, `production_allowed=false` must remain false.
- PR's `.github/workflows/foundry-gate.yml` now exercises the two new modules using real GitHub Actions and checks the current checkout remains clean.

## Explicitly unverified / absent

**No real general-purpose AI coding model is connected.** No API key, account, provider, pricing, token budget or model execution is authorized. A separately approved budget and provider policy are needed before invoking any paid inference.

**No actual hardened sandbox has been demonstrated.** The Python Executor 0.1 still runs *only a fixed trusted synthetic test*. Python isolated mode `-I` is NOT an OS sandbox. Docker confinement flags in the policy are not proof that Docker is installed, that an image digest points to a safe local image, that the daemon is appropriately trusted, that network isolation was confirmed from inside the container, or that CPU/RSS/time/cgroup limits worked during execution. Do NOT run LLM output in the existing Python subprocess.

**No general code or actual OpDB Core patch is admitted.** The single demo allowlist is deliberately much narrower than a production agent. The synthetic proposal merely produces a diff for review. The read-only CI token cannot write branches, issues or PRs. No automatic merging, deployment, canary, staging or rollback. Launch Gate remains NOT_READY and no launch timestamp has been recorded.

## Next admission steps

1. Independent Safety/Quality review of the sandbox threat model and patch ingestion against adversarial filesystem, Python/network and Docker escape cases.
2. Provision and independently verify a pinned local container image, OS/cgroup isolation, no egress, limits, no Docker socket, no secrets and observable exit/timeout/cleanup semantics. The sandbox runner must fail closed if verification is absent.
3. Agree on a low-cost model provider and per-run hard spending/token caps before any request. Model text is always untrusted and must pass patch validation, never become shell commands.
4. Add a real task allowlist and exact-source-SHA workflow with independently authored tests; one draft branch/PR per issue, explicit Quality review; no automatic merge.
5. Roll forward only after P0 #21 and separate Core/Safety/Quality integration gates are satisfied for actual Lens admission. Full autonomous launch still requires explicit owner click on the green «Запустить» control and authoritative start-time receipt.

## Reproduce

    python -m unittest -v tests.test_patch_admission tests.test_sandbox_policy
    python -m unittest discover -s tests -p 'test_*.py' -v
    python -m foundry.sandbox_policy --fixture /absolute/path/to/checkout/foundry/fixtures

The final command without a pinned trusted local image must exit with BLOCKED. No command in this document launches the full autonomous engineering system.
