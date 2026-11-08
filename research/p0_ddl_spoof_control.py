"""Independent negative control: SQLite schema-version is not capture attestation.

This deliberately attacks a trigger-backed *reference fixture*, not OpDB Core.
An expected counterexample proves the probe can expose an unsafe design;
it does NOT establish that the real OpDB Proof Gate detects the attack.
"""
import random
import sqlite3
import tempfile
from pathlib import Path


def probe_p0_ddl_spoof(seed):
    """Demonstrate privileged trigger removal + schema cookie restoration."""
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="opdb-ddl-spoof-") as folder:
        db_path = str(Path(folder) / "truth.db")
        source = sqlite3.connect(db_path, cached_statements=0)
        try:
            source.executescript("""
                CREATE TABLE kv (id INTEGER PRIMARY KEY, value INTEGER NOT NULL);
                CREATE TABLE journal (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_value INTEGER NOT NULL,
                    new_value INTEGER NOT NULL
                );
                CREATE TRIGGER kv_capture AFTER UPDATE ON kv BEGIN
                    INSERT INTO journal (old_value, new_value)
                    VALUES (old.value, new.value);
                END;
            """)
            initial = rng.randrange(1, 10000)
            source.execute("INSERT INTO kv VALUES (1, ?)", (initial,))
            source.commit()

            # Ordinary external SQL goes through the trigger and can be replayed.
            with sqlite3.connect(db_path) as writer:
                writer.execute("UPDATE kv SET value=? WHERE id=1", (initial + 7,))
            captured = source.execute(
                "SELECT seq, old_value, new_value FROM journal ORDER BY seq"
            ).fetchall()
            source_after_normal = source.execute(
                "SELECT value FROM kv WHERE id=1"
            ).fetchone()[0]
            replayed = initial + sum(new - old for _, old, new in captured)
            normal_capture_matches = (
                len(captured) == 1 and captured[0][0] == 1
                and replayed == source_after_normal == initial + 7
            )
            schema_before = source.execute("PRAGMA schema_version").fetchone()[0]

            # Privileged external actor bypasses the trigger, and spoofs the
            # SQLite schema cookie back to its previous value. This actor is
            # outside the supported trust boundary of a trigger-only scheme.
            with sqlite3.connect(db_path) as attacker:
                attacker.execute("DROP TRIGGER kv_capture")
                attacker.execute(f"PRAGMA schema_version={schema_before}")
                attacker.execute("UPDATE kv SET value=? WHERE id=1", (initial + 31,))

            schema_after = source.execute("PRAGMA schema_version").fetchone()[0]
            journal_after = source.execute(
                "SELECT seq, old_value, new_value FROM journal ORDER BY seq"
            ).fetchall()
            final_truth = source.execute(
                "SELECT value FROM kv WHERE id=1"
            ).fetchone()[0]
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            surviving_triggers = source.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name='kv_capture'"
            ).fetchone()[0]

            checks = {
                "normal_capture_matches": normal_capture_matches,
                "trigger_removed": surviving_triggers == 0,
                "schema_cookie_restored": schema_after == schema_before,
                "journal_unchanged": journal_after == captured,
                "derived_result_wrong": replayed != final_truth,
                "source_only_result_correct": final_truth == initial + 31,
                "sqlite_integrity_ok": integrity == "ok",
            }
            if not all(checks.values()):
                raise AssertionError(f"P0 DDL spoof control did not reproduce: {checks}")
            return {
                "status": "EXPECTED_COUNTEREXAMPLE",
                "assertions": len(checks),
                "checks": checks,
                "seed": seed,
                "scope": (
                    "Privileged SQLite DDL removes the capture trigger, restores schema_version, "
                    "and makes a derived replay stale with an unchanged journal. "
                    "Source-only reference read remains correct. NOT an OpDB adapter test."
                ),
            }
        finally:
            source.close()
