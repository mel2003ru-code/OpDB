"""TASK-014 research prototype: numeric Lens (count, sum, min, max per group).

Values are 8-byte big-endian signed integers. Groups come from a named,
deterministic caller function registered at open; the name is stored in the
file. Source rows, per-group aggregates, an ordered per-group value index and
both sequence numbers change in ONE SQLite transaction. See
docs/M4_NUMERIC_LENS.md for the cost of min/max and the threat boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import time
from typing import Callable, Literal

from .core import SourceIntegrityError, TruthStore, _key, _validate_ops
from .lens import group_of

SCHEMA_VERSION = 1
INT64_MIN, INT64_MAX = -(1 << 63), (1 << 63) - 1
_CHUNK = 300     # rows per multi-row statement (<= 900 bound parameters)


class LensOverflow(Exception):
    """A group sum left the signed 64-bit range: the Lens must not be used."""


@dataclass(frozen=True)
class NumericStats:
    count: int
    total: int
    minimum: int | None
    maximum: int | None
    served_from: Literal["LENS", "SOURCE"]


def _decode(value: object) -> int:
    if type(value) is not bytes or len(value) != 8:
        raise SourceIntegrityError("numeric Source value is not an 8-byte BLOB")
    return int.from_bytes(value, "big", signed=True)


def _group(fn: Callable[[str], str], key: str) -> str:
    g = fn(key)
    if type(g) is not str or "\x00" in g:
        raise ValueError("grouping function must return str without NUL")
    try:
        g.encode("utf-8")
    except UnicodeError as exc:
        raise ValueError("grouping function returned invalid UTF-8") from exc
    return g


def _scan(db: sqlite3.Connection, fn):
    """Yield (group, key, int) for every Source row; refuse anything else."""
    for key, kind, value in db.execute("SELECT k,typeof(v),v FROM opdb_source_kv"):
        try:
            _key(key)
        except ValueError as exc:
            raise SourceIntegrityError("invalid source key") from exc
        if kind != "blob":
            raise SourceIntegrityError("non-BLOB source value")
        yield _group(fn, key), key, _decode(value)


class NumericTruthStore(TruthStore):
    def __init__(self, path, *, groupers=None, grouping="prefix"):
        super().__init__(path, lens=False)
        self._groupers = dict(groupers) if groupers else {"prefix": group_of}
        self.open_mode = "SOURCE_FALLBACK"   # PERSISTED | REBUILT | SOURCE_FALLBACK
        self.open_reason = ""
        self.open_ns = 0
        self._trusted = False
        self._dv = None
        self._failed = None                  # (seq, data_version) of a failed rebuild
        try:
            if grouping not in self._groupers or not callable(self._groupers[grouping]):
                raise ValueError("grouping name is not a registered function")
            self._name = grouping
            self._fn = self._groupers[grouping]
            started = time.perf_counter_ns()
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_nlens_group (g TEXT PRIMARY KEY "
                "COLLATE BINARY NOT NULL, n INTEGER NOT NULL, s INTEGER NOT NULL)")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_nlens_val (g TEXT NOT NULL "
                "COLLATE BINARY, x INTEGER NOT NULL, k TEXT NOT NULL COLLATE "
                "BINARY, PRIMARY KEY (g,x,k)) WITHOUT ROWID")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_nlens_meta (singleton INTEGER "
                "PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL, "
                "lens_seq INTEGER NOT NULL, grouping TEXT NOT NULL, "
                "tot_n INTEGER NOT NULL)")
            reason = self._validate()
            if reason is None:
                self._trusted, self.open_mode = True, "PERSISTED"
                self._dv = self._data_version()
            else:
                self.open_reason = reason
                self._rebuild_or_fallback()
                if self._trusted:
                    self.open_mode = "REBUILT"
            self.open_ns = time.perf_counter_ns() - started
        except BaseException:
            self.close()
            raise

    def _data_version(self) -> int:
        return self._db.execute("PRAGMA data_version").fetchone()[0]

    def _seq(self) -> int:
        return self._db.execute(
            "SELECT commit_seq FROM opdb_meta WHERE singleton=1").fetchone()[0]

    def _validate(self) -> str | None:
        """Bounded: reads only opdb_meta, opdb_nlens_meta, opdb_nlens_group."""
        meta = self._db.execute(
            "SELECT schema_version,lens_seq,grouping,tot_n FROM opdb_nlens_meta"
        ).fetchone()
        if meta is None:
            return "missing metadata"
        if meta[0] != SCHEMA_VERSION:
            return "incompatible schema version"
        if meta[2] != self._name:
            return "grouping function changed"
        if any(type(meta[i]) is not int for i in (0, 1, 3)) or type(self._seq()) is not int:
            return "malformed metadata"
        if meta[1] != self._seq():
            return "stale generation"
        n = 0
        for g, gn, gs in self._db.execute("SELECT g,n,s FROM opdb_nlens_group"):
            if type(g) is not str or type(gn) is not int or type(gs) is not int \
                    or gn <= 0 or not INT64_MIN <= gs <= INT64_MAX:
                return "corrupt Lens row"
            n += gn
        if n != meta[3]:
            return "Lens rows disagree with stored totals"
        return None

    def _rebuild_or_fallback(self) -> None:
        self._trusted = False
        try:
            self.rebuild()
            self._failed = None
        except (sqlite3.DatabaseError, SourceIntegrityError, LensOverflow,
                ValueError, TypeError) as exc:
            self.open_reason += f"; rebuild failed: {exc}"
            self._failed = (self._seq(), self._data_version())

    def rebuild(self) -> None:
        """Rescan Source; replace all Lens tables in one atomic transaction."""
        self._trusted = False
        with self._lock:
            self._ensure_open()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                groups: dict[str, list[int]] = {}
                vals = []
                for g, k, x in _scan(self._db, self._fn):
                    p = groups.setdefault(g, [0, 0])
                    p[0] += 1
                    p[1] += x
                    vals.append((g, x, k))
                if any(not INT64_MIN <= p[1] <= INT64_MAX for p in groups.values()):
                    raise LensOverflow("group sum outside signed 64-bit range")
                self._db.execute("DELETE FROM opdb_nlens_group")
                self._db.execute("DELETE FROM opdb_nlens_val")
                self._db.executemany(
                    "INSERT INTO opdb_nlens_group VALUES (?,?,?)",
                    ((g, p[0], p[1]) for g, p in groups.items()))
                self._db.executemany("INSERT INTO opdb_nlens_val VALUES (?,?,?)", vals)
                self._db.execute(
                    "INSERT OR REPLACE INTO opdb_nlens_meta VALUES (1,?,?,?,?)",
                    (SCHEMA_VERSION, self._seq(), self._name, len(vals)))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._trusted = True
            self._dv = self._data_version()

    def _refresh(self) -> None:
        """Any commit by another connection is unverified: rebuild from Source.
        After a failed rebuild, retry only when something has changed."""
        if self._trusted and self._data_version() == self._dv:
            return
        if self._trusted or self._failed != (self._seq(), self._data_version()):
            self._rebuild_or_fallback()

    @property
    def lens_enabled(self) -> bool:
        with self._lock:
            self._ensure_open()
            self._refresh()
            return self._trusted

    # -- reads ----------------------------------------------------------
    def numeric_stats_source(self, group: str) -> NumericStats:
        """Reference answer: scan Source, plain Python ints (no overflow)."""
        with self._lock:
            self._ensure_open()
            xs = [x for g, _k, x in _scan(self._db, self._fn) if g == group]
        return NumericStats(len(xs), sum(xs), min(xs, default=None),
                            max(xs, default=None), "SOURCE")

    def _extreme(self, group: str, order: str):
        row = self._db.execute(
            f"SELECT x,k FROM opdb_nlens_val WHERE g=? ORDER BY x {order} LIMIT 1",
            (group,)).fetchone()
        if row is None:
            return None
        # Cheap cross-check against Source: the entry must still be true.
        src = self._db.execute(
            "SELECT typeof(v),v FROM opdb_source_kv WHERE k=?", (row[1],)).fetchone()
        if src is None or src[0] != "blob" or _decode(src[1]) != row[0] \
                or _group(self._fn, row[1]) != group:
            raise SourceIntegrityError("Lens value index disagrees with Source")
        return row[0]

    def numeric_stats(self, group: str) -> NumericStats:
        group = _group(lambda g: g, group)
        with self._lock:
            self._ensure_open()
            self._refresh()
            if self._trusted:
                try:
                    row = self._db.execute(
                        "SELECT n,s FROM opdb_nlens_group WHERE g=?", (group,)
                    ).fetchone()
                    if row is None:
                        return NumericStats(0, 0, None, None, "LENS")
                    lo, hi = self._extreme(group, "ASC"), self._extreme(group, "DESC")
                    if lo is None or hi is None:
                        raise SourceIntegrityError("group without value index")
                    return NumericStats(row[0], row[1], lo, hi, "LENS")
                except (SourceIntegrityError, sqlite3.DatabaseError):
                    self._trusted = False
                    self._failed = None
            return self.numeric_stats_source(group)

    # -- writes ---------------------------------------------------------
    def apply(self, operations) -> None:
        checked = _validate_ops(operations)
        for item in checked:
            if item[0] == "put" and len(item[2]) != 8:
                raise ValueError("numeric Lens values must be 8-byte big-endian ints")
        with self._lock:
            self._ensure_open()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                trusted = self._trusted and self._data_version() == self._dv
                overflow = False
                if trusted:
                    final = {}                      # key -> final int or None
                    for it in checked:
                        final[it[1]] = _decode(it[2]) if it[0] == "put" else None
                    old = {}
                    keys = tuple(final)
                    for i in range(0, len(keys), 500):
                        chunk = keys[i:i + 500]
                        for k, kind, v in self._db.execute(
                                "SELECT k,typeof(v),v FROM opdb_source_kv WHERE k IN "
                                f"({','.join('?' * len(chunk))})", chunk):
                            if kind != "blob":
                                raise SourceIntegrityError("non-BLOB source value")
                            old[k] = _decode(v)
                    gnames = {k: _group(self._fn, k) for k in keys}
                    removes, adds, delta = [], [], {}
                    for k in keys:
                        o, n_ = old.get(k), final[k]
                        if o == n_:
                            continue
                        d = delta.setdefault(gnames[k], [0, 0])
                        if o is not None:
                            removes.append((gnames[k], o, k)); d[0] -= 1; d[1] -= o
                        if n_ is not None:
                            adds.append((gnames[k], n_, k)); d[0] += 1; d[1] += n_
                    current = {}
                    names = tuple(delta)
                    for i in range(0, len(names), 500):
                        chunk = names[i:i + 500]
                        for g, n, s in self._db.execute(
                                "SELECT g,n,s FROM opdb_nlens_group WHERE g IN "
                                f"({','.join('?' * len(chunk))})", chunk):
                            current[g] = (n, s)
                    new_rows = {}
                    for g, (dn, ds) in delta.items():
                        n, s = current.get(g, (0, 0))
                        n, s = n + dn, s + ds
                        if n < 0:
                            raise SourceIntegrityError("negative Lens count")
                        if not INT64_MIN <= s <= INT64_MAX:
                            overflow = True
                        new_rows[g] = (n, s)
                runs: list[list] = []
                for item in checked:
                    if not runs or runs[-1][0] != item[0]:
                        runs.append([item[0], []])
                    runs[-1][1].append(item)
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
                if trusted and not overflow:
                    deleted = 0
                    for i in range(0, len(removes), _CHUNK):
                        part = removes[i:i + _CHUNK]
                        deleted += self._db.execute(
                            "DELETE FROM opdb_nlens_val WHERE (g,x,k) IN (VALUES "
                            + ",".join(["(?,?,?)"] * len(part)) + ")",
                            [x for r in part for x in r]).rowcount
                    if deleted != len(removes):
                        raise SourceIntegrityError("Lens value index missing entries")
                    for i in range(0, len(adds), _CHUNK):
                        part = adds[i:i + _CHUNK]
                        self._db.execute(
                            "INSERT INTO opdb_nlens_val VALUES "
                            + ",".join(["(?,?,?)"] * len(part)),
                            [x for r in part for x in r])
                    live = [(g, n, s) for g, (n, s) in new_rows.items() if n > 0]
                    for i in range(0, len(live), _CHUNK):
                        part = live[i:i + _CHUNK]
                        self._db.execute(
                            "INSERT OR REPLACE INTO opdb_nlens_group VALUES "
                            + ",".join(["(?,?,?)"] * len(part)),
                            [x for r in part for x in r])
                    gone = [g for g, (n, _s) in new_rows.items() if n == 0]
                    for i in range(0, len(gone), 500):
                        part = gone[i:i + 500]
                        self._db.execute(
                            "DELETE FROM opdb_nlens_group WHERE g IN ("
                            + ",".join("?" * len(part)) + ")", part)
                    self._db.execute(
                        "UPDATE opdb_nlens_meta SET lens_seq=?, tot_n=tot_n+?",
                        (self._seq(), len(adds) - len(removes)))
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                self._trusted = False       # state unknown: re-verify on next read
                self._failed = None
                raise
            if trusted and overflow:
                # Source is committed; the stored Lens is now one generation
                # behind, so it stays untrusted (reopen rebuilds or falls back).
                self._trusted = False
                self._failed = (self._seq(), self._data_version())
            elif not trusted:
                self._trusted = False
