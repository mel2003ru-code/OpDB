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
