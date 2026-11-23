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

Measured source SHA: `240adaa7283300ab7e72e343b6931b445de748c6`. Host: VPS1,
Linux 7.0.0-43-generic, x86_64, Intel Xeon Icelake, 978220 KiB RAM. Toolchain:
rustc/cargo 1.93.1, Python 3.14.4, SQLite 3.46.1. Each row is the median of
three runs; raw per-run values and versions are in the two files under
`docs/bench/`.

Rust v0 results (times for N operations unless identified as sampled per-op):

| N | Value B | put total ms | sampled put p50/p95/p99 µs | get existing/missing ms | cold open after put/final ms | final file MB | peak RSS KiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 16 | 18.194 | 1.266 / 1.888 / 3.388 | 2.232 / 0.502 | 8.716 / 20.197 | 1.320 | 12,756 |
| 10,000 | 256 | 44.098 | 3.806 / 5.339 / 9.758 | 3.636 / 0.556 | 36.833 / 74.700 | 6.120 | 29,784 |
| 100,000 | 16 | 163.668 | 1.271 / 1.838 / 2.989 | 32.499 / 6.890 | 84.237 / 210.702 | 13.200 | 97,508 |
| 100,000 | 256 | 491.079 | 3.904 / 5.415 / 10.494 | 38.034 / 7.021 | 402.095 / 777.946 | 61.200 | 270,676 |

SQLite results on the **same VPS**, using the same seed, keys, order and
independent Python dict oracle:

| N | Value B | put ms | get existing/missing ms | overwrite/delete ms | final file MB | peak RSS KiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 16 | 32.204 | 86.303 / 90.269 | 38.223 / 15.860 | 0.926 | 23,080 |
| 10,000 | 256 | 37.177 | 98.078 / 97.034 | 52.071 / 26.256 | 3.568 | 32,144 |
| 100,000 | 16 | 493.866 | 1,201.253 / 1,160.926 | 704.585 / 330.988 | 9.318 | 63,804 |
| 100,000 | 256 | 525.468 | 1,127.548 / 1,089.078 | 876.231 / 333.271 | 35.647 | 140,572 |

This is a workload record, not a general speed claim. Rust `put` does not sync
each call; `close` calls `sync_all`. SQLite uses `journal_mode=delete`,
`synchronous=FULL`, and one transaction per write phase, so the durability and
commit boundaries differ. Both implementations verify changed overwrites,
deletes, and reopened contents against an independent model. Rust cold-open
timing follows a successful per-file `dd iflag=nocache` cache-drop request;
the harness does not flush the VPS-wide page cache. Peak RSS is Linux `VmHWM`
after resetting the benchmark process high-water mark for each configuration;
it includes keys and the oracle, not just the store.

All 10k/100k cases completed three times. All six Rust 1M cases were skipped
before writes because `/tmp` had 143,155,200 free bytes: estimated peaks were
228,750,018 bytes for 16 B values and 1,128,750,018 bytes for 256 B values.
Thus 1M behavior remains unmeasured. Results do not use production files or
change the experimental store format.

Exact commands on the measured source:

```text
cd /tmp/opdb-pr85-rust-check && cargo test --release --offline
cd /tmp/opdb-pr85-rust-check && cargo run --release --offline --example bench_v0
python3 /opt/opdb-review-87-rust/bench_sqlite_kv.py --sizes 10000,100000 --value-sizes 16,256 --repeats 3
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
