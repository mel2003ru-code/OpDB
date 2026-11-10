# Lens 0.1 — disposable group aggregates

`TruthStore(path, lens=True)` enables the new experimental group-count Lens.
The default remains `lens=False` so the 43 existing Core Source-only tests and
older callers are unchanged. `get`, `scan` and `snapshot` **always** read Source;
only `group_stats(group)` may return `served_from="LENS"`NaN`GroupStats` reports row count, sum of BLOB byte lengths and read path.
`group_stats_source` computes the result from Source rows, independently of
Lens state. Empty groups return `(0, 0)`; key `/x` belongs to group `""`.

`opdb_meta` holds an engine-owned incrementing `commit_seq`. Every `apply`
increments it in its SQLite data transaction. When Lens is enabled, each batch
computes old/new per-group deltas inside the transaction; only a successful
`COMMIT` advances the in-memory Lens. Rollback never publishes a delta.
Opening with Lens enabled rebuilds from one SQLite snapshot. A mismatch in
`commit_seq` or connection-local SQLite `PRAGMA data_version` discards Lens:
that call reads Source, then rebuilds for subsequent Lens reads.

**Trust boundary:** ADR-006 assumes OpDB is the single writer. External raw
SQLite writes are outside this model; `data_version`/sequence checks are only
best-effort detection, not authentication. Lens data is not persisted and is
not a native DBMS or a cross-process-safe cache. A privileged writer changing
SQLite files/schema can defeat detection. The legacy `admit_lens()` diagnostic
still rejects arbitrary row-candidate admission; it is unrelated to the
engine-maintained, opt-in aggregate Lens.

Reproduce with `python -m unittest discover -s tests -p 'test_*.py' -v`.
For local microbenchmarks: `python experiments/lens_bench.py`. Benchmarks
compare Lens only to Source on the same SQLite-backed prototype.
