# OpDB Foundry S-008 / fixed worker OS-boundary experiment (INCOMPLETE)

Date: 2026-11-08. All work is confined to existing draft PR #32.
Status: **S-008A experimental guest confinement observed; S-008 full trusted boundary NOT VERIFIED**.

## Security statement

The PR head controls `foundry/isolated_worker.py`, the reviewed fixture,
the SHA allowlist, tests and the PR-triggered workflow. On 2026-11-08 the GitHub
branch API returned `main.protected=false`. **No independently protected,
reviewed, immutable controller exists yet.** A PR CI PASS is self-tested
engineering evidence, NOT an authorization to execute AI-generated code.

The Docker *host* invokes a local Docker daemon, but the fixed guest has no
Docker socket or host credentials. The guest is **not given the token**,
production credentials, a checkout writable mount, external network or code
from an issue, model or PR comment. PR code on the host remains part of the
untrusted review surface; this must be corrected before expanding the executor.

## S-008A implementation

* `foundry/fixtures/handoff_worker.py`: standalone, deterministic, **fixed
  synthetic** data-only program. It reads the read-only reviewed
  `calculator.py` fixture, validates its SHA-256 and emits one JSON reply for
  the allowlisted Issue #31 task and exact checkout SHA. No shell commands, AI,
  arbitrary source, arbitrary filesystem paths, PR creation or candidate
  execution.
* `foundry/sandbox_policy.py`: only the SHA-pinned fixture is authorized;
  `--network=none`, `--read-only`, `--cap-drop=ALL`,
  `--security-opt=no-new-privileges`, `--user=65534:65534`,
  `--pids-limit=32`, `--cpus=0.5`, `--memory=128m`,
  `--memory-swap=128m`, `--tmpfs=/tmp:rw,noexec,nosuid,size=8m` and
  `--shm-size=8m`, and `--log-driver=none` (no Docker daemon-side
  log-file accumulation). No Docker socket mount. Immutable OCI image digest from
  the S-006 pinned-image policy, no implicit pull during execution.
* `foundry/isolated_worker.py`: bounded Docker CLI stdout/stderr (shared
  64 KiB through the existing driver), bounded wall-clock time (25 seconds),
  random container name, forced cleanup and post-cleanup absence check.
  The guest validates cgroups, non-root privileges, root/source read-only,
  network isolation, missing credentials/socket, seccomp, and both 8 MiB
  writable tmpfs ceilings. The host rejects missing, duplicated or forged
  JSON and revalidates with `worker_contract.review`. **Only
  `ISOLATED_REVIEW_ONLY` or a failure; never launch permission.**
* `tests/test_isolated_worker_s008.py`: seven test methods plus adversarial
  subcases for modified requests, invalid SHA/checkout, fake launch claim,
  failed guest, timeout, fake confinement flags, duplicated JSON, absent
  runtime and unverified cleanup.
* `.github/workflows/foundry-sandbox-smoke.yml`: real Docker execution of
  fixed guest and explicit negative control for a missing shared-memory cap,
  while keeping `contents: read`, no persistent checkout credentials, no
  production environment and no PR write API.

## Observed evidence (specific commits, not release claims)

* Test-first RED: commit `32f10a52d8744bd035df8eb163bc7dc9e92cc98f`,
  [full CI #42492047434](https://github.com/mel2003ru-code/OpDB/actions/runs/42492047434)
  failed because `foundry.isolated_worker` did not exist. Later GREEN cycles
  also exposed test harness mistakes, fixed in the branch before acceptance.
* Verified intermediate GREEN at commit
  `4c12d2de0f143ca50390d1943a248b5c4d806f78`:
  [full repository CI #42492584262](https://github.com/mel2003ru-code/OpDB/actions/runs/42492584262);
  [Foundry gate #42492584241](https://github.com/mel2003ru-code/OpDB/actions/runs/42492584241);
  [real Docker fixed handoff #42492584339](https://github.com/mel2003ru-code/OpDB/actions/runs/42492584339)
  completed successfully. Docker logs contain `S008_FIXED_GUEST_OBSERVED`
  and `independent trusted controller NOT ATTESTED`; the generated patch was
  quarantined for review, and the source checkout remained unmodified.
* Real negative control, exact SHA `e950767d83793c32e83d89581fb279d40fdc1cf5`,
  [Docker CI #42492813621](https://github.com/mel2003ru-code/OpDB/actions/runs/42492813621):
  a reviewed container intentionally run WITHOUT `--shm-size=8m` exited
  nonzero, with `shm_8m=false`, correct network isolation and confirmed
  cleanup. Logs include `EXPECTED_S008_NEGATIVE`. At this SHA,
  [full CI #42492813694](https://github.com/mel2003ru-code/OpDB/actions/runs/42492813694)
  ran 244/244 PASS and
  [Foundry Gate #42492813592](https://github.com/mel2003ru-code/OpDB/actions/runs/42492813592)
  ran 163/163 PASS.
* Final code hardening at `8841c14614f1cd6dc6d3e657e26629ac41649d12`
  additionally disables Docker daemon logging while preserving bounded
  stdout/stderr for the controller.
  [Full CI #42493053102](https://github.com/mel2003ru-code/OpDB/actions/runs/42493053102),
  [Foundry Gate #42493053075](https://github.com/mel2003ru-code/OpDB/actions/runs/42493053075)
  and [real Docker CI #42493053098](https://github.com/mel2003ru-code/OpDB/actions/runs/42493053098)
  all completed successfully. This is still evidence from a PR-controlled
  workflow, not independent Safety/Quality authorization.

## Mandatory blockers / S-008B

1. Establish a **separately controlled, independently reviewed and protected**
   controller at a stable immutable SHA, running outside any candidate PR
   checkout. Set reviewed branch/ruleset protections and audit who can alter
   workflow files or trusted code. No attestation solely from branch-local
   hashes, self-authored tests, run metadata or CI summaries.
2. Separate the controller and guest using distinct principals/runner trust
   domains. Authenticate and bind the task, source SHA, allowed files, budget,
   nonce/one-time use and worker artifacts to the trusted controller. Prove
   replay and tampering resistance and enforce zero secrets and zero GitHub
   privileges in the guest at an **independent** boundary.
3. Independent Safety and Quality reviewers must reproduce resource escapes,
   secret and Docker-socket probes, bad output, timeouts, cleanup failures,
   tampered handoff JSON, forged checks, workflow replacement and image
   substitution. Record exact SHA, job logs and signed or protected provenance.
4. Only after independent approval consider **a separate experiment** with
   truly untrusted worker code. Existing sandbox must never be reused for
   arbitrary generated code on the strength of this fixed-fixture proof.
5. Core #33 still depends on separately reviewing stacked Quality #34.
   P0 Issue #21 remains OPEN and all Lens admission remains Source-only.
   No automatic PR merge, GitHub write, paid inference, staging, production
   deployment, launch enablement or first-start timestamp.

The owner's large green **«Запустить»** button remains **DISABLED**.
