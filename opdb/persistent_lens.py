"""M3 research-only opt-in durable aggregate state inside SQLite.

The SHA-256 checksum detects accidental cache damage; it does NOT authenticate
privileged external writers or verify that Source data was not tampered with.
Call schema/load/save only while holding the caller's SQLite write transaction.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3

from .core import SourceIntegrityError, _key


class PersistedLensState:
    VERSION = 1

    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def ensure_schema(self) -> None:
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS opdb_lens_groups_v1("
            "grp TEXT PRIMARY KEY COLLATE BINARY NOT NULL,"
            "row_count INTEGER NOT NULL, value_bytes INTEGER NOT NULL)"
        )
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS opdb_lens_state_v1("
            "singleton INTEGER PRIMARY KEY CHECK(singleton=1),"
            "format_version INTEGER NOT NULL, source_seq INTEGER NOT NULL,"
            "checksum TEXT NOT NULL)"
        )

    @staticmethod
    def _valid(stats: dict[str, tuple[int, int]]) -> bool:
        try:
            for group, (count, total) in stats.items():
                _key(group, allow_empty=True)
                if type(count) is not int or count <= 0:
                    return False
                if type(total) is not int or total < 0:
                    return False
        except (UnicodeError, ValueError, TypeError):
            return False
        return True

    @classmethod
    def checksum(cls, stats: dict[str, tuple[int, int]], seq: int) -> str:
        payload = json.dumps(
            [cls.VERSION, seq,
             [[key, count, size] for key, (count, size) in sorted(stats.items())]],
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def load(self, seq: int) -> dict[str, tuple[int, int]] | None:
        meta = self.db.execute(
            "SELECT format_version,source_seq,checksum "
            "FROM opdb_lens_state_v1 WHERE singleton=1"
        ).fetchone()
        if (meta is None or type(meta[0]) is not int
                or meta[0] != self.VERSION or type(meta[1]) is not int
                or meta[1] != seq or type(meta[2]) is not str):
            return None
        stats = {}
        for group, count, total in self.db.execute(
            "SELECT grp,row_count,value_bytes FROM opdb_lens_groups_v1"
        ):
            if type(group) is not str or group in stats:
                return None
            stats[group] = (count, total)
        if not self._valid(stats):
            return None
        actual = self.checksum(stats, seq)
        if not hmac.compare_digest(meta[2], actual):
            return None
        return stats

    def save(self, stats: dict[str, tuple[int, int]], seq: int) -> None:
        if not self._valid(stats) or type(seq) is not int:
            raise SourceIntegrityError("invalid persisted Lens metrics")
        # The caller's BEGIN IMMEDIATE encompasses Source, commit_seq, and
        # these tables. Never save a derived state after Source COMMIT.
        self.db.execute("DELETE FROM opdb_lens_groups_v1")
        self.db.executemany(
            "INSERT INTO opdb_lens_groups_v1(grp,row_count,value_bytes) "
            "VALUES (?,?,?)",
            [(group, count, total) for group, (count, total)
             in sorted(stats.items())],
        )
        self.db.execute(
            "INSERT INTO opdb_lens_state_v1 "
            "(singleton,format_version,source_seq,checksum) VALUES (1,?,?,?) "
            "ON CONFLICT(singleton) DO UPDATE SET "
            "format_version=excluded.format_version,"
            "source_seq=excluded.source_seq,checksum=excluded.checksum",
            (self.VERSION, seq, self.checksum(stats, seq)),
        )
