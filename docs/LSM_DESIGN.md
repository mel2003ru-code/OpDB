# Rust LSM store: design (M6 stage 1, experimental)

Status: design only, no code. The on-disk format is EXPERIMENTAL and carries no compatibility promise.
Owner decision of 2026-11-26: competitor is SQLite; stage 1 is an LSM tree in Rust aimed at bulk inserts;
stage 2 (a paged B-tree aimed at reads) starts only after stage 1 is measured. The OpDB Lens stays as the
correctness reference and is not touched.

## 1. Goal and honest limits
- Goal: higher bulk-insert throughput than SQLite at the SAME durability, measured by one reproducible benchmark
  (`experiments/bench/`, `docs/benchmarks/`). Nothing here is a speed claim until that benchmark has run.
- Non-goals for stage 1: concurrency, MVCC, secondary indexes, a query language (M7 is undecided), a stable format.
- The earlier Rust v0 (`rust/opdb-core`, an append-only log with an in-memory index) is kept as the simplest reference.
  Its published numbers (`docs/RUST_STORAGE_V0.md`) are NOT comparable with SQLite: `put` does not fsync.

## 2. Durability contract (the part that decides whether a comparison is fair)
- `Db::write_batch(ops)` appends ONE WAL record and, with `SyncPolicy::EveryBatch`, calls `sync_data` before it
  returns. This is the equivalent of one SQLite commit under `synchronous=FULL` and is the ONLY mode the published
  benchmark uses. `SyncPolicy::OnClose` and `Never` exist for experiments and are reported as separate rows.
- A write that returned `Ok` under `EveryBatch` must survive a killed process (test L14). A power-loss claim is not made:
  tests simulate process kill and torn tails only.

## 3. Components
1. **Memtable**: sorted map `key -> Option<value>` (`None` is a tombstone), byte-ordered keys, size accounting; frozen and
   flushed when it reaches 4 MiB.
2. **WAL**: one segment per memtable. Record = the existing experimental record layout (`kind u8, key len u32, value len
   u32, key, value, crc32`); a batch is ONE record of kind 3 whose value is `encode_ops(ops)` (`rust/opdb-core`
   TASK-028), so the length framing and the CRC protect the batch as a unit. A torn tail is detected on open and cut by
   `repair`, exactly as in the v0 store.
3. **SSTable**: immutable file, sorted entries in data blocks of about 4 KiB, then an index block (first key of each
   block and its offset), then a footer (magic, format version, index offset, entry count, crc32 of the footer). Written
   to `name.tmp`, synced, renamed. No Bloom filter in stage 1 (a later, measured addition).
4. **Manifest**: the list of live SSTables (file name, level, sequence number). Updated by writing `MANIFEST.tmp`,
   `sync`, `rename`, `sync` of the directory. The manifest is the single source of truth for which files are live.
5. **Compaction (stage 1)**: size-tiered. When 4 or more SSTables exist, merge all of them into one, newest entry wins,
   tombstones are dropped because nothing older remains. The new file is installed through the manifest; old files are
   deleted after the manifest update.
6. **Recovery on open**: read the manifest; open every listed SSTable (verify footer and index); replay every WAL
   segment newer than the manifest (cut a torn tail and report it); delete orphan `*.tmp` files and SSTables that the
   manifest does not list. A damaged SSTable or WAL record is `Error::Corrupt` with the file name and offset, never a
   silent wrong answer.

## 4. Read path
`get`: memtable, then the frozen memtable, then SSTables from newest to oldest; the first hit wins, a tombstone ends the
search with `None`. `scan(prefix)`: a merge iterator over the same sources with newest-wins and tombstone suppression.

## 5. Crate layout and an open prerequisite
New crate `rust/opdb-lsm/` (standard library only): `src/lib.rs`, `src/ops.rs`, `src/memtable.rs`, `src/wal.rs`,
`src/sstable.rs`, `src/manifest.rs`, `src/compaction.rs`, `src/db.rs`, tests under `tests/`.
**Prerequisite that needs the owner:** the controller and its Rust sandbox currently accept only
`rust/opdb-core/{src/lib.rs, tests/*.rs, examples/*.rs}` with a fixed `Cargo.toml`, and one PR may return at most 600
lines. A multi-file second crate (and the CI line that runs its tests, a protected `.github/` change) cannot be built by
the free-model pipeline until that is extended. Until then the tasks below stay `BLOCKED_OWNER`.

## 6. Failure and recovery test plan (green CI is not proof of correctness)
- Model-based fuzz against `BTreeMap`: random batches, reads, reopen, flush and compaction at random points.
- Torn WAL tail: cut the last record at EVERY interior offset; the store opens, reports the tail, equals the state before
  that record, and accepts writes after `repair`.
- Single-byte corruption of EVERY byte of a WAL segment, an SSTable and the manifest: never silent (the same invariant as
  research hypothesis R-RUST-02).
- Crash between "SSTable written" and "manifest updated" and between "manifest updated" and "old files deleted":
  recovery yields the pre-flush or the post-flush state, never a mix, and removes the orphans.
- Kill test: a child process writes under `EveryBatch`, is killed right after a write returned, the parent reopens and
  every acknowledged write is present.

## 7. Task breakdown (each task one PR, each with a reference-checkable acceptance test)
| ID | Task | Acceptance |
| --- | --- | --- |
| L01 | crate skeleton, `Op`, `encode_ops` / `decode_ops` copied from v0 | round-trip and malformed-input tests |
| L02 | memtable: put, get, delete (tombstone), sorted iteration, size accounting | model equality (BTreeMap), 20 seeds |
| L03 | WAL writer: append a batch record, sync policy | exact bytes of a record, CRC covers the batch |
| L04 | WAL reader and replay, torn-tail detection and `repair` | every-cut and every-byte-corruption tests |
| L05 | `Db` over memtable + WAL: `write_batch`, `get`, reopen replays | model equality across reopen, 20 seeds |
| L06 | SSTable writer: sorted entries to blocks, index, footer, temp file and rename | file layout test, reopen reads back |
| L07 | SSTable reader: `get` by binary search of the index, iteration, corruption detection | every-byte corruption never silent |
| L08 | flush: memtable to SSTable, manifest update, WAL segment rotation | state equal before and after flush |
| L09 | read path across memtable and SSTables with tombstone shadowing | model equality with overwrites and deletes |
| L10 | size-tiered compaction (merge all, drop tombstones, install via manifest) | model equality, file count shrinks |
| L11 | recovery of orphans and half-finished flush or compaction | both crash-point tests above |
| L12 | `scan(prefix)` merge iterator | model equality, newest wins |
| L13 | research hypothesis R-RUST-03: model-based fuzz of the whole Db (template under `research/rust/`) | harness self-test fails when it should |
| L14 | kill test under `EveryBatch` | every acknowledged write survives |
| L15 | benchmark adapter (an `examples/` binary) and its contender in `experiments/bench/` | verified rows, same data and settings as SQLite |
After L15 the benchmark (`docs/benchmarks/`) decides whether stage 2 is worth starting.

## 8. Decisions that stay with the owner
- The durability equivalence in section 2 (SQLite `synchronous=FULL` versus `EveryBatch`).
- Extending the sandbox and CI for a multi-file second crate (section 5).
- Approval of any permanent on-disk format (stage 1 is experimental).
