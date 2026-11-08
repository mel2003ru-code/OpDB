"""Bounded, reproducible research checks for GitHub's half-hourly schedule.

IMPORTANT: these SQLite experiments do not prove that an OpDB engine works.
Missing track implementations report NOT_CONFIGURED, never PASS.
"""
import argparse
import datetime as dt
import json
import os
import platform
import random
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from research.probes_extended import (
    probe_r01, probe_r02, probe_r04, probe_r05, probe_r06, probe_r08, probe_r09,
    probe_p0_negative_control,
)

TRACKS = [(f"R{i:02d}", i + 6) for i in range(1, 11)] + [
    ("TASK-001", 2), ("TASK-002", 3), ("TASK-003", 4)
]


def probe_dynamic_index(seed):
    """Oracle equality across in-transaction updates and SQLite index DDL."""
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:", cached_statements=0)
    try:
        db.execute("CREATE TABLE kv (id INTEGER PRIMARY KEY, tenant INTEGER, bucket INTEGER, value INTEGER)")
        truth = {}
        for ident in range(300):
            row = (rng.randrange(6), rng.randrange(40), rng.randrange(-100, 101))
            truth[ident] = row
            db.execute("INSERT INTO kv VALUES (?,?,?,?)", (ident, *row))
        db.commit()
        checks = 0
        for step in range(240):
            if step == 32:
                db.execute("CREATE INDEX idx_derived ON kv(tenant,bucket)")
            if step == 95:
                db.execute("DROP INDEX idx_derived")
            if step == 158:
                db.execute("CREATE INDEX idx_derived ON kv(tenant,bucket)")
            ident = rng.randrange(380)
            action = rng.randrange(4)
            if action in (0, 1):
                row = (rng.randrange(6), rng.randrange(40), rng.randrange(-100, 101))
                db.execute(
                    "INSERT INTO kv VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "tenant=excluded.tenant,bucket=excluded.bucket,value=excluded.value",
                    (ident, *row)
                )
                truth[ident] = row
            elif action == 2:
                db.execute("DELETE FROM kv WHERE id=?", (ident,))
                truth.pop(ident, None)
            tenant = rng.randrange(6)
            lo = rng.randrange(40)
            hi = rng.randrange(lo, 40)
            actual = db.execute(
                "SELECT COALESCE(SUM(value),0) FROM kv WHERE tenant=? "
                "AND bucket BETWEEN ? AND ?", (tenant, lo, hi)
            ).fetchone()[0]
            expected = sum(v for t, b, v in truth.values()
                           if t == tenant and lo <= b <= hi)
            if actual != expected:
                raise AssertionError("dynamic index oracle mismatch: step %s" % step)
            checks += 1
        rows = db.execute("SELECT id,tenant,bucket,value FROM kv ORDER BY id").fetchall()
        if rows != [(k, *v) for k, v in sorted(truth.items())]:
            raise AssertionError("final-state mismatch")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise AssertionError("SQLite integrity check failed")
        return {"assertions": checks + 2, "scope": "SQLite-only dynamic-index/oracle smoke test"}
    finally:
        db.close()


