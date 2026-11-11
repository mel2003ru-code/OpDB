# OpDB Foundry — Launch Gate and launch timestamp protocol

**Status:** DRAFT / NOT READY. Task: [Foundry Loop #31](https://github.com/mel2003ru-code/OpDB/issues/31). Related [Safety P0 #21](https://github.com/mel2003ru-code/OpDB/issues/21), [integration #5](https://github.com/mel2003ru-code/OpDB/issues/5), and draft PR #32.

## Owner's launch instruction (2026-11-08)

The owner explicitly requested a **large green button labelled «Запустить»** before full OpDB Foundry automation is enabled. The button is the **only user-visible approval gesture** for starting the full autonomous development cycle after all independent readiness requirements have been met. Do not activate the button prematurely or substitute a routine scheduled research run for this launch.

### Exact timing policy

Record two distinct milestones:

1. **Launch request**: the moment the owner actually presses the enabled button, captured from an authoritative server-side received-event timestamp (UTC). This is a request, not proof that anything started.
2. **Confirmed launch**: the first independently verified successful activation of the approved autonomous worker, captured from a trusted server-side deployment/run event, with pinned release SHA, trusted run ID, expected services, healthy checks and approval link.

Only the confirmed event is the official launch time. Persist both UTC instants in the release log / GitHub Issue #31 with Paris and Moscow local representations and numerical UTC offsets. On every retry keep the original request event ID, new attempt IDs and each result; never overwrite a previous failure. Time formatting and daylight-saving conversion use the IANA timezones Europe/Paris and Europe/Moscow. Do not invent or backdate timestamps; a passing Python test does not create a launch event.

**Planned receipt fields:** requested_at_utc, confirmed_started_at_utc, requested_at_paris, confirmed_started_at_paris, confirmed_started_at_moscow, request_event_id, github_run_id, github_run_url, approved_commit_sha, deployment_artifact_digest, approved_by, independent_quality_review, safety_proof_review, health_check_evidence, status and retry_id. If no confirmed run exists: status=NOT_LAUNCHED and confirmed_started_at_utc=null.

## Safety state machine

- NOT_READY: one or more prerequisites missing, and no trusted operational readiness attestation. The green launch button is visible only as **disabled**, with its reason clearly stated.
- BLOCKED: invalid evidence schema or declared failed critical check. The button stays disabled.
- OWNER_REVIEW_REQUIRED: 14/14 syntactically complete **self-reported** checks. Still **NOT** sufficient for launch because links, SHA claims, artifacts and signatures are not independently verified by this offline module. Button stays disabled.
- READY_TO_LAUNCH: reserved for a future trusted release controller which independently verifies evidence, enforces single-use owner approval, an actual deployment target, budget, operational safety and a rollback path. This state is **not implemented** in Phase A.
- LAUNCH_REQUESTED: after the enabled button was pressed and the authenticated server received the launch request. This state is **not implemented** in Phase A.
- RUNNING_VERIFIED: after observed service startup, health check and an authenticated launch receipt. This state is **not implemented** in Phase A.
- FAILED / ROLLED_BACK: retain timestamps and evidence; never mark the failed attempt as a successful launch. Future state machine only.

## Required gates before enabling

Actual Core adapter, enforceable trusted mutation capture for Lens (P0 #21), independent Quality, complete fault matrix and oracle, pinned reproducible baselines, approved model worker isolation and budget ceilings, minimum privileges and secrets protection, staging rehearsal, working rollback/restore, explicit production policy, monitoring/emergency stop and a trustworthy superiority pause watcher.

The safety system MUST NOT accept a caller-set boolean as an attestation. The Phase A tool validates only 14 status entries with linked provenance **shapes**. Even a full PASS record produces OWNER_REVIEW_REQUIRED and explicitly launch_authorized=false, launched=false, launched_at_utc=null. No production or autonomous AI worker is started by this code.

## Reproduction

    python -m unittest -v tests.test_launch_gate
    python -m unittest discover -s tests -p 'test_*.py' -v
    python -m foundry.launch_gate --output launch-readiness.json

The last command must say NOT_READY, button_enabled=false and launched_at_utc=null while no real trusted launch system has been installed. Output is a readiness description, not an actual launch receipt.

## Owner UI contract

Before readiness, present the large green button **Запустить** only in disabled state with the safety reason displayed. Once trustworthy readiness is established, show the enabled large green button. Its future click must send an explicit approval event through an authenticated host action; it must not execute a deployment based solely on a client-side message, a self-reported JSON flag, or a metadata PASS. On click, record the server receipt time first; after real health-confirmed startup, append the official start time and GitHub run evidence to this project log. If no launch occurs, show NOT_LAUNCHED without inventing a date.

The current ChatGPT interface can display the disabled preview and accept a new conversation turn, but this repository has **no installed launch backend or secure deployment approval endpoint yet**. Do not misrepresent a conversational UI button as a production launcher.

## Outstanding work

1. Get runnable Core/Safety/Quality into GitHub; independently validate Issue #21 and the full ADR contract.
2. Build and independently verify the isolated coding runtime, budget/rate controls, staging, rollback, and authenticated release run.
3. Build trusted readiness verification; replace the read-only placeholder only after independent Quality approval.
4. Wire an enabled Launch action to the approved runtime with idempotency, user identity, server timestamp, exact commit and deployment receipts.
5. Verify the receipt with an independent observer and append both local and UTC timestamps to the durable GitHub log.

**No production deployment or full autonomous Foundry launch is approved by this document.**
