# OpDB Foundry S-008B-2 — independent trust root (REFERENCE ONLY)

Date: 2026-11-08. Existing draft PR #32, branch `foundry/guarded-loop-gate-0-1`.
**Verdict: PARTIAL / NOT INDEPENDENTLY ATTESTED / LAUNCH DISABLED.**

## Actual trust-boundary finding

GitHub `main` at `9a03a91fe1b4ee90d6abda9394d6543d00fb5395`
reports `protected=false` (verified again for this phase).
PR #32 previously at `7bc8ae4609f3b1a4822b63bfa5b4f9b2f5358ce2`.
PR #33 at `14ad0415db0a9fdf6dc3a68fe4c858b08cf467d5`,
stacked PR #34 at `30f9ca7aa5e1be5b23144e22ef22d47fe0826d78`.
All three draft PRs are open. P0 Issue #21 remains open.
This PR controls its workflows, Python modules, tests and SHA allowlists.
**Passing its own CI can never by itself attest its controller.**

For current GitHub plans, protected branches are provided for public repositories
on GitHub Free; a private repository requires a supported paid plan. A public
trust-root *code-only* repository is a potential no-subscription alternative,
but has NOT been authorized or created. No private source, logs, credentials or
private evidence should be published to enable that option.

## Target separation (NOT DEPLOYED)

1. **Owner-governed authority**: controller code, pinned dependency tree,
   job definition, policy allowlist, signing key, trusted clock and persistent
   replay ledger must live outside PR #32 and outside any candidate write path.
   Do not use the current unprotected `main` as an attested authority.
2. **Admission**: independent controller fetches immutable source commit,
   checks allowlisted fixed offline task, exact policy/image bytes, execution
   limits, source origin and owner-approved intent. Treat all PR paths,
   filenames, workflow YAML, logs and artifacts as hostile input.
3. **Challenge**: controller creates a fresh 128-bit nonce, binds repository,
   immutable source commit, fixed task and canonical request SHA-256, policy
   digest, immutable OCI-image digest, expiry and 16-KiB report budget. The
   controller alone holds the HMAC key. Public challenge MAC can be passed
   to a guest; **key cannot**.
4. **Guest**: currently only the fixed reviewed Docker fixture is permitted.
   Guest has no secret, GitHub write token, Docker socket, network, arbitrary
   candidate code permission or authority to validate itself.
5. **Evidence**: controller verifies challenge MAC, exact immutable context,
   trusted clock window, bounded guest data and echoed nonce/digest, and
   transactionally consumes nonce in controller-controlled durable storage.
   Only then may it create an HMAC-protected *quarantine receipt*. Replays
   and ledger failures block; crash-after-consumption intentionally blocks a
   retry. The guest response is **not authenticated as an honest computation**.
6. **Independent validation**: Safety and Quality must separately replay
   adversarial cases against the independently governed implementation.
   No production/Lens/merge/launch permission is derived from a receipt.

The reference Python module `foundry/s008b2_protocol.py` implements only
the *data protocol*, HMAC domain separation and SQLite-transaction replay
demonstration, with `tests/test_s008b2_protocol.py` offline falsification.
Both files are currently PR-controlled and cannot establish a trust boundary.
The implementation is intentionally NOT connected to
`foundry/isolated_worker.py` or any privileged CI job. It does not execute
a worker, generate any real credentials, deploy a service, or unlock launch.

HMAC-SHA256 authenticates **only possession of one symmetric key**;
it is not a public signature, not worker attestation, and not proof of output
correctness. Source commit SHA and SHA-256 content digests are not trust
anchors without independent verification of where bytes came from.
The protocol's `now`, `request`, image/policy identifiers and SQLite handle
are caller-supplied in the reference API; a PR-controlled host could fabricate
them. Production adaptation requires trusted identity/clock, resource
isolation, key rotation, durable ledger backups, file permissions and review.

## Minimal-cost trust root options — owner approval required

A. **Code-only protected public controller repo** on GitHub Free. Only
owner-reviewed, public, generic verifier code; never expose private OpDB
sources. Run manually on trusted trigger, no execution of PR checkout. A
read-only private-repository credential, if ever needed, must be separately
approved and protected. Public visibility alone does NOT make Actions secure.

B. **Dedicated existing VPS service** with a distinct unprivileged account,
separately reviewed signed/pinned controller image, isolated working tree,
independent secret store and append-only replay ledger. Cost could be low if
existing resources suffice, but isolation, administration, backups and
network boundaries have not been audited. NOT authorized for deployment.

C. **Supported GitHub paid private-branch protection** with enforced
independent reviewers and non-bypass policy. Subscription and permissions
must be assessed and owner-approved; current plan/controls are unverified.

Do **not** add a `pull_request_target` or `workflow_run` privileged workflow
that checks out or executes candidate PR code. A compromised PR can poison
artifacts or scripts. Even a read-only workflow may be modified in the PR,
so only separately governed workflow and input provenance count.

## Test matrix / evidentiary limits

- Challenge MAC mutation, wrong key, repo, SHA, policy and image binding.
- Short expiry, future task, overlong validity, fixed no-model task.
- Replay using same ledger; two SQLite connections racing; committed nonce
  reopened after process restart.
- Duplicate JSON fields (including nested), malformed or oversized output,
  wrong guest nonce/digest, forged launch authority.
- HMAC receipt tampering, absent SQLite table, guest-controlled payload
  treated only as quarantined untrusted data.
- Always false: trusted controller attested, GitHub write, auto-merge,
  production, launch.

**RED attempt:** first test-only commit
`7bf0ef0ee2130eb7ac952ce998d0d06e710f7334`.
GitHub created runs
[full CI #42496188517](https://github.com/mel2003ru-code/OpDB/actions/runs/42496188517),
[Foundry #42496188561](https://github.com/mel2003ru-code/OpDB/actions/runs/42496188561),
[Docker #42496188445](https://github.com/mel2003ru-code/OpDB/actions/runs/42496188445).
All were marked failure within seconds **with no job steps or retrievable
logs**. Therefore they do NOT prove the expected test RED, nor a Docker
regression. Reason for runner startup failure is not independently known.

**Implementation checkpoint:** protocol `6959a8c9a9774455c2fe8e51d809642d965a4705`;
Foundry Gate wiring `6930f339f08a430e27becac5f9fe6d169beb1d55`;
additional concurrency/restart falsification
`3b281ab59d14b267a1820ce3f5c6fbb1ecd27bca`.
CI on these changes is not yet established GREEN.
Prior S-008B-1 CI remains historical evidence only, bound to its exact SHA.
New work must not inherit a prior run's PASS.

## Required before any S-008B-2 acceptance

- Independent owner approval of trust-root location and governance.
- Truly independent code+workflow source pinned outside candidate branch.
- Real root with no secret/socket/token available to guest.
- Secret lifecycle, audited durable nonce ledger, trusted time, resource
  and disk limits; test crash/race/compromised-controller recovery.
- Fail-closed authentic CI rerun with logs, independent negative controls,
  Quality/Safety signatures/review at exact immutable SHAs.
- S-008B-2 closure still does not override open P0 #21. No automatic
  PR merges, Lens activation, remote execution, production or launch date.

**Current owner button: DISABLED.**
