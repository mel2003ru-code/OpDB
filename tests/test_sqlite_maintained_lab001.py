"""LAB-001 SQLite trigger-maintained materialized summary cross-checks.

Adversarial cases independent of the OpDB Lens implementation.
"""
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path

from research.sqlite_maintained import install_maintained_summary, maintained_stats


class MaintainedSQLiteOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lab001-trigger-")
        self.addCleanup(self.tmp.cleanup)
        self.db = sqlite3.connect(Path(self.tmp.name) / "fixture.db",
                                  isolation_level=None)
        self.addCleanup(self.db.close)
        self.db.execute(
            "CREATE TABLE opdb_source_kv("
            "k TEXT PRIMARY KEY COLLATE BINARY NOT NULL, v BLOB NOT NULL)"
        )
        self.db.execute("INSERT INTO opdb_source_kv VALUES ('g1/old',X'010203')")
        install_maintained_summary(self.db)

    def check_group(self, model, group):
        values = [value for key, value in model.items()
                  if key.split("/", 1)[0] == group]
        expected = (len(values), sum(len(value) for value in values))
        self.assertEqual(maintained_stats(self.db, group), expected)
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*),COALESCE(SUM(LENGTH(v)),0) "
                "FROM opdb_source_kv"
            ).fetchone()[0],
            len(model),
        )

    def test_seeded_mutations_and_sql_rollbacks(self):
        rng = random.Random(59173)
        model = {"g1/old": bytes((1, 2, 3))}
        groups = ["", "g1", "g10", "g1-other", "clé", "empty", "missing"]
        for i in range(450):
            group = rng.choice(groups[:-1])
            key = group + ("/" + str(rng.randrange(15))
                           if rng.randrange(2) else "")
            if not key:
                key = "/"
            operation = rng.randrange(5)
            self.db.execute("BEGIN IMMEDIATE")
            if operation == 0:
                self.db.execute("DELETE FROM opdb_source_kv WHERE k=?", (key,))
                new_model = dict(model)
                new_model.pop(key, None)
            else:
                value = bytes([rng.randrange(256)]) * rng.randrange(35)
                self.db.execute(
                    "INSERT INTO opdb_source_kv VALUES (?,?) "
                    "ON CONFLICT(k) DO UPDATE SET v=excluded.v",
                    (key, value),
                )
                new_model = dict(model)
                new_model[key] = value
            if i % 7 == 0:
                self.db.execute("ROLLBACK")
            else:
                self.db.execute("COMMIT")
                model = new_model
            for name in groups:
                self.check_group(model, name)
        # UPDATE that moves an existing key into another aggregate group.
        self.db.execute("UPDATE opdb_source_kv SET k=? WHERE k=?", ("moved/a", "g1/old"))
        if "g1/old" in model:
            model["moved/a"] = model.pop("g1/old")
        for name in groups + ["moved"]:
            self.check_group(model, name)

    def test_transactional_trigger_failure_rolls_back_source(self):
        before = self.db.execute("SELECT * FROM opdb_source_kv").fetchall()
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("INSERT INTO opdb_source_kv VALUES ('tmp/z',X'00')")
        self.db.execute("ROLLBACK")
        self.assertEqual(self.db.execute(
            "SELECT * FROM opdb_source_kv").fetchall(), before)
        self.assertEqual(maintained_stats(self.db, "tmp"), (0, 0))
        self.assertEqual(maintained_stats(self.db, "g1"), (1, 3))


if __name__ == "__main__":
    unittest.main()
