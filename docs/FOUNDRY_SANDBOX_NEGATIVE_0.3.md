# OpDB Foundry — Sandbox evidence S-003: real negative controls

**Date:** 2026-11-08. **Status:** independent, reproducible engineering checks for ONE reviewed synthetic Docker probe. **NOT** certification for executing model-produced code. Owner's full autonomous `Запустить` button remains DISABLED.

References: draft [Foundry PR #32](https://github.com/mel2003ru-code/OpDB/pull/32), [Issue #31](https://github.com/mel2003ru-code/OpDB/issues/31), [P0 #21](https://github.com/mel2003ru-code/OpDB/issues/21), [Sandbox policy 0.2](FOUNDRY_PATCH_QUARANTINE_0.2.md).

## Reproducible positive evidence

- A fixed pre-reviewed `foundry/fixtures/sandbox_runtime_probe.py` runs inside Linux Docker on a disposable GitHub-hosted Ubuntu 24.04 runner.
- The container's image is fixed by an OCI manifest SHA256, `python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`. This reproducibility pin is **not** independent provenance or vulnerability review of the image.
- Observed 11 true in-container checks: non-root uid, read-only root and work bind mount, noexec tmp, only loopback network device, no external TCP, cgroup memory 128 MiB, PID count 32, CPU quota 0.5, no-new-privileges, and zero effective capabilities.
- Positive observation is `OBSERVED_FIXED_PROBE_PASS`; it always states `untrusted_model_code_allowed=false`, `candidate_executed=false`, `production_allowed=false`, `launch_authorized=false`. JSON evidence is a diagnostic report from a guest we have not independently attested; CI source, runner and event SHA must also be checked.

## Four negative controls (actually executed on CI)

For each test the only executed guest is the same reviewed probe. We deliberately remove a security guard from a fresh, bounded and disposable container. A **PASS** means the guest probe returned a nonzero exit and the particular expected guard was observed false, not that the unsafe configuration was authorized.

1. `--read-only` removed; guest reports `root_filesystem_read_only=false`.
2. `--network=none` removed; guest reports `network_only_loopback=false`. When a non-loopback interface appears, the guest does NOT initiate any external network traffic; it fails closed and marks outbound protection false.
3. `--user=65534:65534` removed; guest reports `non_root_uid=false`. Other defense flags stay in place.
4. `--memory=128m` **and** `--memory-swap=128m` removed as ONE logical memory-policy negative; guest reports `cgroup_memory_128m=false`. Docker cannot start a container with standalone `--memory-swap` and no `--memory`; such an invalid-command failure is **not** evidence that the guest detected missing memory isolation.

## Scientific negative trace / red-to-green

- [First extended-control run #42483489105](https://github.com/mel2003ru-code/OpDB/actions/runs/42483489105): **FAIL / NOT VERIFIED** because a Docker negative scenario emitted no JSON, despite earlier fixed positive controls. Do not report this as successful detection.
- [Diagnostic run #42483579855](https://github.com/mel2003ru-code/OpDB/actions/runs/42483579855): **FAIL** identifies `memory: guest report absent/malformed, docker exit 125`, i.e. invalid Docker arguments, NOT observed loss of memory isolation.
- Updated `foundry/sandbox_negative.py` to remove both memory/swap flags in the intentional memory experiment, and `foundry/fixtures/sandbox_runtime_probe.py` to avoid external network requests when the network-negative control enables a non-loopback interface.
- [Actual fixed-control CI #42483669415](https://github.com/mel2003ru-code/OpDB/actions/runs/42483669415) on SHA `d53c5eb671181b15076bbdb6f9cff7f602149909`: positive 11/11, original root read-only negative, **three new negative controls** network/UID/memory all detected by the real guest. Unit tests 34/34. [Full repository CI #42483669461](https://github.com/mel2003ru-code/OpDB/actions/runs/42483669461): 176/176 PASS; [Foundry CI #42483669479](https://github.com/mel2003ru-code/OpDB/actions/runs/42483669479): 129/129 PASS.
- The workflow **attempted** to upload JSON evidence artifacts named with exact `github.sha`, but [CI run #42483793603](https://github.com/mel2003ru-code/OpDB/actions/runs/42483793603) failed at `actions/upload-artifact`: GitHub Actions reported **Artifact storage quota has been hit**. The actual container positive and negative tests had already passed in that run; **do not claim artifact upload succeeded**. To avoid quota expenditure, the workflow now prints these two small, synthetic JSON evidence reports with exact `GITHUB_SHA` into GitHub Actions run logs. Log retention and deletion policies still apply: these logs are **not permanent or independently immutable**. The durable research narrative and run links live in this repository and Issue #31. New exact-SHA CI runs after this change must pass before considering the milestone complete.

## Fail-closed policy and restrictions

The fixed probe runs with `--network=none --read-only --cap-drop=ALL --security-opt=no-new-privileges --pids-limit=32 --memory=128m --memory-swap=128m --cpus=0.5 --user=65534:65534`, read-only bind mount, and a writable noexec tmpfs. Docker image pull is pinned to exact SHA before execution, and the run uses `--pull=never`. GitHub workflow token is `contents:read`; checkout does not preserve credentials.

This tests observed configuration on one ephemeral GitHub-hosted Docker daemon, not resistance to hostile guest code, kernel escapes, malicious supply-chain artifacts, daemon compromise, build-time exploitation, Docker socket exposure in other workflows, guaranteed all-egress isolation under every host environment, or adversarial PR authors modifying the test itself. The GitHub PR workflow runs branch code and therefore is **not a security boundary against malicious project maintainers**. An accountable independent Safety/Quality reviewer must inspect these limitations.

**NOT VERIFIED:** independent OS security attestation for executing untrusted model patches, per-model price/token limits, secure GitHub draft-PR write mechanism, original Core/Safety/Quality integration, protected capture (P0 #21), independent benchmarks, staging/rollback, and production launch.

## Commands / next task

- `python -m unittest -v tests.test_sandbox_policy tests.test_sandbox_smoke tests.test_sandbox_negative`
- `python -m unittest discover -s tests -p 'test_*.py' -v`
- Actual Docker evidence: inspect `.github/workflows/foundry-sandbox-smoke.yml`, CI logs and downloadable JSON evidence from an exact SHA run. Do not run on real data or send secrets into the container.

**Next milestone:** independent review of the sandbox trust boundary and a **separate restricted worker** with verified no-egress, permission isolation, cgroup controls and enforceable wall-clock limits before allowing any model-produced code, followed by audited cost-limited model integration and human-reviewed draft PRs. No merge, production deployment, native engine claims, or first launch time was authorized.
