"""Disposable group aggregates over a SQLite Source (ADR-006 single-writer model).

Best-effort foreign-write detection is not authentication of a privileged writer.
"""
from __future__ import annotations

from collections import defaultdict
import sqlite3
import time

from .core import GroupStats, MAX_VALUE_BYTES, SourceIntegrityError, _key


def group_of(key: str) -> str:
    return key.split("/", 1)[0]


def _metric(row: tuple) -> tuple[str, int]:
    key, storage, size = row
    if type(key) is not str:
        raise SourceIntegrityError("invalid source key: not UTF-8 text")
    try:
        _key(key)
    except ValueError as exc:
        raise SourceIntegrityError("invalid source key: outside typed KV contract") from exc
    if storage != "blob":
        raise SourceIntegrityError("non-BLOB source value")
    if type(size) is not int or not 0 <= size <= MAX_VALUE_BYTES:
        raise SourceIntegrityError("oversized or malformed source BLOB")
    return key, size


def source_stats(db: sqlite3.Connection, group: str) -> GroupStats:
    """Independent Source reference: read matching rows, not cached aggregates."""
    prefix = group + "/"
    # The slash's next Unicode code point is '0'. BINARY ranges select a
    # group prefix without SQL LIKE wildcard or case-folding ambiguity.
    upper = group + "0"
    rows = db.execute(
        "SELECT k,typeof(v),length(v) FROM opdb_source_kv "
        "WHERE k=? COLLATE BINARY OR "
        "(k>=? COLLATE BINARY AND k<? COLLATE BINARY)",
        (group, prefix, upper),
    )
    count = size_sum = 0
    for row in rows:
        key, size = _metric(row)
        if group_of(key) == group:
            count += 1
            size_sum += size
    return GroupStats(count, size_sum, "SOURCE")


class AggregateLens:
    """Per-connection group counts and lengths; never a source of durability."""

    def __init__(self, db: sqlite3.Connection, *, persistent: bool = False):
        self.db = db
        from .persistent_lens import PersistedLensState
        self.persist = PersistedLensState(db) if persistent else None
        self.loaded_from_disk = False
        self.stats: dict[str, tuple[int, int]] | None = None
        self.seq: int | None = None
        self.data_version: int | None = None
        self.rebuild_ns = 0

    def clear(self) -> None:
        self.loaded_from_disk = False
        self.stats = None
        self.seq = None
        self.data_version = None

    def versions(self) -> tuple[int, int]:
        result = self.db.execute(
            "SELECT commit_seq FROM opdb_meta WHERE singleton=1"
        ).fetchone()
        if result is None or type(result[0]) is not int:
            raise SourceIntegrityError("missing or malformed commit sequence")
        return result[0], self.db.execute("PRAGMA data_version").fetchone()[0]

    def valid(self) -> bool:
        if self.stats is None:
            return False
        try:
            correct = (self.seq, self.data_version) == self.versions()
        except (sqlite3.DatabaseError, SourceIntegrityError):
            correct = False
        if not correct:
            self.clear()
        return correct

    def rebuild(self) -> bool:
        """Only publish after scanning one consistent read transaction."""
        self.clear()
        started = time.perf_counter_ns()
        self.db.execute("BEGIN")
        try:
            before = self.versions()
            counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for row in self.db.execute(
                "SELECT k,typeof(v),length(v) FROM opdb_source_kv"
            ):
                key, size = _metric(row)
                pair = counts[group_of(key)]
                pair[0] += 1
                pair[1] += size
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        after = self.versions()
        self.rebuild_ns = time.perf_counter_ns() - started
        if after != before:
            return False
        self.stats = {name: (pair[0], pair[1]) for name, pair in counts.items()}
        self.seq, self.data_version = after
        return True

    def restore_or_rebuild(self, *, force: bool = False) -> bool:
        """Load versioned aggregate without Source scan, or rebuild atomically.

        Stale/malformed saved state is disposable. Source remains the only
        durable truth; this is not a privileged-writer authenticity proof.
        """
        if self.persist is None:
            return self.rebuild()
        self.clear()
        started = time.perf_counter_ns()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            self.persist.ensure_schema()
            before = self.versions()
            cached = None if force else self.persist.load(before[0])
            restored = cached is not None
            if not restored:
                counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
                for row in self.db.execute(
                    "SELECT k,typeof(v),length(v) FROM opdb_source_kv"
                ):
                    key, size = _metric(row)
                    pair = counts[group_of(key)]
                    pair[0] += 1
                    pair[1] += size
                cached = {name: (pair[0], pair[1])
                          for name, pair in counts.items()}
                self.persist.save(cached, before[0])
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        after = self.versions()
        self.rebuild_ns = time.perf_counter_ns() - started
        if after != before:
            self.clear()
            return False
        self.stats = cached
        self.seq, self.data_version = after
        self.loaded_from_disk = restored
        return True

    def persist_batch(self, changes: dict[str, list[int]], next_seq: int) -> None:
        """Stage new durable Lens inside the same Source write transaction."""
        if self.persist is None:
            return
        if self.stats is None:
            raise SourceIntegrityError("Lens missing before persistent commit")
        updated = dict(self.stats)
        for group, (count_delta, size_delta) in changes.items():
            count, size = updated.get(group, (0, 0))
            count += count_delta
            size += size_delta
            if count < 0 or size < 0:
                raise SourceIntegrityError("invalid persistent Lens delta")
            if count:
                updated[group] = (count, size)
            else:
                updated.pop(group, None)
        self.persist.save(updated, next_seq)

    def get(self, group: str) -> GroupStats:
        if self.valid():
            count, size = self.stats.get(group, (0, 0))
            return GroupStats(count, size, "LENS")
        answer = source_stats(self.db, group)
        try:
            if self.persist is None:
                self.rebuild()
            else:
                # An observed outside write invalidates the saved checkpoint.
                self.restore_or_rebuild(force=True)
        except (sqlite3.DatabaseError, SourceIntegrityError):
            self.clear()
        return answer

    def advance(self, changes: dict[str, list[int]], next_seq: int,
                old_data_version: int) -> None:
        """Called strictly after successful COMMIT; failure discards Lens."""
        try:
            if self.stats is None or self.versions()[1] != old_data_version:
                self.clear()
                return
            for name, (count_delta, size_delta) in changes.items():
                count, size = self.stats.get(name, (0, 0))
                count += count_delta
                size += size_delta
                if count < 0 or size < 0:
                    raise SourceIntegrityError("negative Lens aggregate")
                if count:
                    self.stats[name] = (count, size)
                else:
                    self.stats.pop(name, None)
            self.seq = next_seq
            self.data_version = old_data_version
        except (sqlite3.DatabaseError, SourceIntegrityError):
            self.clear()