def probe_sqlite_crash(seed):
    """Process termination before/after commit, not real power-loss testing."""
    checks = 0
    with tempfile.TemporaryDirectory(prefix="opdb-research-") as directory:
        for committed in (False, True):
            file = str(Path(directory) / ("committed.db" if committed else "pending.db"))
            db = sqlite3.connect(file)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, value INTEGER)")
            db.execute("INSERT INTO kv VALUES (1,1)")
            db.commit()
            db.close()
            child = (
                "import os,sqlite3,sys\n"
                "db=sqlite3.connect(sys.argv[1]);db.execute('PRAGMA synchronous=FULL');"
                "db.execute('BEGIN IMMEDIATE');db.execute('UPDATE kv SET value=2 WHERE id=1');\n"
                "if sys.argv[2]=='yes': db.commit()\n"
                "os._exit(17)\n"
            )
            proc = subprocess.run(
                [sys.executable, "-c", child, file, "yes" if committed else "no"],
                timeout=15, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            if proc.returncode != 17:
                raise AssertionError("child did not exit as expected: %s" % proc.stderr.decode(errors="replace"))
            db = sqlite3.connect(file)
            try:
                expected = 2 if committed else 1
                value = db.execute("SELECT value FROM kv WHERE id=1").fetchone()[0]
                if value != expected:
                    raise AssertionError("SQLite crash test mismatch, committed=%s" % committed)
                if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise AssertionError("SQLite integrity failed after process exit")
                checks += 2
            finally:
                db.close()
    return {"assertions": checks, "scope": "SQLite WAL recovery after os._exit only; not power loss, not OpDB WAL"}


def probe_metamorphic_sql(seed):
    """Independent Python oracle plus split-range metamorphic SQL identity."""
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE kv(tenant INTEGER,bucket INTEGER,value INTEGER)")
        rows = [(rng.randrange(12), rng.randrange(128), rng.randrange(-1000,1001))
                for _ in range(400)]
        db.executemany("INSERT INTO kv VALUES (?,?,?)", rows)
        db.commit()
        checks = 0
        for _ in range(120):
            tenant = rng.randrange(12)
            lower = rng.randrange(128)
            upper = rng.randrange(lower, 128)
            middle = rng.randrange(lower, upper + 1)
            query = "SELECT COALESCE(SUM(value),0) FROM kv WHERE tenant=? AND bucket BETWEEN ? AND ?"
            params = (tenant, lower, upper)
            whole = db.execute(query, params).fetchone()[0]
            left = db.execute(query, (tenant, lower, middle)).fetchone()[0]
            right = db.execute(query, (tenant, middle + 1, upper)).fetchone()[0]
            expected = sum(value for t, bucket, value in rows
                           if t == tenant and lower <= bucket <= upper)
            if whole != left + right or whole != expected:
                raise AssertionError("metamorphic sum mismatch")
            checks += 2
        return {"assertions": checks, "scope": "SQLite integer SUM metamorphic and Python oracle; not OpDB SQL"}
    finally:
        db.close()


PROBES = {
    "R01": probe_r01,
    "R02": probe_r02,
    "R03": probe_dynamic_index,
    "R04": probe_r04,
    "R05": probe_r05,
    "R06": probe_r06,
    "R07": probe_sqlite_crash,
    "R08": probe_r08,
    "R09": probe_r09,
    "R10": probe_metamorphic_sql,
}
MODEL_TRACKS = {"R04", "R05", "R09"}


def run_cycle(seed):
    started = dt.datetime.now(dt.timezone.utc)
    results = []
    for index, (track, issue) in enumerate(TRACKS):
        probe = PROBES.get(track)
        if probe is None:
            results.append({
                "track": track, "issue": issue, "status": "NOT_CONFIGURED",
                "reason": "No executable research probe has been reviewed for this workstream"
            })
            continue
        local_seed = seed + index * 1009
        t0 = time.perf_counter()
        try:
            detail = probe(local_seed)
            results.append({
                "track": track, "issue": issue, "status": (
                    "MODEL_SMOKE_PASS" if track in MODEL_TRACKS else "SQLITE_SMOKE_PASS"
                ),
                "seed": local_seed, "elapsed_s": round(time.perf_counter() - t0, 6),
                **detail
            })
        except Exception as exc:
            results.append({
                "track": track, "issue": issue, "status": "FAIL",
                "seed": local_seed, "elapsed_s": round(time.perf_counter() - t0, 6),
                "error": "%s: %s" % (type(exc).__name__, exc)
            })
    try:
        control = probe_p0_negative_control(seed + 50051)
        negative_controls = [{"name": "P0_FORGED_OR_BYPASSED_CAPTURE",
                              "status": "EXPECTED_COUNTEREXAMPLE", **control}]
    except Exception as exc:
        negative_controls = [{"name": "P0_FORGED_OR_BYPASSED_CAPTURE",
                              "status": "FAIL",
                              "error": "%s: %s" % (type(exc).__name__, exc)}]
    return {
        "start_utc": started.isoformat(),
        "seed": seed,
        "repository_sha": os.getenv("GITHUB_SHA", "not-provided"),
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "disclaimer": "All probes are SQLite/Python/model smoke tests; P0 deliberately demonstrates an unsafe unprotected Lens; no autonomous AI agents or production OpDB engine are exercised",
        "results": results,
        "negative_controls": negative_controls
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=int(time.time() // 1800),
                        help="30-minute UTC slot; override to reproduce exact trace")
    parser.add_argument("--output", default="research-cycle.json")
    args = parser.parse_args()
    report = run_cycle(args.seed)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rows = [
        "## OpDB 30-minute research checks",
        "",
        "Seed: \`%s\`; Python %s; SQLite %s; revision \`%s\`." %
        (report["seed"], report["python"], report["sqlite"], report["repository_sha"]),
        "",
        "**These are limited SQLite/Python checks, not research agents and not OpDB guarantees.**",
        "",
        "| Track | Status | Evidence |", "|---|---|---|",
    ]
    for item in report["results"]:
        details = item.get("scope", item.get("reason", item.get("error", "")))
        rows.append("| [%s](https://github.com/mel2003ru-code/OpDB/issues/%d) | %s | %s |" %
                    (item["track"], item["issue"], item["status"], details.replace("|", "\\|")))
    rows.extend(["", "### Mandatory negative control (unsafe implementation)",
                 ""])
    for control in report["negative_controls"]:
        rows.append("- %s: **%s** — %s" % (
            control["name"], control["status"],
            control.get("scope", control.get("error", ""))
        ))
    rows.append("A detected stale result is an EXPECTED counterexample, NOT a passing safety property of OpDB.")
    summary = "\n".join(rows) + "\n"
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(summary)
    if (any(item["status"] == "FAIL" for item in report["results"])
            or any(item["status"] == "FAIL" for item in report["negative_controls"])):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
