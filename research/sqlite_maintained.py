"""SQLite-managed materialized aggregate baseline for LAB-001.

Independent reference implemented solely with SQLite tables/triggers.
All changes are in disposable lab fixtures, never production files.
"""
from __future__ import annotations

import sqlite3


def _group_expr(alias: str) -> str:
    if alias not in ("NEW", "OLD", "t"):
        raise ValueError("Only fixed SQL aliases are accepted")
    key = alias + ".k"
    return (
        f"CASE WHEN instr({key},'/')=0 THEN {key} "
        f"ELSE substr({key},1,instr({key},'/')-1) END"
    )


def install_maintained_summary(db: sqlite3.Connection) -> None:
    """Build a real SQLite summary and enable transactional INSERT/UPDATE/DELETE.

    Caller must use a disposable fixture, and must have no active transaction.
    Installation time is reported separately from query time.
    """
    db.execute(
        "CREATE TABLE lab_group_summary("
        "grp TEXT PRIMARY KEY COLLATE BINARY NOT NULL,"
        "row_count INTEGER NOT NULL CHECK(row_count>=0),"
        "value_bytes INTEGER NOT NULL CHECK(value_bytes>=0))"
    )
    db.execute(
        "INSERT INTO lab_group_summary "
        f"SELECT {_group_expr('t')} AS grp, count(*),"
        "coalesce(sum(length(t.v)),0) "
        "FROM opdb_source_kv AS t GROUP BY grp"
    )
    db.executescript(f"""
        CREATE TRIGGER lab_group_ai AFTER INSERT ON opdb_source_kv BEGIN
            INSERT INTO lab_group_summary
            VALUES({_group_expr('NEW')}, 1, length(NEW.v))
            ON CONFLICT(grp) DO UPDATE
              SET row_count=row_count+1,
                  value_bytes=value_bytes+excluded.value_bytes;
        END;
        CREATE TRIGGER lab_group_ad AFTER DELETE ON opdb_source_kv BEGIN
            UPDATE lab_group_summary
              SET row_count=row_count-1,
                  value_bytes=value_bytes-length(OLD.v)
              WHERE grp={_group_expr('OLD')};
            DELETE FROM lab_group_summary WHERE row_count=0;
        END;
        CREATE TRIGGER lab_group_au AFTER UPDATE OF k,v ON opdb_source_kv BEGIN
            UPDATE lab_group_summary
              SET row_count=row_count-1,
                  value_bytes=value_bytes-length(OLD.v)
              WHERE grp={_group_expr('OLD')};
            DELETE FROM lab_group_summary WHERE row_count=0;
            INSERT INTO lab_group_summary
            VALUES({_group_expr('NEW')}, 1, length(NEW.v))
            ON CONFLICT(grp) DO UPDATE
              SET row_count=row_count+1,
                  value_bytes=value_bytes+excluded.value_bytes;
        END;
    """)


def maintained_stats(db: sqlite3.Connection, group: str) -> tuple[int, int]:
    row = db.execute(
        "SELECT row_count,value_bytes FROM lab_group_summary WHERE grp=?",
        (group,),
    ).fetchone()
    return (int(row[0]), int(row[1])) if row is not None else (0, 0)
