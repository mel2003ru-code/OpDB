# Rust storage v0 (experimental)

`rust/opdb-core/` is an experiment. Its file format is **unstable and has no
compatibility promise**: it may change or be deleted at any time, and no
OpDB data should be kept in it. No permanent on-disk format has been
approved by the owner (see issues #53 and #74).

It is an append-only record log (header with magic and format version,
CRC-32 per record) replayed into an in-memory index on open. It has no WAL,
no compaction. It has exclusive writable access,
but no concurrent transactions.
It does not touch or call the Python engine in `opdb/`.

## TASK-021 measurements (experimental, one VPS)

Measured source SHA: `e9bbefccf421253175667c72fd78d67a0ae86097`. Host: VPS1,
Linux 7.0.0-43-generic, x86_64, Intel Xeon Icelake, 978220 KiB RAM. Toolchain:
rustc/cargo 1.93.1, Python 3.14.4, SQLite 3.46.1. Each row is the median of
three runs; raw per-run values and versions are in the two files under
`docs/bench/`.

Rust v0 results (times for N operations unless identified as sampled per-op):

| N | Value B | put total ms | sampled put p50/p95/p99 µs | get existing/missing ms | cold open after put/final ms | final file MB | peak RSS KiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 16 | 18.057 | 1.439 / 2.022 / 3.945 | 1.937 / 0.456 | 8.815 / 22.061 | 1.320 | 12,804 |
| 10,000 | 256 | 45.273 | 3.866 / 5.839 / 9.910 | 2.869 / 0.502 | 37.050 / 79.032 | 6.120 | 29,832 |
| 100,000 | 16 | 189.610 | 1.427 / 2.076 / 3.666 | 32.577 / 7.856 | 102.826 / 215.531 | 13.200 | 97,560 |
| 100,000 | 256 | 478.512 | 4.020 / 5.985 / 10.509 | 35.035 / 6.901 | 377.193 / 870.741 | 61.200 | 270,708 |

SQLite results on the **same VPS**, using the same seed, keys, order and
independent Python dict oracle:

| N | Value B | put ms | get existing/missing ms | overwrite/delete ms | final file MB | peak RSS KiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 16 | 40.144 | 91.327 / 92.165 | 48.202 / 19.829 | 0.926 | 23,196 |
| 10,000 | 256 | 51.222 | 93.472 / 94.432 | 74.884 / 36.760 | 3.568 | 32,148 |
| 100,000 | 16 | 546.373 | 1,184.544 / 1,004.795 | 790.074 / 304.495 | 9.318 | 62,960 |
| 100,000 | 256 | 574.199 | 1,034.165 / 993.621 | 1,034.497 / 529.958 | 35.647 | 140,840 |

This is a workload record, not a general speed claim. Rust `put` does not sync
each call; `close` calls `sync_all`. SQLite uses `journal_mode=delete`,
`synchronous=FULL`, and one transaction per write phase, so the durability and
commit boundaries differ. Both implementations verify changed overwrites,
deletes, and reopened contents against an independent model. Rust cold-open
timing runs on disk-backed `/dev/sda4`. The harness calls
`posix_fadvise(DONTNEED)` for its private file and verifies page residency with
`mincore`; every measured open had zero resident pages. It does not flush the
VPS-wide page cache. Peak RSS is Linux `VmHWM` after resetting the benchmark
process high-water mark for each configuration; it includes keys and the oracle,
not just the store.

All Rust and SQLite 10k/100k cases completed three times. Rust 1M x 16 B was
skipped before writes because the estimated RAM need was 2.6 GB with about
359 MB available. Rust 1M x 256 B was skipped because estimated disk need was
1.13 GB with about 1.01 GB free; estimated RAM need was 3.2 GB. Thus 1M behavior
remains unmeasured. Results do not use production files or change the
experimental store format.

Exact commands on the measured source:

```text
cd /tmp/opdb-pr85-rust-check && TMPDIR=/opt/opdb-review-87-rust/tmp cargo test --release --offline
cd /tmp/opdb-pr85-rust-check && TMPDIR=/opt/opdb-review-87-rust/tmp cargo run --release --offline --example bench_v0
TMPDIR=/opt/opdb-review-87-rust/tmp python3 /opt/opdb-review-87-rust/bench_sqlite_kv.py --sizes 10000,100000 --value-sizes 16,256 --repeats 3
```

## Experimental exclusive access

Writable `Store` handles now acquire a nonblocking OS file lock before replay
or mutation and retain it through `close` or `Drop`. A second opener of the
same file, including another process or a hard-link alias, returns `Error::Busy`.
On Unix, a forked child can inherit the locked file descriptor until exec;
`flock` is released only after every inherited copy is closed.
This is an advisory `flock` lock on Unix and a Windows file lock; callers that
ignore the lock can still modify the file. No multi-writer transaction support
or stable storage format is implied. `create` continues to fail if the path
already exists.

Creation prepares and locks a temporary file in the same directory, then
publishes it through an atomic hard link. Filesystems without hard-link support
fail closed. An interrupted creation may leave a hidden `.opdb-create-*.tmp`
file; the store path is either absent or has a complete, locked header at the
moment of publication. Such temporary files are not removed automatically.

Run the tests: `cd rust/opdb-core && cargo test`.

## Experimental recovery evidence

The TASK-020 tests construct raw log records with a test-only encoder and
compare replay to a separate `HashMap` model. Every byte offset of five short
put/delete records is tested after a verified prefix, including empty and
binary keys/values. Eight seeded 24-operation put/overwrite/delete prefixes
are tested with nine selected cuts of a larger binary record. A partial
record leaves all preceding complete records visible, reports
`truncated_tail()`, and refuses `put` and `delete`. Explicit `repair()`
truncates to the last complete record; the tests reopen, compare the model,
write again, and reopen a second time.

Complete records with an invalid CRC or operation are rejected as
`Error::Corrupt`. Wrong magic and version are rejected before replay. A
damaged length field can look identical to a truncated tail; this format
cannot prove whether the length or the file was damaged. The tests therefore
require an explicit tail report and deny mutation, but do **not** claim
corruption detection for that case. An extra trailing byte is likewise a
reported incomplete tail.

On Linux, a child process writes a temporary store and waits at three
different points between operations. The parent kills it, reopens the store
in a separate process, and checks that it contains exactly the confirmed
operation prefix. This is a controlled process interruption between writes,
not a power cut or an injected mid-system-call write failure. The byte-cut
tests cover parsing of incomplete records; they do not establish the
filesystem's write atomicity.

`put` does not call `fsync`, and neither successful `put` nor a killed
process proves persistence across power failure. Directory sync after
creation and storage-device failure behavior are also unverified. Do not
store durable user data in this experiment or treat `repair()` as a general
corruption recovery tool. No permanent disk format or WAL decision was made.
