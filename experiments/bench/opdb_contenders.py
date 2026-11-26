"""OpDB participants of the benchmark: Source (TruthStore) and the numeric Lens (NumericTruthStore).

Both open their SQLite file with WAL and synchronous=FULL (see opdb/core.py), the same durability as the
SQLite contender's default."""
import sqlite3

from opdb import NumericTruthStore, TruthStore


class OpdbSourceContender:
    name = "opdb_source"
    store_class = TruthStore

    def __init__(self, path):
        self.path = str(path)
        self.store = self.store_class(self.path)

    @classmethod
    def applicable(cls, value_bytes):
        return True

    def bulk_insert(self, rows, batch=1000):
        for start in range(0, len(rows), batch):
            self.store.apply([("put", k, v) for k, v in rows[start:start + batch]])

    def get(self, key):
        return self.store.get(key)

    def count(self):
        db = sqlite3.connect(self.path)
        try:
            return db.execute("SELECT count(*) FROM opdb_source_kv").fetchone()[0]
        finally:
            db.close()

    def close(self):
        self.store.close()


class OpdbNumericContender(OpdbSourceContender):
    name = "opdb_numeric_lens"
    store_class = NumericTruthStore

    @classmethod
    def applicable(cls, value_bytes):
        return value_bytes == 8
