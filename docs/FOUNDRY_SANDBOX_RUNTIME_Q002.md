# Agent Foundry: bounded Docker runtime validation Q-Sandbox-002

- Date: 2026-11-08
- Status: **LIMITED OBSERVED synthetic isolation, NOT arbitrary-AI-code approval**
- Target: draft Foundry PR #32 / Issue #31
- Authoritative code under test: reviewed fixed probes bundled in `foundry/fixtures`; no model output was executed
- Deployment/main/merge/LLM spend: **NONE**
- Safety P0 #21: **OPEN**

## What changed

1. Added `foundry/sandbox_runner.py`: pins the same reviewed Docker Official Image digest already used by the existing Foundry Docker smoke workflow (`python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`). The driver does **not** pull images; it refuses missing local images.
2. The host-side Docker command uses an explicit minimal environment, fixed executable, one reviewed fixture bind mount read-only, no network, read-only guest root, non-root UID, cgroup CPU/RAM/PIDs limits, no new privileges, default seccomp and cap-drop-all via `sandbox_policy.plan`.
3. Added wall-clock timeout, stable container name and force-cleanup in `finally` after timeout or failure. Cleanup has defensive limits; host daemon/kernel crash conditions are not attested.
4. Added exactly defined JSON evidence contracts for the **11** confinement checks and **7** adversarial deny-operation checks. No accepting arbitrary output fields or claims of successful AI isolation.
5. Added `tests/test_sandbox_runner.py`: denial of unapproved probes, missing Docker/pinned image, forged evidence, falsified checks, Docker CLI exit and timeout, cleanup, no token inheritance, and review-only result.
6. Integrated driver tests and both **real Docker fixed-probe executions** into the pre-existing `.github/workflows/foundry-sandbox-smoke.yml` read-only job. An accidental duplicate Docker workflow was removed to avoid spending extra Actions minutes.

## Traceable RED / GREEN

**First attempt failed, not papered over:** `[CI 42486242262](https://github.com/mel2003ru-code/OpDB/actions/runs/42486242262)` on commit `77030908fa4d3932166427d469e9a0dc7d49ae7e` successfully pulled and ran the pinned image, and the confinement probe passed, but the driver incorrectly demanded nine checks from *every* probe. The adversarial probe legitimately had seven fixed checks and was incorrectly marked `BLOCKED`. This was a controller false-negative, not a Docker security failure.

**After correction and consolidation** at SHA `a845273fb6ae667d25be7f6da167783f7963a03e`:
- [Real fixed-probe Docker CI #42486498579](https://github.com/mel2003ru-code/OpDB/actions/runs/42486498579): **SUCCESS**. The fixed confinement and adversarial probes each returned `REVIEWED_PROBE_PASS`. Existing negative controls also detected deliberate removal of read-only root, network isolation, non-root user, memory limit, fake secret canary and relaxed seccomp.
- [Foundry gate CI #42486498608](https://github.com/mel2003ru-code/OpDB/actions/runs/42486498608): **143 tests PASS**.
- [Repository CI #42486498565](https://github.com/mel2003ru-code/OpDB/actions/runs/42486498565): **214 tests PASS**.
- The PR remains DRAFT; protected `main` remains unchanged. Verify later branch SHA before attributing these runs to newer commits.

## What this does **not** prove

- It is **NOT** a secure execution environment for hostile AI-generated code. The existing workflow checks out a branch and executes branch-authored Python on a runner that has a Docker daemon. A malicious PR author could change Python/test/workflow bytes; a fixed bind-mount path is not independent content attestation. True untrusted code needs a separate protected controller and physically separate no-secret worker.
- No real LLM is connected; `model_gate.py` still allows only zero-cost offline mock.
- Docker image SHA pinning protects reproducibility, not publisher provenance or independent image supply-chain certification. Host kernel compromise, escape attacks, cgroup accounting beyond observed probe cases, OCI trust, disk quotas and output flooding are not independently attested.
- Successful unit tests and synthetic guest observations do NOT prove Source-to-Lens trust, durable OpDB engine properties, production readiness or cross-DB benchmark superiority. P0 #21 is still open.
- No autonomous code change, PR publication, staging or deployment occurred. The big green owner launch button remains disabled, and no first launch timestamps exist.

## Next real automation milestone

Design and review **trusted-controller → untrusted worker** separation first: protected controller reads signed task identity and owns provider cost cap/keys, sends only bounded data to a disposable code-worker with no GitHub write credential, no host Docker socket, and no accessible project secrets. The worker returns a bounded patch artifact as untrusted DATA. A separately protected verifier validates source SHA, path allowlist, code/test changes, independent Quality, and only then may request a draft PR with narrowly scoped permissions. Even a clean CI run must not auto-merge, auto-activate Lens or deploy.
