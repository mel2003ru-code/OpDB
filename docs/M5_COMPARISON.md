# M5 comparison: OpDB numeric Lens vs plain SQLite (TASK-015)

Script: `experiments/m5_compare.py`. Raw numbers (every run): `experiments/m5_results.json`.
Command: `python experiments/m5_compare.py --sizes 10000 100000 1000000 --seed 15 --runs 15 --json experiments/m5_results.json`

Machine: Intel Xeon 2.10 GHz, 2 CPUs, Linux 6.18 (cloud sandbox, shared), Python 3.13.18,
SQLite 3.53.1, git SHA a299d78a05c773701e45e94aef36f0c6ecdcdc49 (plus this PR's files).
All contenders: `journal_mode=WAL`, `synchronous=FULL`. Fixture: seed 15, 1,000 groups,
values uniform in ±2^40, keys `grp<i>/<n>`. Numbers are medians of 15 runs (reads of A/B/C: 200 calls).
Every contender matched an independent Python dict model on all groups before timing and
after the first and last run of each workload; D (a full scan per call) was checked on a seeded
sample of 20 groups above 10k rows.

Contenders: **A** table + index (g,x), aggregate by query. **B** same plus summary table kept by SQL
triggers. **C** OpDB numeric Lens. **D** OpDB Source recomputation (same file as C).

## One-group aggregate read (count, sum, min, max), ms

| rows | A index | B triggers | C Lens | D Source |
| --- | --- | --- | --- | --- |
| 10k | 0.003 | 0.002 | 0.029 | 9.877 |
| 100k | 0.011 | 0.003 | 0.031 | 101.0 |
| 1M | 0.060 | 0.002 | 0.023 | 1132.6 |

## 1,000-row batch, ms (insert = new keys, overwrite, delete)

| rows | workload | A | B | C |
| --- | --- | --- | --- | --- |
| 10k | insert | 4.2 | 5.7 | 10.0 |
| 10k | overwrite | 6.1 | 10.2 | 20.1 |
| 10k | delete | 6.1 | 10.3 | 16.9 |
| 100k | insert | 28.2 | 32.1 | 45.3 |
| 100k | overwrite | 29.6 | 34.0 | 46.6 |
| 100k | delete | 33.8 | 43.0 | 49.2 |
| 1M | insert | 61.6 | 66.8 | 74.3 |
| 1M | overwrite | 78.6 | 86.8 | 102.1 |
| 1M | delete | 77.7 | 86.9 | 88.3 |

## File size (bytes, incl. WAL) and open + first read (ms)

| rows | size A | size B | size C/D | open A | open B | open C/D |
| --- | --- | --- | --- | --- | --- | --- |
| 10k | 1,069,056 | 1,130,496 | 1,163,264 | 0.14 | 0.17 | 0.71 |
| 100k | 8,593,408 | 8,654,848 | 9,101,312 | 0.14 | 0.17 | 0.73 |
| 1M | 85,135,360 | 85,200,896 | 91,082,752 | 0.32 | 0.25 | 1.31 |

## What the numbers say

- Where OpDB wins: against its own Source recomputation (D) the Lens is 340x to 49,000x faster
  to read, and the answer is checked against Source. That is the M1 claim, repeated here.
- Where OpDB loses to plain SQLite: **writes.** C is slower than A for every batch type and size
  (1.2x to 3.3x; worst case is 10k-row overwrite, 20.1 vs 6.1 ms). C is also slower than B,
  which does the same job with triggers (1.0x to 2.0x). **File size:** C is 7% larger than A at 1M
  rows. **Open:** C opens 4x to 5x slower than A/B, though still about 1 ms and without a rescan.
- Reads: B (trigger summary) is as fast or faster than the Lens at every size (0.002 ms at 1M vs 0.023);
  A's index query is within a factor of 3 of C at 1M rows with about 1,000 rows per group
  (0.060 vs 0.023 ms) and faster than C at 10k and 100k.
- So in this measurement, a developer using plain SQLite with an index or triggers gets equal or
  better read, write, size and open numbers than the OpDB Lens. OpDB's remaining distinguishing property
  is the Source cross-check and rebuild-on-doubt behaviour, which these timings do not measure and
  which cost the extra write and read work shown above.

## Limits of this comparison

One machine, one fixture shape (1,000 groups, evenly sized), one value range, no concurrency, no
crash/power-loss testing, no cold OS cache, single fixture seed for timing (tests use six seeds).
The 1M insert/overwrite/delete numbers include WAL fsync noise from a shared cloud disk. Only SQLite
(via Python `sqlite3`) and OpDB were measured; nothing here is a claim about any other database.
The bulk fixture load for C bypasses `apply()` and calls `rebuild()` explicitly, because raw writes
to a closed store are not detected by the stored sequence number (known boundary, issue #53).
