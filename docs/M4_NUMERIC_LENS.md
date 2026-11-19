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

Numeric reads pin one SQLite read snapshot for version checking, count/sum,
extremes and Source fallback. A concurrent writer cannot mix generations in
one answer. Open/rebuild capture the trusted data version before validation
or rebuilding, so a foreign commit after completion is noticed on the next
read rather than silently adopted as a trusted baseline.

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

## TASK-017: rebuild-from-Source time

Machine: Intel Xeon @ 2.10 GHz, 2 vCPU, 7.8 GB RAM, Linux 6.18 (x86_64,
glibc 2.39), virtual disk (`/dev/vda`, reported non-rotational), Python
3.13.18, SQLite 3.53.1, WAL + `synchronous=FULL`. "Before" = unchanged code at
5d35094; "after" = the same tree plus the `rebuild()` change of this PR. Script:
`experiments/m17_rebuild_bench.py` (1,000 groups, random 8-byte values, seed 17);
raw runs in `experiments/results/m17_*.json`. Each cell: median / worst of 7
runs, ms. "Untrusted open" = open after `lens_seq` was moved back from outside.

| rows | rebuild, before (run 1; run 2) | rebuild, after (run 1; run 2) | untrusted open, before | untrusted open, after |
| --- | --- | --- | --- | --- |
| 10k | 25/29; 26/42 | 22/22; 21/22 | 25/26; 30/38 | 26/29; 25/26 |
| 100k | 314/424; 317/377 | 314/354; 242/288 | 327/396; 322/334 | 250/266; 258/379 |
| 1M | 5166/5546; 5238/5544 | 3154/3523; 3146/3359 | 5296/5818; 5204/5385 | 3386/3535; 3215/3468 |

Where the time went (one 1M-row rebuild split into steps, `--phases`, ms):
Source fetch 674, key validation + grouping + decode 674, aggregation 368,
both `DELETE`s 10, group insert 1, **value-index insert in Source order 3,535**;
the same insert after sorting 1,356 plus the sort 1,301. COMMIT is not
measurable separately in this mode (the steps are rolled back).

Change: `rebuild()` collects rows per group and inserts the value index in
(group, value) order, in chunks inside the same `BEGIN IMMEDIATE`, so the
`opdb_nlens_val` B-tree fills almost sequentially. Stored format, schema
version, validation, `open_mode`/`open_reason` and overflow fallback are
unchanged; tables after the new rebuild were checked equal to the old one's
on a 200k-row file and to a Source-derived expectation in
`tests/test_numeric_rebuild_017.py`.

Result: at 1M rows rebuild and untrusted open fell by about 35-40% (about
5.2 s to 3.2 s), well outside the run-to-run spread. At 100k the two "after"
runs disagree (one shows no gain for rebuild, one ~24%); at 10k the gain is
~15% for rebuild and none for open. Rebuild is still O(rows); the remaining
time is mostly the Python scan, validation and sort. Peak memory was not measured.
