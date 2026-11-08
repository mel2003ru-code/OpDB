"""Independent bounded SQLite/model probes, not a test of a production OpDB engine.

All datasets are synthetic. No external URLs, credentials, project databases or
persistent files are accessed. Numerical measurements are descriptive only.
"""
from collections import OrderedDict, deque
import math
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path


def probe_r01(seed):
    """R01: exact cache invalidation vs SQL and independent Python row oracle."""
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, tenant INTEGER, value INTEGER)")
        truth = {}
        for ident in range(200):
            row = (rng.randrange(8), rng.randrange(-200, 201))
            db.execute("INSERT INTO kv VALUES(?,?,?)", (ident, *row))
            truth[ident] = row
        db.commit()
        cache = {}
        assertions = 0
        hits = 0
        invalidations = 0
        for _ in range(180):
            if rng.randrange(5) < 2:
                ident = rng.randrange(200)
                row = (rng.randrange(8), rng.randrange(-200, 201))
                db.execute("UPDATE kv SET tenant=?,value=? WHERE id=?", (*row, ident))
                truth[ident] = row
                cache.clear()  # conservative global invalidation; not an optimized product policy
                invalidations += 1
            tenant = rng.randrange(8)
            for _ in range(2):
                if tenant in cache:
                    answer = cache[tenant]
                    hits += 1
                else:
                    answer = db.execute(
                        "SELECT COALESCE(SUM(value),0) FROM kv WHERE tenant=?", (tenant,)
                    ).fetchone()[0]
                    cache[tenant] = answer
                independent = sum(value for t, value in truth.values() if t == tenant)
                if answer != independent:
                    raise AssertionError("cache returned stale or incorrect aggregate")
                assertions += 1
        assert hits > 0 and invalidations > 0
        return {"assertions": assertions + 2, "cache_hits": hits,
                "invalidations": invalidations,
                "scope": "SQLite/Python oracle for conservative cache invalidation; not OpDB"}
    finally:
        db.close()


def probe_r02(seed):
    """R02: SQLite page/WAL accounting; never claim these are physical SSD bytes."""
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="opdb-r02-") as directory:
        path = Path(directory) / "probe.db"
        db = sqlite3.connect(str(path))
        try:
            mode = db.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA wal_autocheckpoint=0")
            db.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, val INTEGER)")
            values = [(k, rng.randrange(-5000, 5001)) for k in range(420)]
            db.executemany("INSERT INTO kv VALUES(?,?)", values)
            db.commit()
            size_page = db.execute("PRAGMA page_size").fetchone()[0]
            page_count = db.execute("PRAGMA page_count").fetchone()[0]
            wal_path = Path(str(path) + "-wal")
            wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
            actual = db.execute("SELECT SUM(val) FROM kv").fetchone()[0]
            expected = sum(v for _, v in values)
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            if mode != "wal" or size_page <= 0 or page_count <= 0 or actual != expected:
                raise AssertionError("SQLite WAL/page-count/source mismatch")
            if integrity != "ok" or wal_bytes <= 0:
                raise AssertionError("SQLite file/WAL integrity or sizing mismatch")
            return {"assertions": 6, "sqlite_pages": page_count,
                    "page_bytes": size_page, "sqlite_wal_bytes": wal_bytes,
                    "scope": "Logical SQLite page count and WAL file size only; no device I/O"}
        finally:
            db.close()


