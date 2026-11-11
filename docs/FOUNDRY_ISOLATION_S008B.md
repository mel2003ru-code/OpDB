# OpDB Foundry S-008B-1 — bounded handoff freshness (PARTIAL)

Date: 2026-11-08. Branch: `foundry/guarded-loop-gate-0-1`, existing **DRAFT PR #32**.
Security verdict: **limited session-binding proof PASS; independently trusted controller NOT VERIFIED**.
This is an extension of S-008A, not an authorization for general worker execution.

## Existing security boundary and threat model

The GitHub PR controls Python host code, worker fixture, Docker policy, SHA pins,
workflow, and tests. The fixed containerized guest has no GitHub token, mounted
Docker socket or external network in the observed reviewed CI, and its report
is untrusted data. These observations do not defend against a PR author who can
change the workflow/controller, an adversarial OCI image, hostile kernel, or
privileged modifications on the Docker host. The owner-facing Launch Gate
must remain disabled.

The main branch API was read as `protected=false`; a rulesets read returned
GitHub 403 (subscription/visibility limitation), and branch protection details
could not be accessed with the linked integration. A separately governed
trusted controller has **not** been deployed or attested.

## Concrete change

* `foundry/isolated_worker.py` generates a random 128-bit `session_nonce`
  via `secrets.token_hex(16)` for **each invocation**, and computes a SHA-256
  digest over the exact, sorted, compact JSON of the already allowed fixed task.
* Both values are passed as **public, non-secret** environment metadata to
  the fixed reviewed container. The guest refuses to produce a candidate if
  either field is absent/ill-formed. Its report echoes the fields.
* The host checks strict field types and exact nonce + request digest matches
  before passing the returned candidate to the pre-existing data-only quarantine
  validator. Missing, mismatched, duplicated or forged fields fail closed.
* The reviewed fixture content SHA-256 was updated; the work still runs only
  `/work/handoff_worker.py` in the allowlisted immutable OCI-image digest.
* The main Foundry Gate now includes the new 10-test S-008 suite.
* The sandbox workflow contains a **real Docker negative control** for a
  missing nonce, verifies guest refusal, checks container removal, and emits
  a bounded review-only evidence JSON to CI logs.

This protects **one tested local invocation** against accidentally reusing a
result from another invocation or task. **Nonce echo is not authentication**:
the PR-controlled host sees, can set and can forge both values. SHA-256 is
content integrity, not a signature. There is no external signing key, durable
replay ledger, authenticated remote transport, or independent source of trust.

## Reproducible RED → GREEN evidence

1. Test-first RED SHA `63bc41c0cedb927ae71d0875eb3e6662e1452012`:
   [full CI #42493885521](https://github.com/mel2003ru-code/OpDB/actions/runs/42493885521)
   observed three failures from previously unbound sessions.
   [Docker workflow #42493885551](https://github.com/mel2003ru-code/OpDB/actions/runs/42493885551)
   failed as well. The unchanged Foundry gate did not yet run the new suite.
2. Implemented nonce/request-digest matching in fixed guest and host;
   updated fixture's reviewed SHA and corrected a test regex.
   [GREEN full CI #42494148036](https://github.com/mel2003ru-code/OpDB/actions/runs/42494148036):
   **247/247 PASS**; [Foundry #42494148135](https://github.com/mel2003ru-code/OpDB/actions/runs/42494148135):
   163/163 PASS; [real Docker #42494148015](https://github.com/mel2003ru-code/OpDB/actions/runs/42494148015):
   10/10 S-008 tests, positive fixed guest and existing 8 MiB shared-memory
   negative control PASS.
3. New real negative control and Foundry Gate integration:
   exact code SHA `cab79a4594c279bcd406ce32837cfd8519b47d1e`.
   [full CI #42494505114](https://github.com/mel2003ru-code/OpDB/actions/runs/42494505114):
   **247/247 PASS**.
   [Foundry gate #42494505113](https://github.com/mel2003ru-code/OpDB/actions/runs/42494505113):
   **173/173 PASS**.
   [real Docker #42494505111](https://github.com/mel2003ru-code/OpDB/actions/runs/42494505111):
   fixed guest positive and missing-nonce adversarial run PASS.
   Docker logs include `EXPECTED_S008B_NEGATIVE: missing nonce denied in actual Docker guest`
   and `S008_FIXED_GUEST_OBSERVED; independent trusted controller NOT ATTESTED`.

The 10 Python S-008 tests are **mocked host orchestration**; they do not
certify OS isolation. The Docker observations come from actual containers on
GitHub-hosted runners; they use fixed, reviewed fixtures, **not** arbitrary AI
code. No paid model or external API was used for the worker.

## Outstanding S-008B work / acceptance gate

1. **Trusted authority**: choose an owner-approved trust root that candidate
   PR code cannot modify. E.g., independently administered pinned controller
   image/service, or appropriately protected CI pipeline with separately
   controlled review and immutable source. Do not assume the existing private
   GitHub branch has protective policies.
2. **Separate security principals**: the controller must own task admission,
   credentials, Docker execution authority and budgets; the guest must never
   receive those privileges. Verify job/workflow edits cannot bypass controls.
3. **Authenticated provenance**: bind controller-signed request to repository,
   immutable commit, task, input bytes, allowed files, nonce, policy version,
   resource limits and expiration. Design verification so the untrusted worker
   has *no signing secret*. Provide independently controlled replay prevention.
4. **Artifacts and recovery**: limit and authenticate messages, verify outputs
   against independent test oracles, harden lifecycle and daemon-side disk quotas,
   persist evidence outside untrusted candidate checkout. Current `/tmp` and
   `/dev/shm` bounds do not prove total host/Docker disk caps.
5. **Independent Safety/Quality sign-off**: reproduce mutation of workflow,
   payload, nonce and digest; race and replay, image substitutions, secret/socket,
   network, timeout, output, resource denial, cleanup and provenance tests.
   A single development assistant cannot self-certify its own work.
6. **Governance**: P0 #21 OPEN blocks Lens; Core #33 remains draft with stacked
   Quality #34 separately reviewed first. No PR merges, write credentials to
   guest, paid AI use, production execution, launch enablement or start timestamp.

S-008B is **PARTIAL / NOT READY**. The green owner button stays **DISABLED**.
