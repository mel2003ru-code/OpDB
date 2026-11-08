# OpDB Foundry 30-minute research checks (research execution boundary)

Date: 2026-11-08. Status: experimental workflow. A successful GitHub Actions run does not establish OpDB safety.

## What actually runs every 30 minutes

GitHub Actions triggers the small, isolated research checker at UTC :07 and :37. Every run enumerates 10 research areas R01-R10 and 3 engineering areas TASK-001/002/003, records an explicit status and uploads a JSON artifact and a Step Summary.

Currently **R01–R10** have narrowly scoped SQLite/Python or synthetic-model checks. R01: transactional aggregate equivalence; R02: logical SQLite file page footprint; R03: dynamic-index oracle; R04: FIFO/LRU cache models; R05: synthetic prediction admission; R06: SQLite concurrent writers and snapshots; R07: os._exit WAL recovery; R08: tail latency including index DDL; R09: synthetic cost/validity guard; R10: metamorphic SUM oracle. TASK-001/002/003 remain **NOT_CONFIGURED** because no independent working engine/Safety/Quality implementation has been admitted. Models (R04/R05/R09) report MODEL_SMOKE_PASS and SQLite-backed checks report SQLITE_SMOKE_PASS. These tests do **not** implement the OpDB engine or autonomous scientific discovery. A Python/SQLite PASS is not a production correctness proof and never authorizes a merge.

New probes must be proposed through a PR, tested independently, reviewed by Quality and admitted to the schedule from trusted main. Never execute untrusted PR code in a write-privileged scheduled runner.

## What does not run automatically

Existing ChatGPT chats cannot be executed every 30 minutes through GitHub. ChatGPT scheduled tasks have a maximum recurrence of once per hour, and an existing daily OpDB engineering autopilot remains configured until explicitly changed. GitHub CLI/API cannot wake a specific chat.

A true multi-agent research executor needs a separately provisioned model runtime/worker and authorization, with explicit budget control and API credentials if a paid external API is chosen. This workflow deliberately contains **no model API calls**, no API secrets, no branch write access, no auto-PR, no merge, no deployment and no production database connectivity.

## Resource controls

- A single bounded 5-minute job; actual short probes should finish far sooner.
- Read-only GitHub token, no external Python packages or network requests from tests.
- Results are retained in GitHub Actions Job Summary and log output (not artifact uploads), because the repository encountered an exhausted Actions artifact storage quota. GitHub Actions minutes for a private repository may still be limited or billable.
- GitHub cron executions can be delayed or skipped; reports must distinguish missing runs.
- Full model-generated scientific work cannot be inferred from this heartbeat.

## Next admission

Safety, Core and Quality must deliver reviewed runnable tests, with exact seeds, independent oracle, data hashes, failure modes and performance budgets. Only then can the respective task be marked as genuinely tested.

## Additional independent controls and scientific discovery (v0.4)

### Mandatory P0 negative control (every 30-minute cycle)
The research heartbeat now *deliberately* reproduces two unsafe behavior classes in an isolated SQLite fixture:
- A cached derived Lens value becomes stale after a different connection commits a change.
- A privileged editor forges a change-log payload while retaining the expected sequence and old image, causing an incorrect replayed Lens.

If both counterexamples are demonstrated, the field is `EXPECTED_COUNTEREXAMPLE`; this is not a successful safety property of the actual OpDB engine. If the fixture stops demonstrating the expected result, the research run fails. Results appear in the GitHub Issue #17 rolling status and the job logs. The unresolved integration blocker remains Issue #21.

### Weekly multi-runtime reproducibility
`.github/workflows/research-matrix.yml`: runs four fixed seeds on Python 3.11/3.13 on Ubuntu plus Python 3.13 on Windows, records JSON in GitHub Actions logs and summaries. This checks the *research harness*, not complete cross-platform OpDB compatibility. It is intentionally scheduled weekly to avoid exhausting private runner minutes.

### Weekly literature metadata radar
`.github/workflows/literature-radar.yml`: queries public Crossref REST bibliographic metadata and logs DOI candidate lists (recent publications in four DB research areas). Candidates are **not evaluated research results**. Exact publisher/author claims and DOI details must be verified before scientific use. No article full text is automatically downloaded, and no model/paid inference API is invoked. Offline unit tests use mock responses.

### Artifacts and missing executable engines
The GitHub Actions artifact-storage quota is reported exhausted. All new workflows retain evidence in logs and Job Summary rather than calling `upload-artifact`. This avoids scheduled job failures from uploads, but logs have GitHub retention limits. For durable evidence, an explicitly reviewed PR may separately add small checked-in results with reproducible SHA-256.

TASK-001, TASK-002 and TASK-003 retain `NOT_CONFIGURED` in scheduled checks until independent runnable adapters are supplied as reviewed source code, and Quality runs the integration matrix. No private chat is automatically executing every half-hour.