def probe_r04(seed):
    """R04: equal-capacity toy LRU/FIFO miss accounting and residency bounds."""
    rng = random.Random(seed)
    trace = []
    for step in range(900):
        if step % 170 < 85:
            trace.append(rng.randrange(24))
        else:
            trace.append(rng.randrange(150))
    cap = 16
    lru = OrderedDict()
    fifo_queue = deque()
    fifo_set = set()
    hits_lru = 0
    hits_fifo = 0
    assertions = 0
    for key in trace:
        if key in lru:
            hits_lru += 1
            lru.move_to_end(key)
        else:
            if len(lru) == cap:
                lru.popitem(last=False)
            lru[key] = None
        if key in fifo_set:
            hits_fifo += 1
        else:
            if len(fifo_set) == cap:
                evicted = fifo_queue.popleft()
                fifo_set.remove(evicted)
            fifo_queue.append(key)
            fifo_set.add(key)
        if len(lru) > cap or len(fifo_set) > cap:
            raise AssertionError("cache budget exceeded")
        if fifo_set != set(fifo_queue):
            raise AssertionError("FIFO queue/set divergence")
        assertions += 2
    return {"assertions": assertions, "lru_misses": len(trace)-hits_lru,
            "fifo_misses": len(trace)-hits_fifo,
            "scope": "Toy equal-sized Python LRU/FIFO only; excludes metadata and SSD I/O"}


def probe_r05(seed):
    """R05: a Cost Guard model declines low-confidence, negative-ROI or RAM-heavy plans."""
    rng = random.Random(seed)
    cases = [
        # name, reads, writes, saved/read, build, verify, maintenance/write, memory, confidence, admit
        ("hot_reads", 800, 15, 0.8, 28, 10, 0.02, 32, 0.95, True),
        ("all_writes", 9, 950, 0.8, 28, 10, 0.03, 32, 0.96, False),
        ("large_build", 120, 20, 0.8, 180, 10, 0.02, 32, 0.95, False),
        ("uncertain_forecast", 900, 20, 0.8, 28, 10, 0.02, 32, 0.32, False),
        ("too_much_memory", 900, 20, 0.8, 28, 10, 0.02, 1024, 0.95, False),
    ]
    assertions = 0
    for name, reads, writes, saving, build, verify, maintenance, mem, conf, expected in cases:
        noise_margin = 5 + rng.randrange(3)
        net = reads*saving - build - verify - writes*maintenance - noise_margin
        allow = net > 0 and conf >= 0.80 and mem <= 64
        if allow != expected:
            raise AssertionError("incorrect simulated Cost Guard decision: " + name)
        assertions += 1
    return {"assertions": assertions,
            "scope": "Synthetic utility/cost admission model, not measured I/O or a trained predictor"}


def probe_r06(seed):
    """R06: controlled overlapping WAL transactions illustrate snapshot consistency."""
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="opdb-r06-") as directory:
        path = str(Path(directory) / "snap.db")
        first = sqlite3.connect(path, timeout=4.0, isolation_level=None)
        second = sqlite3.connect(path, timeout=4.0, isolation_level=None)
        try:
            mode = first.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            first.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, val INTEGER)")
            original = rng.randrange(1, 1000)
            first.execute("INSERT INTO kv VALUES(1,?)", (original,))
            first.execute("BEGIN")
            observed = first.execute("SELECT val FROM kv WHERE id=1").fetchone()[0]
            second.execute("BEGIN IMMEDIATE")
            second.execute("UPDATE kv SET val=? WHERE id=1", (original+7,))
            second.execute("COMMIT")
            pinned = first.execute("SELECT val FROM kv WHERE id=1").fetchone()[0]
            first.execute("COMMIT")
            fresh = first.execute("SELECT val FROM kv WHERE id=1").fetchone()[0]
            integrity = first.execute("PRAGMA integrity_check").fetchone()[0]
            if (mode, observed, pinned, fresh, integrity) != (
                "wal", original, original, original+7, "ok"
            ):
                raise AssertionError("WAL snapshot isolation smoke test failed")
            return {"assertions": 5,
                    "scope": "Two SQLite connections/snapshot only; no general OpDB serializability proof"}
        finally:
            first.close()
            second.close()


