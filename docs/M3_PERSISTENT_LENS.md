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
