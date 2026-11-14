"""TASK-012 research prototype: Lens stored in the same SQLite file as Source.

Opt-in. Source rows, per-group aggregates and the commit sequence change in
ONE SQLite transaction. This is NOT the native OpDB format. See
docs/M3_PERSISTENT_LENS.md for the exact threat boundary.
"""
from __future__ import annotations

import sqlite3
import time

from .core import (GroupStats, SourceIntegrityError, TruthStore, _key,
                   _validate_ops)
from .lens import _metric, group_of, source_stats

SCHEMA_VERSION = 1
_CHUNK = 300     # rows per multi-row statement (<= 900 bound parameters)


class PersistentTruthStore(TruthStore):
    def __init__(self, path, *, trace=None):
        super().__init__(path, lens=False)
        self.open_mode = "SOURCE_FALLBACK"   # PERSISTED | REBUILT | SOURCE_FALLBACK
        self.open_reason = ""
        self.open_ns = 0
        self.open_vm_steps = 0
        self._trusted = False
        self._dv = None
        try:
            started = time.perf_counter_ns()
            if trace is not None:
                self._db.set_trace_callback(trace)
            steps = [0]

            def tick():
                steps[0] += 1000
                return 0
            self._db.set_progress_handler(tick, 1000)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_lens_group (g TEXT PRIMARY KEY "
                "COLLATE BINARY NOT NULL, n INTEGER NOT NULL, b INTEGER NOT NULL)")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_lens_meta (singleton INTEGER "
                "PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL, "
                "lens_seq INTEGER NOT NULL, tot_n INTEGER NOT NULL, "
                "tot_b INTEGER NOT NULL)")
            reason = self._validate()
            if reason is None:
                self._trusted, self.open_mode = True, "PERSISTED"
                self._dv = self._data_version()
            else:
                self.open_reason = reason
                self._rebuild_or_fallback()
                if self._trusted:
                    self.open_mode = "REBUILT"
            self._db.set_progress_handler(None, 0)
            self._db.set_trace_callback(None)
            self.open_vm_steps = steps[0]
            self.open_ns = time.perf_counter_ns() - started
        except BaseException:
            self.close()
            raise

    # -- verification -------------------------------------------------
    def _data_version(self) -> int:
        return self._db.execute("PRAGMA data_version").fetchone()[0]

    def _validate(self) -> str | None:
        """Bounded checks: touch only opdb_meta, opdb_lens_meta, opdb_lens_group
        (size = number of groups). Never reads opdb_source_kv. Returns the
        reason the stored Lens is untrusted, or None."""
        meta = self._db.execute(
            "SELECT schema_version,lens_seq,tot_n,tot_b FROM opdb_lens_meta"
        ).fetchone()
        if meta is None:
            return "missing metadata"
        if meta[0] != SCHEMA_VERSION:
            return "incompatible schema version"
        seq = self._db.execute(
            "SELECT commit_seq FROM opdb_meta WHERE singleton=1").fetchone()
        if seq is None or any(type(x) is not int for x in (*meta, seq[0])):
            return "malformed metadata"
        if meta[1] != seq[0]:
            return "stale generation"
        n = b = 0
        for g, gn, gb in self._db.execute("SELECT g,n,b FROM opdb_lens_group"):
            if type(g) is not str or type(gn) is not int or type(gb) is not int \
                    or gn <= 0 or gb < 0:
                return "corrupt Lens row"
            n += gn
            b += gb
        if (n, b) != (meta[2], meta[3]):
            return "Lens rows disagree with stored totals"
        return None

    def _rebuild_or_fallback(self) -> None:
        self._trusted = False
        try:
            self.rebuild()
        except (sqlite3.DatabaseError, SourceIntegrityError) as exc:
            self.open_reason += f"; rebuild failed: {exc}"

    def rebuild(self) -> None:
        """Rescan Source and replace the stored Lens in one atomic transaction.
        An interrupted rebuild rolls back completely (old rows stay untrusted)."""
        self._trusted = False
        with self._lock:
            self._ensure_open()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                counts: dict[str, list[int]] = {}
                for row in self._db.execute(
                        "SELECT k,typeof(v),length(v) FROM opdb_source_kv"):
                    key, size = _metric(row)
                    pair = counts.setdefault(group_of(key), [0, 0])
                    pair[0] += 1
                    pair[1] += size
                seq = self._db.execute(
                    "SELECT commit_seq FROM opdb_meta WHERE singleton=1"
                ).fetchone()[0]
                self._db.execute("DELETE FROM opdb_lens_group")
                self._db.executemany(
                    "INSERT INTO opdb_lens_group(g,n,b) VALUES (?,?,?)",
                    ((g, p[0], p[1]) for g, p in counts.items()))
                self._db.execute(
                    "INSERT OR REPLACE INTO opdb_lens_meta VALUES (1,?,?,?,?)",
                    (SCHEMA_VERSION, seq, sum(p[0] for p in counts.values()),
                     sum(p[1] for p in counts.values())))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._trusted = True
            self._dv = self._data_version()

    def _refresh(self) -> None:
        """Called under the lock before using the Lens. Any commit by another
        connection (data_version change) is treated as unverified: re-validate,
        and rebuild from Source if the stored Lens cannot be shown consistent."""
        if self._trusted and self._data_version() == self._dv:
            return
        # A foreign commit may be a raw Source write that touched no Lens
        # row, so bounded checks alone cannot clear it: always rebuild.
        self._rebuild_or_fallback()

    # -- reads / writes -------------------------------------------------
    @property
    def lens_enabled(self) -> bool:
        with self._lock:
            self._ensure_open()
            self._refresh()
            return self._trusted

    def group_stats(self, group: str) -> GroupStats:
        group = _key(group, allow_empty=True)
        with self._lock:
            self._ensure_open()
            self._refresh()
            if not self._trusted:
                return source_stats(self._db, group)
            row = self._db.execute(
                "SELECT n,b FROM opdb_lens_group WHERE g=?", (group,)).fetchone()
            return GroupStats(*(row or (0, 0)), "LENS")

    def apply(self, operations) -> None:
        checked = _validate_ops(operations)
        with self._lock:
            self._ensure_open()
            self._refresh()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                trusted = self._trusted and self._data_version() == self._dv
                deltas: dict[str, list[int]] = {}
                if trusted:
                    lengths = dict.fromkeys(item[1] for item in checked)
                    keys = tuple(lengths)
                    for i in range(0, len(keys), 500):
                        chunk = keys[i:i + 500]
                        for row in self._db.execute(
                                "SELECT k,typeof(v),length(v) FROM opdb_source_kv "
                                f"WHERE k IN ({','.join('?' * len(chunk))})", chunk):
                            key, size = _metric(row)
                            lengths[key] = size
                runs: list[list] = []     # contiguous same-kind runs, in order
                for item in checked:
                    if trusted:
                        d = deltas.setdefault(group_of(item[1]), [0, 0])
                        old = lengths[item[1]]
                        if old is not None:
                            d[0] -= 1
                            d[1] -= old
                        new = len(item[2]) if item[0] == "put" else None
                        if new is not None:
                            d[0] += 1
                            d[1] += new
                        lengths[item[1]] = new
                    if not runs or runs[-1][0] != item[0]:
                        runs.append([item[0], []])
                    runs[-1][1].append(item)
                # One multi-row statement per <=300 rows of a same-kind run
                # (bound-parameter limit 999). Rows apply in order, so repeated
                # keys behave as in a one-by-one loop; far fewer statements are
                # prepared than with one execute() per operation.
                for kind, run in runs:
                    for i in range(0, len(run), _CHUNK):
                        part = run[i:i + _CHUNK]
                        if kind == "put":
                            self._db.execute(
                                "INSERT INTO opdb_source_kv(k,v) VALUES "
                                + ",".join(["(?,?)"] * len(part))
                                + " ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                                [x for it in part for x in (it[1], it[2])])
                        else:
                            self._db.execute(
                                "DELETE FROM opdb_source_kv WHERE k IN ("
                                + ",".join("?" * len(part)) + ")",
                                [it[1] for it in part])
                self._db.execute(
                    "UPDATE opdb_meta SET commit_seq=commit_seq+1 WHERE singleton=1")
                if trusted:
                    changed = [(g, dn, db_) for g, (dn, db_) in deltas.items()
                               if dn or db_]
                    for i in range(0, len(changed), _CHUNK):
                        part = changed[i:i + _CHUNK]
                        self._db.execute(
                            "INSERT INTO opdb_lens_group(g,n,b) VALUES "
                            + ",".join(["(?,?,?)"] * len(part))
                            + " ON CONFLICT(g) DO UPDATE SET "
                            "n=n+excluded.n, b=b+excluded.b",
                            [x for row in part for x in row])
                    if self._db.execute(
                            "SELECT 1 FROM opdb_lens_group WHERE n<0 OR b<0 "
                            "LIMIT 1").fetchone():
                        raise SourceIntegrityError("negative Lens aggregate")
                    self._db.execute("DELETE FROM opdb_lens_group WHERE n=0")
                    tn = sum(d[0] for d in deltas.values())
                    tb = sum(d[1] for d in deltas.values())
                    self._db.execute(
                        "UPDATE opdb_lens_meta SET lens_seq=(SELECT commit_seq "
                        "FROM opdb_meta WHERE singleton=1), tot_n=tot_n+?, "
                        "tot_b=tot_b+?", (tn, tb))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                if trusted:      # state unknown after an error: re-verify next use
                    self._trusted = False
                raise