def probe_r08(seed):
    """R08: include mid-workload DDL in recorded latency distribution."""
    rng = random.Random(seed)
    db = sqlite3.connect(":memory:", cached_statements=0)
    try:
        db.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, tenant INTEGER, bucket INTEGER, val INTEGER)")
        rows = [(k, rng.randrange(10), rng.randrange(100), rng.randrange(-200,201))
                for k in range(2000)]
        db.executemany("INSERT INTO kv VALUES(?,?,?,?)", rows)
        db.commit()
        samples = []
        verified = 0
        for step in range(160):
            t0 = time.perf_counter_ns()
            if step == 40:
                db.execute("CREATE INDEX idx_kv ON kv(tenant,bucket)")
            elif step == 120:
                db.execute("DROP INDEX idx_kv")
            tenant = rng.randrange(10)
            bucket = rng.randrange(100)
            actual = db.execute(
                "SELECT COALESCE(SUM(val),0) FROM kv WHERE tenant=? AND bucket=?",
                (tenant,bucket)
            ).fetchone()[0]
            expected = sum(v for _,t,b,v in rows if t == tenant and b == bucket)
            duration_us = (time.perf_counter_ns() - t0)/1000
            if actual != expected:
                raise AssertionError("index DDL changed SQL results")
            samples.append(duration_us)
            verified += 1
        samples.sort()
        def percentile(p):
            return samples[max(0, math.ceil(len(samples)*p/100)-1)]
        p50,p95,p99,max_us = percentile(50),percentile(95),percentile(99),samples[-1]
        if not (p50 <= p95 <= p99 <= max_us) or max_us <= 0:
            raise AssertionError("invalid measured latency order")
        return {"assertions": verified + 2, "p50_us": round(p50,2),
                "p95_us": round(p95,2), "p99_us": round(p99,2),
                "max_us": round(max_us,2), "count": len(samples),
                "scope": "SQLite in-memory DDL incl. timing; NOT an OpDB p99 guarantee"}
    finally:
        db.close()


def probe_r09(seed):
    """R09: finite fail-closed admission model for automation control."""
    rng = random.Random(seed)
    cases = [
        (True,True,True,True,True,True),
        (False,True,True,True,True,False),
        (True,False,True,True,True,False),
        (True,True,False,True,True,False),
        (True,True,True,False,True,False),
        (True,True,True,True,False,False),
        (True,True,None,True,True,False),
    ]
    assertions = 0
    for capture,proof,source,epoch,budget,expected in cases:
        # A toy policy, not an enforceable external-writer attestation.
        candidate = all(v is True for v in (capture,proof,source,epoch,budget))
        if candidate != expected:
            raise AssertionError("fail-closed admission violated")
        assertions += 1
    if rng.randrange(1000) < 0:
        raise AssertionError("unreachable deterministic random branch")
    return {"assertions": assertions,
            "scope": "Policy model only; no real Proof Gate, privilege enforcement or rollback"}


def probe_p0_negative_control(seed):
    """Deliberately demonstrate stale unprotected Lens after external COMMIT.

    The return value means a known *unsafe* implementation was falsified,
    never that Safety/Core have successfully blocked the actual issue.
    """
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="opdb-p0-") as directory:
        path = str(Path(directory) / "counterexample.db")
        first = sqlite3.connect(path)
        first.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, val INTEGER)")
        before = rng.randrange(1,100)
        first.execute("INSERT INTO kv VALUES(1,?)", (before,))
        first.commit()
        lens_cache = before  # deliberately unguarded, unsafe
        external = sqlite3.connect(path)
        try:
            external.execute("UPDATE kv SET val=? WHERE id=1", (before+10,))
            external.commit()
        finally:
            external.close()
        actual = first.execute("SELECT val FROM kv WHERE id=1").fetchone()[0]
        integrity = first.execute("PRAGMA integrity_check").fetchone()[0]
        first.close()
        if actual == lens_cache or actual != before + 10 or integrity != "ok":
            raise AssertionError("expected stale-Lens negative control no longer detected")
        return {"assertions": 3, "outcome": "EXPECTED_STALE_LENS_DETECTED",
                "scope": "Intentionally unsafe Python cache vs SQLite external COMMIT; NOT target OpDB"}
