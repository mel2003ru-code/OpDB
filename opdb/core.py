"""OpDB Core experiment 0.1: SQLite-backed authoritative KV and disposable Lens.

Not a native DBMS, no SQL compatibility, no verified change capture.
All user reads use SQLite directly. No derived-Lens admission exists because
external privileged writers can bypass/forge SQLite trigger logs (P0 #21).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from itertools import islice
from pathlib import Path
import sqlite3
import threading
import time
from typing import Iterable, Literal

MAX_KEY_UTF8 = 512
MAX_VALUE_BYTES = 1024 * 1024
MAX_BATCH = 10000
MAX_BATCH_BYTES = 8 * 1024 * 1024
MAX_SCAN = 1000

@dataclass(frozen=True)
class SourceSnapshot:
    rows: tuple[tuple[str, bytes], ...]
    digest_sha256: str
    row_count: int

@dataclass(frozen=True)
class GroupStats:
    row_count: int
    value_bytes: int
    served_from: Literal["LENS", "SOURCE"]

@dataclass(frozen=True)
class LensCandidate:
    """Untrusted, disposable read-only image; NEVER used by public reads."""
    rows: tuple[tuple[str, bytes], ...]
    source_digest_sha256: str
    build_ns: int

@dataclass(frozen=True)
class Admission:
    accepted: Literal[False]
    mode: Literal["SOURCE_ONLY"]
    reason: str

def _key(value: object, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or "\x00" in value:
        raise ValueError("key must be valid UTF-8 text without NUL")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError as exc:
        raise ValueError("key must be valid UTF-8") from exc
    if size > MAX_KEY_UTF8 or (size == 0 and not allow_empty):
        raise ValueError("key must have 1..512 UTF-8 bytes")
    return value

def _value(value: object) -> bytes:
    if type(value) is not bytes or len(value) > MAX_VALUE_BYTES:
        raise ValueError("value must be bytes up to 1 MiB")
    return value

def _digest(rows: tuple[tuple[str, bytes], ...]) -> str:
    digest = hashlib.sha256()
    digest.update(len(rows).to_bytes(8, "big"))
    for key, value in rows:
        raw = key.encode("utf-8")
        digest.update(len(raw).to_bytes(4, "big"))
        digest.update(raw)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()

class SourceIntegrityError(RuntimeError):
    """Underlying SQLite source row violates the typed KV read contract."""


def _source_row(row: tuple) -> tuple[str, bytes]:
    """Reject unexpected SQLite storage types without coercing integers to bytes.

    The SQL read projection avoids loading external BLOBs bigger than 1 MiB;
    row = (key, safe_blob_or_null, sqlite_typeof, sqlite_length).
    This guards the Core API but does NOT authenticate a privileged writer.
    """
    key, value, storage, size = row
    if type(key) is not str:
        raise SourceIntegrityError("invalid source key: not UTF-8 text")
    try:
        _key(key)
    except ValueError as exc:
        raise SourceIntegrityError("invalid source key: outside typed KV contract") from exc
    if storage != "blob":
        raise SourceIntegrityError("non-BLOB source value; refuse unsafe conversion")
    if type(size) is not int or size < 0 or size > MAX_VALUE_BYTES:
        raise SourceIntegrityError("oversized or malformed source BLOB")
    if type(value) is not bytes or len(value) != size:
        raise SourceIntegrityError("invalid source BLOB representation")
    return key, value


class TruthStore:
    """Single-process research API. SQLite remains authoritative.

    An untrusted external SQLite connection may mutate the database. This API
    does NOT assume it can authenticate that writer, detect forged journals,
    or safely authorize accelerated reads. Therefore all read paths are Source.
    """

    def __init__(self, path: str | Path, *, lens: bool = False):
        path = str(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, timeout=5, isolation_level=None,
                                   check_same_thread=False, cached_statements=0)
        self._closed = False
        self._lens = None
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            if path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_source_kv "
                "(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)"
            )
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_meta "
                "(singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
                "commit_seq INTEGER NOT NULL)"
            )
            self._db.execute(
                "INSERT OR IGNORE INTO opdb_meta(singleton,commit_seq) VALUES(1,0)"
            )
            if lens:
                from .lens import AggregateLens
                self._lens = AggregateLens(self._db)
                self._lens.rebuild()
        except BaseException:
            self._db.close()
            self._closed = True
            raise

    @property
    def read_mode(self) -> str:
        return "SOURCE_ONLY"

    @property
    def lens_enabled(self) -> bool:
        with self._lock:
            self._ensure_open()
            return self._lens is not None and self._lens.valid()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("TruthStore is closed")

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._db.close()
                self._closed = True

    def __enter__(self) -> TruthStore:
        self._ensure_open()
        return self

    def __exit__(self, _typ, _value, _tb) -> None:
        self.close()

    def apply(self, operations: Iterable[tuple]) -> None:
        """One atomic SQLite transaction. Errors roll back the whole batch.

        Accepted operations: ("put", key, bytes), ("delete", key).
        Validate all arguments before a transaction to avoid partial effects.
        """
        actions = list(islice(iter(operations), MAX_BATCH + 1))
        if len(actions) > MAX_BATCH:
            raise ValueError("batch exceeds 10000 operations")
        checked = []
        total_bytes = 0
        for item in actions:
            if not isinstance(item, tuple) or not item:
                raise ValueError("invalid operation")
            if len(item) == 3 and item[0] == "put":
                key, value = _key(item[1]), _value(item[2])
                total_bytes += len(key.encode("utf-8")) + len(value)
                checked.append(("put", key, value))
            elif len(item) == 2 and item[0] == "delete":
                key = _key(item[1])
                total_bytes += len(key.encode("utf-8"))
                checked.append(("delete", key))
            else:
                raise ValueError("invalid operation")
            if total_bytes > MAX_BATCH_BYTES:
                raise ValueError("batch exceeds 8 MiB of key and value payload")
        with self._lock:
            self._ensure_open()
            tracking = self._lens is not None and self._lens.valid()
            baseline = (self._lens.seq, self._lens.data_version) if tracking else None
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if tracking and self._lens.versions() != baseline:
                    tracking = False
                changes = {}
                if tracking:
                    from .lens import _metric, group_of
                for item in checked:
                    if tracking:
                        previous = self._db.execute(
                            "SELECT k,typeof(v),length(v) FROM opdb_source_kv WHERE k=?",
                            (item[1],),
                        ).fetchone()
                        group = group_of(item[1])
                        delta = changes.setdefault(group, [0, 0])
                        if previous is not None:
                            _, old_length = _metric(previous)
                            delta[0] -= 1
                            delta[1] -= old_length
                        if item[0] == "put":
                            delta[0] += 1
                            delta[1] += len(item[2])
                    if item[0] == "put":
                        self._db.execute(
                            "INSERT INTO opdb_source_kv(k,v) VALUES (?,?) "
                            "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                            (item[1], item[2]),
                        )
                    else:
                        self._db.execute(
                            "DELETE FROM opdb_source_kv WHERE k=?", (item[1],)
                        )
                self._db.execute(
                    "UPDATE opdb_meta SET commit_seq=commit_seq+1 WHERE singleton=1"
                )
                next_seq = self._db.execute(
                    "SELECT commit_seq FROM opdb_meta WHERE singleton=1"
                ).fetchone()[0]
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            if self._lens is not None:
                if tracking:
                    self._lens.advance(changes, next_seq, baseline[1])
                else:
                    self._lens.clear()
                    try:
                        self._lens.rebuild()
                    except (sqlite3.DatabaseError, SourceIntegrityError):
                        self._lens.clear()

    def group_stats_source(self, group: str) -> GroupStats:
        """Reference calculation directly over authoritative Source rows."""
        group = _key(group, allow_empty=True)
        from .lens import source_stats
        with self._lock:
            self._ensure_open()
            return source_stats(self._db, group)

    def group_stats(self, group: str) -> GroupStats:
        """Version-checked group Lens, or safe Source fallback."""
        group = _key(group, allow_empty=True)
        from .lens import source_stats
        with self._lock:
            self._ensure_open()
            if self._lens is None:
                return source_stats(self._db, group)
            return self._lens.get(group)

    def put(self, key: str, value: bytes) -> None:
        self.apply([("put", key, value)])

    def delete(self, key: str) -> None:
        self.apply([("delete", key)])

    def get(self, key: str) -> bytes | None:
        key = _key(key)
        with self._lock:
            self._ensure_open()
            result = self._db.execute(
                "SELECT k, CASE WHEN typeof(v)='blob' AND length(v)<=? "
                "THEN v ELSE NULL END, typeof(v), length(v) "
                "FROM opdb_source_kv WHERE k=?",
                (MAX_VALUE_BYTES, key),
            ).fetchone()
        return _source_row(result)[1] if result is not None else None

    def scan(self, prefix: str = "", limit: int = MAX_SCAN) -> tuple[tuple[str, bytes], ...]:
        prefix = _key(prefix, allow_empty=True)
        if type(limit) is not int or not 1 <= limit <= MAX_SCAN:
            raise ValueError("limit must be an integer in 1..1000")
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT k, CASE WHEN typeof(v)='blob' AND length(v)<=? "
                "THEN v ELSE NULL END, typeof(v), length(v) "
                "FROM opdb_source_kv "
                "WHERE substr(k,1,length(?))=? COLLATE BINARY "
                "ORDER BY k COLLATE BINARY LIMIT ?",
                (MAX_VALUE_BYTES, prefix, prefix, limit),
            ).fetchall()
        return tuple(_source_row(row) for row in rows)

    def snapshot(self) -> SourceSnapshot:
        """Rows are observed in one SQLite read transaction.

        digest_sha256 is a content checksum, NOT a trusted commit ID or a
        proof against ABA updates, external catalog edits or tampering.
        """
        with self._lock:
            self._ensure_open()
            self._db.execute("BEGIN")
            try:
                rows = tuple(
                    _source_row(row) for row in self._db.execute(
                        "SELECT k, CASE WHEN typeof(v)='blob' AND length(v)<=? "
                        "THEN v ELSE NULL END, typeof(v), length(v) "
                        "FROM opdb_source_kv ORDER BY k COLLATE BINARY",
                        (MAX_VALUE_BYTES,),
                    )
                )
            finally:
                self._db.execute("ROLLBACK")
        return SourceSnapshot(rows, _digest(rows), len(rows))

    def build_lens_candidate(self) -> LensCandidate:
        started = time.perf_counter_ns()
        data = self.snapshot()
        return LensCandidate(
            data.rows, data.digest_sha256, time.perf_counter_ns() - started
        )

    def check_candidate_against_source(self, candidate: LensCandidate) -> bool:
        """Best-effort diagnostic only; equality CANNOT authorize cutover."""
        if not isinstance(candidate, LensCandidate):
            raise TypeError("candidate must be a LensCandidate")
        actual = self.snapshot()
        return (candidate.rows == actual.rows
                and candidate.source_digest_sha256 == actual.digest_sha256)

    def admit_lens(self, candidate: LensCandidate) -> Admission:
        """Unconditionally fail closed until Safety provides trusted capture."""
        if not isinstance(candidate, LensCandidate):
            raise TypeError("candidate must be a LensCandidate")
        return Admission(
            accepted=False,
            mode="SOURCE_ONLY",
            reason="UNTRUSTED_CAPTURE_P0_21: no trusted commit journal/cutover proof",
        )
