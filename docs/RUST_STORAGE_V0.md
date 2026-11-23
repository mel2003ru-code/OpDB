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
