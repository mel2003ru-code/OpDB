# OpDB Foundry 30-minute research checks (research execution boundary)

Date: 2026-11-08. Status: experimental workflow. A successful GitHub Actions run does not establish OpDB safety.

## What actually runs every 30 minutes

GitHub Actions triggers the small, isolated research checker at UTC :07 and :37. Every run enumerates 10 research areas R01-R10 and 3 engineering areas TASK-001/002/003, records an explicit status and uploads a JSON artifact and a Step Summary.

Currently **R03**, **R07** and **R10** contain narrowly scoped, reproducible SQLite-only probes (dynamic-index query equivalence; process-exit WAL recovery; metamorphic SUM oracle). Other areas intentionally show **NOT_CONFIGURED**. These tests do **not** implement the OpDB engine or autonomous scientific discovery. A Python/SQLite PASS is not a production correctness proof and never authorizes a merge.

New probes must be proposed through a PR, tested independently, reviewed by Quality and admitted to the schedule from trusted main. Never execute untrusted PR code in a write-privileged scheduled runner.

## What does not run automatically

Existing ChatGPT chats cannot be executed every 30 minutes through GitHub. ChatGPT scheduled tasks have a maximum recurrence of once per hour, and an existing daily OpDB engineering autopilot remains configured until explicitly changed. GitHub CLI/API cannot wake a specific chat.

A true multi-agent research executor needs a separately provisioned model runtime/worker and authorization, with explicit budget control and API credentials if a paid external API is chosen. This workflow deliberately contains **no model API calls**, no API secrets, no branch write access, no auto-PR, no merge, no deployment and no production database connectivity.

## Resource controls

- A single bounded 5-minute job; actual short probes should finish far sooner.
- Read-only GitHub token, no external Python packages or network requests from tests.
- Results stored for 7 days. GitHub Actions limits for private repositories may apply.
- GitHub cron executions can be delayed or skipped; reports must distinguish missing runs.
- Full model-generated scientific work cannot be inferred from this heartbeat.

## Next admission

Safety, Core and Quality must deliver reviewed runnable tests, with exact seeds, independent oracle, data hashes, failure modes and performance budgets. Only then can the respective task be marked as genuinely tested.
