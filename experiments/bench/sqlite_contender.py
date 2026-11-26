"""Plain SQLite as a benchmark contender: WAL, a chosen synchronous level, one transaction per batch."""
import sqlite3


class SqliteContender:
    name = "sqlite"

    def __init__(self, path, synchronous="FULL"):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=%s" % synchronous)
        self.db.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID")

    def bulk_insert(self, rows, batch=1000):
        for start in range(0, len(rows), batch):
            self.db.execute("BEGIN")
            self.db.executemany("INSERT OR REPLACE INTO kv(k, v) VALUES (?, ?)", rows[start:start + batch])
            self.db.execute("COMMIT")

    def get(self, key):
        row = self.db.execute("SELECT v FROM kv WHERE k = ?", (key,)).fetchone()
        return None if row is None else bytes(row[0])

    def count(self):
        return self.db.execute("SELECT COUNT(*) FROM kv").fetchone()[0]

    def close(self):
        self.db.close()
