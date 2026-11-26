# TASK-039 — M5: publish the first benchmark table (a manual run, not a controller task)

Status: waiting for TASK-035..038 to be merged.

## What it is
A person (or the assistant working with the owner) runs `experiments/bench/run.py` on VPS1 under the throttling rules of
`docs/benchmarks/README.md`, and publishes the result as a docs pull request: `docs/benchmarks/FIRST_RUN.md` (the table with
median and min/max of at least 15 runs per cell, the data digest, SHA, seed, command, machine, versions, `uptime` and free
memory before and after) and the raw JSON next to it.

## Why it is not a controller task
The controller only produces Python or Rust source and new tests; it does not run benchmarks and cannot add the raw JSON file.

## Acceptance
- Every contender is verified against the model in the file; a missing capability is `NOT_IMPLEMENTED`, a non-applicable one
  `NOT_APPLICABLE`.
- The table states plainly that VPS1 is a shared production server and the numbers are indicative.
- No sentence claims that OpDB is faster than SQLite unless the table shows it with the stated durability settings.
