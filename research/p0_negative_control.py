"""Required adversarial negative control for unprotected derived SQLite state.

The deliberately insecure caches below MUST return stale/wrong values in the
constructed scenarios. Detection proves the *test* can see these failures,
not that Core or Safety blocks them.
"""
import random
import sqlite3
import tempfile
from pathlib import Path


def probe_p0_negative_control(seed):
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="opdb-p0-") as directory:
        filename = str(Path(directory) / "negative-control.db")
        db = sqlite3.connect(filename, cached_statements=0)
        try:
            db.executescript("""
                CREATE TABLE kv(id INTEGER PRIMARY KEY, val INTEGER NOT NULL);
                CREATE TABLE changes(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    old_v INTEGER NOT NULL, new_v INTEGER NOT NULL
                );
                CREATE TRIGGER kv_update AFTER UPDATE ON kv BEGIN
                    INSERT INTO changes(old_v,new_v) VALUES (old.val,new.val);
                END;
            """)
            before = rng.randrange(1, 500)
            db.execute("INSERT INTO kv VALUES(1,?)", (before,))
            db.commit()

            unguarded_lens_value = before
            external = sqlite3.connect(filename)
            try:
                external.execute("UPDATE kv SET val=? WHERE id=1", (before+20,))
                external.commit()
            finally:
                external.close()
            source = db.execute("SELECT val FROM kv WHERE id=1").fetchone()[0]
            stale_detected = unguarded_lens_value != source
            if not stale_detected:
                raise AssertionError("unguarded stale-Lens counterexample was not detected")

            # A privileged writer can corrupt a journal payload while retaining
            # valid sequence and old image. This is NOT a trustable change stream.
            attacker = sqlite3.connect(filename)
            try:
                attacker.execute("UPDATE changes SET new_v=? WHERE seq=1", (before+37,))
                attacker.commit()
            finally:
                attacker.close()
            change = db.execute("SELECT seq,old_v,new_v FROM changes").fetchone()
            forged_replay = unguarded_lens_value + change[2] - change[1]
            schema_version = db.execute("PRAGMA schema_version").fetchone()[0]
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            if change[0] != 1 or change[1] != before:
                raise AssertionError("negative-control journal topology unexpectedly changed")
            if forged_replay == source or integrity != "ok" or schema_version <= 0:
                raise AssertionError("forged-journal negative control was not reproduced")
            return {
                "assertions": 6, "status": "EXPECTED_COUNTEREXAMPLE",
                "external_untracked_stale": stale_detected,
                "forged_journal_mismatch": forged_replay != source,
                "source_integrity": integrity,
                "scope": "Two intentionally unsafe SQLite/Python examples: unguarded Lens stale after external COMMIT and privileged forged journal. NOT actual OpDB Proof Gate."
            }
        finally:
            db.close()
