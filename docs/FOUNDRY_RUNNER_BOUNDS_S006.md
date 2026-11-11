# OpDB Foundry S-006 — bounded Docker output and verified cleanup

**Date:** 2026-11-08. **Status:** limited engineering red→green result for a **fixed, reviewed synthetic Docker probe**; **not** an independently approved executor for untrusted AI code.

## Motivation and independent negative controls

In draft PR #32, `foundry/sandbox_runner.py` previously called `subprocess.run(..., capture_output=True)` for Docker commands, so an unexpectedly noisy process could accumulate unrestricted stdout/stderr in the host Python process. In a separate issue, the runner attempted `docker rm -f` after a test but ignored a cleanup failure/timeout. It could then return a successful report without verifying that the container had stopped.

Three test-first adversarial cases reproduce the issues on the real runner:

1. A fixed benign Python process emits 128 KiB to stdout; the old runner accepted that unlimited output.
2. A mocked Docker container returns valid proof, but `docker rm -f` returns an error; the old runner still reported success.
3. Same valid guest proof, but Docker cleanup times out; the old runner still reported success.

**RED evidence:** tests-only SHA `94cca08f5e0cc6f27521f260126985f1863ef3d8`, [sandbox CI run #42489059076](https://github.com/mel2003ru-code/OpDB/actions/runs/42489059076) **FAIL with exactly three negative-control failures** (`tests.test_sandbox_runner`). This is expected baseline falsification, not a release failure to be concealed.

## Implementation

- `_run` in `foundry/sandbox_runner.py` now streams stdout and stderr from a host subprocess using `subprocess.Popen` and `selectors`, in fixed 4096-byte chunks, enforcing **64 KiB total combined captured output**. On overflow, it fails closed and terminates the CLI process group. It supplies a tightly restricted environment, no stdin and no shell.
- The timeout uses a monotonic deadline across output consumption and process exit. On timeout, the host CLI process group is killed; no successful proof is emitted.
- After any attempted guest run, the host first attempts `docker rm -f opdb-synthetic-smoke` and **checks absence** with a separate `docker ps -a --format '{{.Names}}' --filter 'name=^/opdb-synthetic-smoke$'` request. This allows the expected `--rm` auto-removal while requiring a successful Docker query showing that the named guest is absent. If the Docker API is unavailable, reports a matching container, or times out, the runner returns `BLOCKED`. This is stronger than silently ignoring cleanup failures.
- Existing tests were updated for the additional cleanup confirmation. All tests still prohibit execution of model output, broad Docker commands, unknown probes, GitHub write, auto-merge and production.

**GREEN evidence:** implementation change SHA `95a57e90f531a1991d9ca24b89d32f1b56fcbf4c`, tests adjusted at SHA `2741114c9fa7b3c691822eb9c49e62461447e702`:
- [Full repository CI #42489326558](https://github.com/mel2003ru-code/OpDB/actions/runs/42489326558): **218/218 PASS**.
- [Fixed Docker sandbox CI #42489326578](https://github.com/mel2003ru-code/OpDB/actions/runs/42489326578): **47/47 sandbox policy tests**, **16/16 runner tests**, and the real approved Docker probes plus negative guards **PASS**.
- [Foundry preflight CI #42489326727](https://github.com/mel2003ru-code/OpDB/actions/runs/42489326727): **144/144 PASS**.

## Explicitly unverified and remaining risks

This is **not a hard guarantee of bounded total host RAM or all Docker daemon descendants**. The 64 KiB budget applies only to Python's combined stdout/stderr capture of each invoked Docker CLI, not to Docker daemon logs, kernel allocations, cgroup memory, parent process startup, child programs that escape the process group, disk usage or direct host network egress. `docker ps` is one snapshot from a trusted daemon, not proof against daemon compromise or malicious races. A failed cleanup query correctly blocks this operation, but a crashed/inaccessible daemon might still leave a container for administrative cleanup.

The current Actions job still runs branch-owned Python on a Docker-enabled host. Path and SHA-256 checks under the same PR are **not independent trust anchors** if an attacker can edit the branch controller. Do not execute arbitrary model-generated code in this setup, allow shell commands from Issues, or grant GitHub write credentials.

**Next gates:** independent protected-controller/worker split, externally reviewed trust root for admitted code, OS-level no-network/no-secrets/no-host-Docker isolation and bounded host/guest CPU/RSS/disk/time, safe output/input artifact ceilings, model spending policy with explicit owner budget, draft-PR-only publish workflow and separate Safety/Quality review. P0 #21 and Verified Lens source capture remain unresolved.

**Governance:** draft PR #32 only, no main merge, no production, no paid model calls, no owner launch click or first-start timestamp. The big green `Запустить` control stays disabled.
