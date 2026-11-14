# M4 research note: numeric Lens (TASK-014)

Research prototype on SQLite; it does not decide the native OpDB format.
Opt-in class `opdb.NumericTruthStore(path, groupers={name: fn}, grouping=name)`;
`TruthStore`, `PersistentTruthStore` and their Lens are unchanged. Values must be
8-byte big-endian signed integers (anything else is a `ValueError` before any
write). `numeric_stats(group)` returns count, sum, min, max, and `served_from`.

**Storage (one transaction per `apply`).** `opdb_nlens_group(g, n, s)` count and
sum per group; `opdb_nlens_val(g, x, k)` an ordered index of every value per
group; `opdb_nlens_meta(schema_version, lens_seq, grouping, tot_n)`.

**min/max rule.** sum and count are incremental. min/max are the first/last
entry of the group in `opdb_nlens_val`, so deleting or overwriting the current
extreme needs no rescan: the old entry is removed by its exact `(g,x,k)`, found
from the old Source value. Cost: one extra index row per key (file size and
write time, see below). The extra index is used instead of looking the new
extreme up in Source because Source cannot find the members of a group defined
by an arbitrary Python function without scanning every row.

**Reads check themselves.** The min and max entries are cross-checked against
the Source row (value and group) before they are returned; a mismatch makes the
Lens untrusted and the answer comes from Source.

**Open** is bounded (no Source or index scan): metadata exists, schema version
and grouping name match, `lens_seq == commit_seq`, group rows are well-typed and
add up to `tot_n`. A different grouping name, stale generation or damage means
untrusted, then rebuilt from Source in one transaction. Any commit by another
connection (`data_version`) triggers a rebuild before the next answer.

**Overflow.** If a group sum would leave signed 64-bit, the Source write still
commits, the Lens is not updated and stays untrusted; answers come from a Source
scan using Python ints. Rebuild is retried only after something changed, and
succeeds once all sums fit again.

**Wrong-width Source values** (written outside the store) are never skipped:
rebuild fails and numeric reads raise `SourceIntegrityError`.

## Limits (not hidden)

- The grouping function must be deterministic; only its *name* is stored and
  compared, not its behaviour. Changing the code under the same name is not detected.
- Without a store open, a raw Source write that moves neither `commit_seq` nor
  the Lens is not detected at open (same boundary as `docs/M3_PERSISTENT_LENS.md`).
  A missing or wrong non-extreme index entry is not detected by the read check.
- The Source answer (and rebuild) is a full scan: O(rows), not a group lookup.

## Measurements

Machine: Intel Xeon @ 2.10 GHz, 2 vCPU, Python 3.13.18, SQLite 3.53.1, SHA of
the base commit 5c6278b (plus the TASK-014 branch). Script:
`experiments/m4_numeric_bench.py`; medians of 15 runs (lens read: 300 runs),
raw runs are printed by the script. 1,000-row batch = puts of new keys into 50 groups,
compared with the plain `TruthStore` (no Lens) on an identical file.

| rows | read one group, Lens | read one group, Source scan | 1,000-row batch, numeric Lens | 1,000-row batch, no Lens | file size, numeric / plain |
| --- | --- | --- | --- | --- | --- |
| 10k | 0.031 ms | 12.2 ms | 7.6 ms | 6.1 ms | 1.83 / 1.18 MB |
| 100k | 0.032 ms | 116.7 ms | 9.4 ms | 7.6 ms | 8.6 / 5.6 MB |
| 1M | 0.032 ms | 1207 ms | 9.4 ms | 7.2 ms | 79.3 / 52.3 MB |

Read: the Lens answer is constant (~0.03 ms); recomputation from Source grows
linearly (38,000x at 1M rows). Writes: the Lens adds about 1.5-2.2 ms per
1,000-row batch (+25% to +31%) and about 50% to the file size. First
open of a 1M-row file (rebuild) took 4.9 s; reopening a persisted Lens took
about 1 ms.
