# Research runs inside the controller cycle

Research does NOT run as a second scheduler and spends no GitHub Actions minutes. The VPS controller (the one
conductor of the development cycle) runs it at the end of a cycle, one run at a time, so heavy runs can never overlap
with task builds.

## How a run works
1. When due (default every 60 minutes) and the host is healthy, the controller reads `research/hypotheses.json` from
   the current `main` and takes the next runnable hypothesis (round robin).
2. It renders the hypothesis template (`research/rust/*.rs.tmpl`) with a fresh seed (derived from the `main` SHA and a
   counter), drops the generated test into the snapshot and runs it in the existing isolated Rust sandbox:
   `cargo test --offline`, no network, CPU/memory limits, 570 s timeout. Only numbers and a 40-hex SHA are substituted.
3. The test prints ONE JSON line: hypothesis, engine, result, commit, seed, configuration, evidence counters, the
   reproduce command and the limits of the claim. The controller keeps it in its state and, in `publish` mode, updates
   one marked comment of Issue #43 in place (no duplicates, nothing is committed to `main`).

## Rules for results
- `PASS` means only: no mismatch found on these seeds in this configuration. It is not a proof.
- No result line means `ERROR`, never `PASS`. A direction without an implementation is `NOT_IMPLEMENTED`.
- A `FAIL` is a finding: it carries the SHA, the seed and the exact command that reproduces it. A person turns it into a
  backlog task; the controller does not create tasks or issues from research.
- Rust and Python (SQLite) results are reported separately.

## Running a hypothesis by hand (throttled: the VPS is shared)
```
python3 render_research.py r_rust_01.rs.tmpl rust/opdb-core/tests/research_r_rust_01.rs 11 20000 24 <40-hex main SHA>
cd rust/opdb-core
nice -n 19 cargo test --offline --test research_r_rust_01 -- --nocapture
```
On a shared server also use a CPU quota (for example `systemd-run --scope -p CPUQuota=20%`). To prove the harness can
fail, set `INJECT_MODEL_FAULT` to `true` in the rendered file: the run must end in `FAIL`.

## Controller switches
- `/var/lib/opdb-agent/research.mode`: `dry` (default: record and log only), `publish`, `off`.
- `/var/lib/opdb-agent/research.disabled`: kill switch without a restart.

## Adding a hypothesis
Add an entry to `hypotheses.json` (id `R-<AREA>-NN`, `engine`, `template` under `research/rust/`, `test_name`
`research_...`, `ops` 100..200000, `keys` 1..64) and the template with the placeholders `__SEED__`, `__OPS__`,
`__KEYS__`, `__SHA__`, each exactly once. Check the template by hand first, including the fault-injection run.
