# Rust storage v0 (experimental)

`rust/opdb-core/` is an experiment. Its file format is **unstable and has no
compatibility promise**: it may change or be deleted at any time, and no
OpDB data should be kept in it. No permanent on-disk format has been
approved by the owner (see issues #53 and #74).

It is an append-only record log (header with magic and format version,
CRC-32 per record) replayed into an in-memory index on open. It has no WAL,
no compaction or fault-injection testing yet. It has exclusive writable access,
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
