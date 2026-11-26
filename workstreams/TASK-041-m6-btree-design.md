# TASK-041 — M6 stage 2: paged B-tree design (aimed at reads)

Status: WAITING. Start only after the first benchmark that includes the Rust LSM has been published (TASK-039 and L15 of
TASK-040).

## Why it waits
SQLite is itself a carefully tuned B-tree, so a read win is not expected to come cheaply. The owner decided stage 2 should come
only after stage 1 is measured; the benchmark results decide whether it is worth starting and which read workloads it must beat.

## What it will be
A design document `docs/BTREE_DESIGN.md` first (pages, free list, copy-on-write or WAL, recovery, the read workloads of
`docs/benchmarks/README.md` it targets), then small implementation tasks like the LSM ones. No code before the document is
reviewed.
