# M3 research note: persisted Lens (TASK-012)

Research prototype on SQLite; it does not decide the native OpDB format.
Opt-in class `opdb.PersistentTruthStore`; `TruthStore` is unchanged.

**Storage.** `opdb_source_kv` (Source), `opdb_lens_group(g, n, b)` (per-group
row count and value bytes), `opdb_lens_meta(schema_version, lens_seq, tot_n,
tot_b)`, and the existing `opdb_meta.commit_seq`. Each `apply` changes Source,
Lens rows, totals and both sequence numbers in one `BEGIN IMMEDIATE`
transaction; no triggers.

**Open (bounded, no Source access).** The Lens is trusted only if the
metadata row exists, `schema_version` matches, `lens_seq == commit_seq`, every
Lens row is well-typed with `n>0, b>=0`, and the Lens rows sum to the stored
totals. Otherwise it is rebuilt from Source in one atomic transaction; if that
fails (e.g. a non-BLOB Source value) the store answers from Source or raises.

**While open.** Any commit by another connection changes `PRAGMA data_version`;
the store then rebuilds before the next Lens answer (correct but costly when
two stores share a file).

## Threat boundary (owner decision needed before widening)

Detected at open: another `TruthStore` write (commit_seq moved), a changed
schema version, missing/garbled metadata, a deleted or edited Lens row that
breaks the totals. Detected while open: any other connection's write.

NOT detected without a full Source scan: a raw SQL write to Source made while
no store has the file open (it changes neither `commit_seq` nor the Lens), or
a Lens edit that keeps every total equal. `test_documented_boundary_...` pins
this. This is not cryptographic corruption detection. `Store.rebuild()` is the
explicit full-scan repair. Widening the guarantee (e.g. a Source checksum
maintained on every write, or periodic scans) is the owner's call.

## TASK-013: write cost of the persisted Lens

Machine: Intel Xeon @ 2.10 GHz, 2 vCPU, Python 3.13.18, SQLite 3.53.1. Before = main
8b820b2; after = the TASK-013 branch. Script: `experiments/m3_write_profile.py`
(30 batches of 1,000 operations per shape; two runs at every size, 1M included). Median / p95 in ms, persisted store only; the in-memory Lens and
Source-only stores were run in the same script for reference.

Where the time went (new-key batch, phases re-run on a private connection and
rolled back, so approximate): 1,000 single `execute()` calls for Source 4.2-4.6 ms
against 1.3-1.6 ms for the same rows batched; old-length lookup 0.8-0.9 ms;
50 Lens upserts 0.22 ms; negative-aggregate check, `DELETE ... WHERE n=0`, meta
update each below 0.02 ms. Only the per-operation Source statements were a
measurable hot spot, so only they (and the per-group Lens upserts) changed: a
same-kind run of operations is now written with multi-row statements of at most
300 rows, in the original order. The other steps were left alone.

| rows | shape | before (median/p95) | after (median/p95) |
| --- | --- | --- | --- |
| 10k | new | 8.56/13.84, 9.0/18.04 | 5.75/9.03, 5.8/8.87 |
| 10k | overwrite | 14.92/20.86, 15.89/21.08 | 6.85/7.74, 6.59/8.73 |
| 10k | delete | 6.94/15.57, 10.68/19.28 | 4.79/9.33, 4.78/7.29 |
| 10k | mixed | 10.91/19.68, 12.0/17.23 | 9.9/12.79, 9.11/11.27 |
| 100k | new | 9.0/12.77, 9.27/19.34 | 5.68/8.78, 7.23/11.35 |
| 100k | overwrite | 19.69/28.71, 20.8/29.56 | 16.07/23.82, 15.52/23.26 |
| 100k | delete | 29.61/39.55, 27.92/34.52 | 19.87/24.46, 23.59/29.42 |
| 100k | mixed | 25.63/34.82, 27.66/37.01 | 23.37/28.83, 24.99/29.7 |
| 1M | new | 9.03/15.45, 9.31/18.47 | 6.62/12.59, 6.46/12.89 |
| 1M | overwrite | 58.37/68.2, 54.18/67.25 | 46.75/61.22, 49.03/68.72 |
| 1M | delete | 65.64/75.12, 70.15/87.37 | 54.45/65.6, 56.8/65.71 |
| 1M | mixed | 42.32/52.36, 44.31/79.33 | 41.07/53.7, 45.88/51.94 |

Reference after the change, same runs (in-memory Lens / Source-only, median ms):
10k new 4.65-4.92 / 7.4-9.9; 100k new 5.12-6.95 / 6.7-7.2; 1M overwrite 43.4-46.8 / 39.7-42.0.
Run-to-run noise on this shared 2-vCPU machine is large (the Source-only rows
differ by up to 2x between runs), so differences of a few ms, such as 1M mixed (the second run is
slightly slower after than before), are not evidence of a change; at 1M the
consistent gains are new keys (about -30%) and delete (about -15-20%), overwrite
is lower in both runs by 5-9 ms. The persisted store is still not faster than
Source-only in every shape. Stored format unchanged (schema version 1).
Note: the benchmark fixture writes rows with raw SQL while the store is closed;
the profile script calls `rebuild()` first. That raw-write-while-closed boundary
is the open owner decision from TASK-012 and is not changed here.

Extra check outside the committed tests (60 seeds 100-159, two stores on one
file applying alternating batches of 3/300/301/900 operations, compared with
Source recomputation after every batch): 0 mismatches. Second 1M series was run
on SHA 5f7309d (after) and main 8b820b2 (before).
