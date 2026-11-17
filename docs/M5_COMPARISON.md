# M5 comparison: OpDB numeric Lens vs plain SQLite (TASK-015)

Script: `experiments/m5_compare.py`. Raw numbers (every run): `experiments/m5_results.json`.
Command: `python experiments/m5_compare.py --sizes 10000 100000 1000000 --seed 15 --runs 15 --json experiments/m5_results.json`

Machine: Intel Xeon 2.10 GHz, 2 CPUs, Linux 6.18 (cloud sandbox, shared), Python 3.13.18,
SQLite 3.53.1, git SHA 632fc0ed5862cb78c27ba6bb729bf9cec7a3b5b4 (plus this PR's files; run on the PR branch head).
All contenders: `journal_mode=WAL`, `synchronous=FULL`. Fixture: seed 15, 1,000 groups,
values uniform in ±2^40, keys `grp<i>/<n>`. Numbers are medians of 15 runs (reads of A/B/C: 200 calls).
Every contender matched an independent Python dict model on all groups before timing and
after the first and last run of each workload. D (a full scan per call) was checked on all
groups before timing and on a seeded sample of 20 groups after each workload.

Contenders: **A** table + index (g,x), aggregate by query. **B** same plus summary table kept by SQL
triggers. **C** OpDB numeric Lens. **D** OpDB Source recomputation (same file as C).

## One-group aggregate read (count, sum, min, max), ms

| rows | A index | B triggers | C Lens | D Source |
| --- | --- | --- | --- | --- |
| 10k | 0.003 | 0.002 | 0.025 | 8.822 |
| 100k | 0.010 | 0.003 | 0.029 | 96.1 |
| 1M | 0.084 | 0.004 | 0.048 | 1051.9 |

## 1,000-row batch, ms (insert = new keys, overwrite, delete)

| rows | workload | A | B | C |
| --- | --- | --- | --- | --- |
| 10k | insert | 4.0 | 5.8 | 9.6 |
| 10k | overwrite | 4.7 | 7.1 | 12.4 |
| 10k | delete | 5.0 | 8.8 | 12.0 |
| 100k | insert | 28.9 | 27.6 | 39.1 |
| 100k | overwrite | 29.6 | 30.8 | 46.2 |
| 100k | delete | 38.4 | 38.5 | 46.1 |
| 1M | insert | 59.0 | 61.3 | 72.2 |
| 1M | overwrite | 77.7 | 83.1 | 94.0 |
| 1M | delete | 75.2 | 84.3 | 87.7 |

## File size (bytes, incl. WAL) and open + first read (ms)

| rows | size A | size B | size C/D | open A | open B | open C/D |
| --- | --- | --- | --- | --- | --- | --- |
| 10k | 1,069,056 | 1,130,496 | 1,163,264 | 0.13 | 0.18 | 0.81 |
| 100k | 8,593,408 | 8,654,848 | 9,101,312 | 0.21 | 0.27 | 1.14 |
| 1M | 85,135,360 | 85,200,896 | 91,082,752 | 0.25 | 0.15 | 0.78 |

## What the numbers say

- Where OpDB wins: against its own Source recomputation (D) the Lens is about 350x to 22,000x faster
  to read, and the answer is checked against Source. That is the M1 claim, repeated here.
- Where OpDB loses to plain SQLite: **writes.** C is slower than A for every batch type and size
  (1.2x to 2.7x; worst case 10k-row overwrite, 12.4 vs 4.7 ms). C is also slower than B, which does
  the same job with triggers (1.0x to 1.8x; at 1M rows delete the two are within 4%). **File size:** C is 7% larger
  than A at 1M rows. **Open:** C opens 3x to 6x slower than A/B, though still about 1 ms and without a rescan.
- Reads: B (trigger summary) is faster than the Lens at every size (0.004 ms vs 0.048 at 1M). A's index
  query beats the Lens at 10k and 100k rows, and loses to it at 1M rows with about 1,000 rows per
  group (0.084 vs 0.048 ms).
- So in this measurement, a developer using plain SQLite with an index or triggers gets equal or
  better write, size and open numbers than the OpDB Lens, and better reads except against the index
  at 1M rows. OpDB's remaining distinguishing property is the Source cross-check and rebuild-on-doubt
  behaviour, which these timings do not measure and which cost the extra write and read work shown above.

## Limits of this comparison

One machine, one fixture shape (1,000 groups, evenly sized), one value range, no concurrency, no
crash/power-loss testing, no cold OS cache, single fixture seed for timing (tests use six seeds).
The 1M insert/overwrite/delete numbers include WAL fsync noise from a shared cloud disk. Only SQLite
(via Python `sqlite3`) and OpDB were measured; nothing here is a claim about any other database.
The bulk fixture load for C bypasses `apply()` and calls `rebuild()` explicitly, because raw writes
to a closed store are not detected by the stored sequence number (known boundary, issue #53).

## TASK-016: where `NumericTruthStore.apply` spends its time (negative result)

No change was made to `opdb/numeric.py`, so there is no before/after table: the
profile below showed nothing removable that is worth the risk. Script:
`python experiments/m16_numeric_profile.py --rows N --batches 30 --seed 16`
(a proxy over the store's SQLite connection times each statement kind; "python"
is the rest of `apply`). Machine: 2 vCPU Intel Xeon @ 2.10 GHz, 8 GB RAM,
Python 3.13.18, SQLite 3.53.1, WAL + synchronous=FULL, one run, 30 batches of
1,000 operations, mean ms per batch (share of the batch):

| rows | workload | batch total (median) | COMMIT | Lens val insert/delete | Source upsert | python |
| --- | --- | --- | --- | --- | --- | --- |
| 10k | insert | 17.3 | 7.1 (39%) | 2.4 (13%) | 2.1 (11%) | 3.6 (19%) |
| 10k | overwrite | 13.2 | 2.5 (17%) | 3.3 (23%) | 1.7 (12%) | 5.0 (34%) |
| 10k | delete | 5.5 | 1.8 (28%) | 0.6 (9%) | - | 2.0 (31%) |
| 100k | insert | 44.3 | 26.1 (59%) | 6.7 (15%) | 5.2 (12%) | 3.1 (7%) |
| 100k | overwrite | 49.0 | 22.8 (47%) | 9.5 (19%) | 5.9 (12%) | 8.1 (17%) |
| 100k | delete | 38.6 | 21.6 (55%) | 4.2 (11%) | - | 6.2 (16%) |
| 1M | insert | 77.0 | 51.1 (66%) | 8.8 (11%) | 10.2 (13%) | 3.3 (4%) |
| 1M | overwrite | 100.1 | 60.4 (60%) | 16.7 (17%) | 10.2 (10%) | 11.0 (11%) |
| 1M | delete | 81.6 | 56.1 (67%) | 7.2 (9%) | - | 8.8 (11%) |

Reading: at 100k and 1M rows the commit (page writes and fsync of the extra
`opdb_nlens_val` and `opdb_nlens_group` trees) is 47-67% of a batch, and cannot
shrink without weakening durability or atomicity. Group lookups, group upserts,
the old-value lookup, the `commit_seq` and Lens meta updates are each at most
5%. The only candidate is the Python part (4-34%, mostly at 10k overwrite),
which would save at best a few ms on a batch; the `WITHOUT ROWID` question was
not touched because it is already used for `opdb_nlens_val`. Statements already
run once per chunk, not once per key. Conclusion: the gap to plain SQLite in
the M5 table is the cost of maintaining a second ordered index, not avoidable
overhead in `apply`. The A and B contenders were not rerun here.

New tests: `tests/test_numeric_write_016.py` (20 seeds against a dict model and
a fresh SQL connection, close/reopen, rollback, overflow, second store and an
outside write).

### TASK-016: repeat of the M5 write workloads (A, B, C), two runs

`opdb/numeric.py` is unchanged, so both runs are the same code (git SHA
`a7d048e6`); they are two independent runs (seeds 15 and 16), not before/after.
Command: `python experiments/m5_compare.py --sizes 10000 100000 1000000 --seed S
--runs 30 --json experiments/results/m16_runN.json`, summarised with
`python experiments/m16_summarize.py run1.json run2.json`. 30 batches of 1,000
operations per cell; milliseconds, median / p95. Same machine as above (2 vCPU
Xeon 2.1 GHz, 8 GB, Python 3.13.18, SQLite 3.53.1, WAL + synchronous=FULL).
Raw numbers: `experiments/results/m16_run1.json`, `m16_run2.json`.
A = covering index, B = trigger summary table, C = numeric Lens.

| run | rows | workload | A med/p95 | B med/p95 | C med/p95 | batches |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 10000 | insert | 3.8 / 6.6 | 5.1 / 8.2 | 9.6 / 15.5 | 30 |
| 1 | 10000 | overwrite | 4.5 / 6.8 | 7.1 / 9.1 | 13.0 / 19.7 | 30 |
| 1 | 10000 | delete | 5.0 / 9.1 | 8.2 / 11.1 | 11.7 / 19.1 | 30 |
| 1 | 100000 | insert | 26.8 / 32.0 | 28.5 / 31.5 | 40.1 / 47.1 | 30 |
| 1 | 100000 | overwrite | 27.8 / 31.7 | 31.9 / 36.8 | 46.4 / 52.5 | 30 |
| 1 | 100000 | delete | 32.9 / 39.5 | 37.4 / 44.0 | 42.6 / 49.5 | 30 |
| 1 | 1000000 | insert | 54.5 / 62.2 | 56.4 / 63.6 | 67.8 / 95.7 | 30 |
| 1 | 1000000 | overwrite | 69.4 / 79.8 | 74.2 / 84.9 | 86.3 / 99.2 | 30 |
| 1 | 1000000 | delete | 67.4 / 75.6 | 73.8 / 80.7 | 77.5 / 87.6 | 30 |
| 2 | 10000 | insert | 3.4 / 5.3 | 5.2 / 6.3 | 9.3 / 11.9 | 30 |
| 2 | 10000 | overwrite | 4.6 / 6.8 | 7.4 / 10.5 | 13.3 / 20.1 | 30 |
| 2 | 10000 | delete | 5.5 / 8.6 | 8.7 / 12.3 | 12.0 / 18.3 | 30 |
| 2 | 100000 | insert | 27.0 / 31.5 | 28.9 / 35.1 | 38.2 / 48.5 | 30 |
| 2 | 100000 | overwrite | 29.7 / 34.0 | 31.9 / 37.3 | 45.9 / 53.3 | 30 |
| 2 | 100000 | delete | 35.3 / 41.1 | 40.8 / 45.9 | 44.0 / 50.2 | 30 |
| 2 | 1000000 | insert | 49.9 / 54.7 | 51.0 / 55.3 | 60.4 / 79.1 | 30 |
| 2 | 1000000 | overwrite | 64.0 / 70.8 | 68.0 / 76.3 | 82.4 / 94.1 | 30 |
| 2 | 1000000 | delete | 66.6 / 72.9 | 71.6 / 82.4 | 75.8 / 89.7 | 30 |

C over A, median, both runs: 2.2x-2.9x at 10k, 1.3x-1.7x at 100k,
1.1x-1.3x at 1M; the two runs differ by up to about 10% for the same cell.
File size at 1M: C is 6-7% larger than A. Open + first read: C 0.6-1.2 ms,
A 0.1-0.4 ms. The earlier TASK-015 numbers are unchanged. Result is the same
as in the profile above: no removable overhead was found.
