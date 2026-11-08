# OpDB Foundry — S-004 fixed denied-operation adversarial sandbox probe

**Date:** 2026-11-08. **Verdict:** PASS for one **fixed, reviewed synthetic** guest on one disposable GitHub Actions Docker runner; **NOT VERIFIED for arbitrary generated code, independent host security, or production.** Core Safety P0 #21 remains OPEN. The owner's full Foundry green `Запустить` button stays disabled; no actual launch timestamp.

## What changed

- `foundry/fixtures/sandbox_adversarial_probe.py` is a *pre-reviewed fixture*, not a model-generated patch. It attempts harmless file creation under `/etc/__opdb_disposable_probe` and `/work/__opdb_disposable_probe`, removes a created file if a guard unexpectedly fails, checks absent Docker socket paths and a small set of secret-related **environment variable names only**, reads seccomp status and repeats the 11 baseline confinement observations. It never prints environment variable values or attempts outbound network connections.
- `foundry/sandbox_policy.py` admits a third **fixed** reviewed probe name (`adversarial`) only; the image remains pinned to `python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`, network none, read-only root/mount, non-root, no capabilities, no new privileges, bounded cgroup, no automatic image pull when running.
- `foundry/sandbox_adversarial.py` refuses to start the fixed probe if the baseline sandbox has not passed, verifies exact guest fields and checked-in fixture hashes, and runs two **separate disposable negative controls**: injection of a `GITHUB_TOKEN=FAKE_CANARY_FOR_NEGATIVE_TEST_ONLY` variable and a temporary `seccomp=unconfined` setting. The checked-in guest must report precisely the disabled protection in each trial and exit nonzero. **No real token or GitHub credential enters the container.**
- `tests/test_sandbox_adversarial.py` adds 10 synthetic tests for policy whitelist, checked reports, missing/forged evidence, timeouts, canary and seccomp tampering. These unit tests use mocks and cannot independently prove OS confinement.
- `.github/workflows/foundry-sandbox-smoke.yml` runs the real fixed probe and negative controls on the same disposable GitHub-hosted runner with read-only repository permissions and no persisted checkout credentials.

## Exact reproducible evidence

- **Implementation PR head tested:** `7e887a3387c7bde4945ad74f477bb467b9059f46` in [draft PR #32](https://github.com/mel2003ru-code/OpDB/pull/32). GitHub's PR synthetic merge checkout was `0b66f5daf000599c335723fe7b8fef172811ca2f`, explicitly distinct from the source branch commit.
- [Real sandbox run #42484652896](https://github.com/mel2003ru-code/OpDB/actions/runs/42484652896): **PASS**, 44/44 targeted unit cases; positive fixed container confinement 11/11; original network/UID/memory/read-only negative controls still pass; new denied-operation probe observed 7/7 expected protections and both fake-secret and disabled-seccomp controls returned the expected nonzero results. The log contains `FIXED_DENIALS_OBSERVED` and `EXPECTED_FIXED_DENIALS: fake-secret and disabled-seccomp detected`.
- [Full repo CI #42484653227](https://github.com/mel2003ru-code/OpDB/actions/runs/42484653227): **186/186 PASS**.
- [Foundry gated preflight #42484653053](https://github.com/mel2003ru-code/OpDB/actions/runs/42484653053): **129/129 PASS**; release/launch still locked.
- GitHub Actions upload-artifact quota remains exhausted as previously recorded in S-003. The fixed/synthetic evidence JSON is printed in Actions logs, which have finite retention; GitHub run links, exact source SHA and this report preserve traceability but are **not immutable third-party attestations**.

## What the result DOES and DOES NOT show

**Observed:** this Docker guest, with these exact approved settings, could not create files under the two tested paths, did not see the Docker daemon socket at standard paths, did not inherit the handful of named GitHub/cloud secrets tested, ran with a seccomp filter, and detected the deliberately fake token and deliberately disabled filter. The fixed baseline confinement checks also passed.

**Not proven:** that no secret can be present under *another* name or path; no host mount beyond audited paths; no kernel/container escape is possible; supply-chain safety of the pinned base image; correct isolation under every Docker daemon; no side channels, DNS/IPv6 bypass or exfiltration by arbitrary malicious code; accurate accounting of untrusted stdout, RAM, CPU, disk and time for adversarial code; no escalation through host-controlled runners or GitHub workflow editing. This test intentionally executes only reviewed synthetic Python. **Do not run model-generated or untrusted arbitrary code in this implementation.** Formal independent Safety/Quality review remains outstanding.

## Next gates before the big button can be enabled

1. Independent threat-model review of privileged host Docker daemon, GitHub workflow permissions and fixture integrity, and verification of an isolated untrusted-code runtime without mounted credentials, network, daemon socket or bypassable CPU/memory/time limits.
2. A source-locked, cost-capped AI model adapter with API token and spending restrictions approved separately; only an allowlisted real issue/task and reviewable diff.
3. An authenticated, idempotent **draft-PR-only** publisher with human Safety/Quality approval, and no direct main write/merge.
4. Complete Core/Safety/Quality integration, P0 trusted capture, reproducible benchmarks, staging/rollback and trusted Launch Gate readiness; request an explicit owner click on the large green `Запустить` before full automation. Record the real request and confirmed start timestamps separately, never during tests.

**No automatic merge, model execution, production deployment or full Foundry launch occurred in S-004.**
