"""Transaction workloads: many commits, a rollback that must leave no trace, recovery after a killed process."""
import json
import os
import sqlite3
import subprocess
import sys

CRASH_CODE = r"""
import json, os, sqlite3, sys
path, = sys.argv[1:]
rows = [(k, bytes.fromhex(v)) for k, v in json.load(sys.stdin)]
db = sqlite3.connect(path, isolation_level=None)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=FULL")
db.execute("CREATE TABLE kv(k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID")
db.execute("BEGIN")
db.executemany("INSERT INTO kv(k, v) VALUES (?, ?)", rows[:200])
db.execute("COMMIT")
db.execute("BEGIN")
db.executemany("INSERT INTO kv(k, v) VALUES (?, ?)", rows[200:300])
os._exit(1)
"""


def commit_many(contender, rows, per_txn=100):
    """Write the rows in transactions of per_txn rows, one commit each; return the number of commits."""
    commits = 0
    for start in range(0, len(rows), per_txn):
        chunk = rows[start:start + per_txn]
        if hasattr(contender, "begin"):
            contender.begin()
            contender.insert(chunk)
            contender.commit()
        else:
            contender.bulk_insert(chunk, batch=len(chunk))
        commits += 1
    return commits


def rollback_check(contender, rows):
    """Write rows[:200], try rows[200:300] and roll that back; return the rolled-back keys that are visible."""
    contender.bulk_insert(rows[:200])
    rolled = rows[200:300]
    if hasattr(contender, "begin"):
        contender.begin()
        contender.insert(rolled)
        contender.rollback()
    else:
        contender.rollback_batch(rolled)
    return [k for k, _ in rolled if contender.get(k) is not None]


def crash_check(path, rows):
    """A child process commits rows[:200], inserts 100 more uncommitted and dies with os._exit(1).
    Return (present keys, PRAGMA integrity_check result) after reopening the file."""
    payload = json.dumps([(k, v.hex()) for k, v in rows[:300]])
    proc = subprocess.run([sys.executable, "-c", CRASH_CODE, str(path)], input=payload, text=True,
                          capture_output=True, timeout=120)
    if proc.returncode != 1:
        raise RuntimeError("crash child ended with %s: %s" % (proc.returncode, proc.stderr[-300:]))
    db = sqlite3.connect(str(path))
    try:
        keys = {k for (k,) in db.execute("SELECT k FROM kv")}
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        db.close()
    return keys, integrity
