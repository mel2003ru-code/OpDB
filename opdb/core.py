"""OpDB Core experiment 0.1: SQLite-backed authoritative KV and disposable Lens.

Not a native DBMS, no SQL compatibility, no verified change capture.
All user reads use SQLite directly. No derived-Lens admission exists because
external privileged writers can bypass/forge SQLite trigger logs (P0 #21).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3
import threading
import time
from typing import Iterable, Literal

MAX_KEY_UTF8 = 512
MAX_VALUE_BYTES = 1024 * 1024
MAX_BATCH = 10000
MAX_SCAN = 1000

@dataclass(frozen=True)
class SourceSnapshot:
    rows: tuple[tuple[str, bytes], ...]
    digest_sha256: str
    row_count: int

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

class TruthStore:
    """Single-process research API. SQLite remains authoritative.

    An untrusted external SQLite connection may mutate the database. This API
    does NOT assume it can authenticate that writer, detect forged journals,
    or safely authorize accelerated reads. Therefore all read paths are Source.
    """

    def __init__(self, path: str | Path):
        path = str(path)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, timeout=5, isolation_level=None,
                                   check_same_thread=False, cached_statements=0)
        self._closed = False
        try:
            self._db.execute("PRAGMA busy_timeout=5000")
            if path != ":memory:":
                self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS opdb_source_kv "
                "(k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)"
            )
        except BaseException:
            self._db.close()
            self._closed = True
            raise

    @property
    def read_mode(self) -> str:
        return "SOURCE_ONLY"

    @property
    def lens_enabled(self) -> bool:
        return False

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
        actions = list(operations)
        if len(actions) > MAX_BATCH:
            raise ValueError("batch exceeds 10000 operations")
        checked = []
        for item in actions:
            if not isinstance(item, tuple) or not item:
                raise ValueError("invalid operation")
            if len(item) == 3 and item[0] == "put":
                checked.append(("put", _key(item[1]), _value(item[2])))
            elif len(item) == 2 and item[0] == "delete":
                checked.append(("delete", _key(item[1])))
            else:
                raise ValueError("invalid operation")
        with self._lock:
            self._ensure_open()
            self._db.execute("BEGIN IMMEDIATE")
            try:
                for item in checked:
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
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def put(self, key: str, value: bytes) -> None:
        self.apply([("put", key, value)])

    def delete(self, key: str) -> None:
        self.apply([("delete", key)])

    def get(self, key: str) -> bytes | None:
        key = _key(key)
        with self._lock:
            self._ensure_open()
            result = self._db.execute(
                "SELECT v FROM opdb_source_kv WHERE k=?", (key,)
            ).fetchone()
        return bytes(result[0]) if result else None

    def scan(self, prefix: str = "", limit: int = MAX_SCAN) -> tuple[tuple[str, bytes], ...]:
        prefix = _key(prefix, allow_empty=True)
        if type(limit) is not int or not 1 <= limit <= MAX_SCAN:
            raise ValueError("limit must be an integer in 1..1000")
        with self._lock:
            self._ensure_open()
            rows = self._db.execute(
                "SELECT k,v FROM opdb_source_kv "
                "WHERE substr(k,1,length(?))=? COLLATE BINARY "
                "ORDER BY k COLLATE BINARY LIMIT ?",
                (prefix, prefix, limit),
            ).fetchall()
        return tuple((row[0], bytes(row[1])) for row in rows)

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
                    (key, bytes(value)) for key, value in self._db.execute(
                        "SELECT k,v FROM opdb_source_kv ORDER BY k COLLATE BINARY"
                    ).fetchall()
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
