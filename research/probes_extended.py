"""Small independent laboratory probes; no source of truth other than SQLite for SQL tests.

These are deliberately bounded sanity/falsification checks. They are not a DBMS,
not complete proofs, not official third-party benchmark replications.
"""
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
import math
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path


def r01_repeated_computation(seed):
    """Compare exact aggregates with a trigger-maintained view after mutations."""
    rng = random.Random(seed)
    c = sqlite3.connect(":memory:")
    try:
        c.executescript("""
        CREATE TABLE kv (id INTEGER PRIMARY KEY, tenant INTEGER NOT NULL, val INTEGER NOT NULL);
        CREATE TABLE sums (tenant INTEGER PRIMARY KEY, total INTEGER NOT NULL);
        CREATE TRIGGER kv_ai AFTER INSERT ON kv BEGIN
          INSERT INTO sums VALUES(new.tenant,new.val)
          ON CONFLICT(tenant) DO UPDATE SET total=total+excluded.total;
        END;
        CREATE TRIGGER kv_au AFTER UPDATE ON kv BEGIN
          UPDATE sums SET total=total-old.val WHERE tenant=old.tenant;
          INSERT INTO sums VALUES(new.tenant,new.val)
          ON CONFLICT(tenant) DO UPDATE SET total=total+excluded.total;
        END;
        CREATE TRIGGER kv_ad AFTER DELETE ON kv BEGIN
          UPDATE sums SET total=total-old.val WHERE tenant=old.tenant;
        END;
        """)
        data = {}
        init_start = time.perf_counter_ns()
        for ident in range(150):
            t, v = rng.randrange(8), rng.randrange(-500, 500)
            c.execute("INSERT INTO kv VALUES(?,?,?)",(ident,t,v))
            data[ident]=(t,v)
        c.commit()
        initial_build_ns=time.perf_counter_ns()-init_start
        checks = 0
        for _ in range(120):
            ident=rng.randrange(190)
            op=rng.randrange(3)
            if op==2:
                c.execute("DELETE FROM kv WHERE id=?",(ident,))
                data.pop(ident,None)
            else:
                t,v=rng.randrange(8),rng.randrange(-500,500)
                c.execute("INSERT INTO kv VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET tenant=excluded.tenant,val=excluded.val",(ident,t,v))
                data[ident]=(t,v)
            c.commit()
            for tenant in range(8):
                reference=sum(value for t,value in data.values() if t==tenant)
                direct=c.execute("SELECT COALESCE(SUM(val),0) FROM kv WHERE tenant=?",(tenant,)).fetchone()[0]
                derived=c.execute("SELECT COALESCE((SELECT total FROM sums WHERE tenant=?),0)",(tenant,)).fetchone()[0]
                if reference!=direct or reference!=derived:
                    raise AssertionError("R01 stale derived sum")
                checks+=1
        return {
            "assertions":checks,"initial_build_ms":round(initial_build_ns/1e6,3),
            "scope":"SQLite trigger-maintained aggregate vs independent Python oracle; exact results, no speedup claim"
        }
    finally:
        c.close()


def r02_logical_write_cost(seed):
    """Page-count baseline with vs without index; no claim about physical SSD I/O."""
    rng=random.Random(seed)
    rows=[(i,rng.randrange(16),rng.randrange(128),rng.randrange(-1000,1000))
          for i in range(1100)]
    updates=[rng.randrange(1100) for _ in range(180)]
    out={}
    with tempfile.TemporaryDirectory(prefix="opdb-r02-") as d:
        for indexed in (False,True):
            path=Path(d)/("with-index.sqlite" if indexed else "without-index.sqlite")
            con=sqlite3.connect(str(path))
            try:
                con.execute("PRAGMA journal_mode=DELETE")
                con.execute("PRAGMA synchronous=FULL")
                con.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY,tenant INTEGER,bucket INTEGER,v INTEGER)")
                con.executemany("INSERT INTO kv VALUES(?,?,?,?)",rows)
                if indexed:
                    con.execute("CREATE INDEX idx_tenant_bucket ON kv(tenant,bucket)")
                con.commit()
                for ident in updates:
                    con.execute("UPDATE kv SET bucket=(bucket+1)%128, v=v+1 WHERE id=?",(ident,))
                con.commit()
                state=con.execute("SELECT id,tenant,bucket,v FROM kv ORDER BY id").fetchall()
                integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity!="ok":
                    raise AssertionError("R02 integrity failure")
                logical=con.execute("PRAGMA page_count").fetchone()[0]*con.execute("PRAGMA page_size").fetchone()[0]
                out["indexed" if indexed else "no_index"]={
                    "state":state,
                    "logical_file_bytes":logical,
                    "file_size_bytes":path.stat().st_size,
                }
            finally:
                con.close()
    if out["indexed"]["state"]!=out["no_index"]["state"]:
        raise AssertionError("R02 index changed authoritative rows")
    return {
        "assertions":len(updates)+2,
        "without_index_file_bytes":out["no_index"]["logical_file_bytes"],
        "with_index_file_bytes":out["indexed"]["logical_file_bytes"],
        "scope":"SQLite logical page footprint and identical rows after updates; NOT measured physical write amplification"
    }


def r04_cache_policies(seed):
    """FIFO and LRU reference cache models; verify exact accounting."""
    rng=random.Random(seed)
    cap=16
    trace=[(i//120)%8*10+rng.randrange(11) if i%9 else rng.randrange(180)
           for i in range(1500)]
    fifo=OrderedDict()
    lru=OrderedDict()
    stats={"FIFO":[0,0],"LRU":[0,0]}
    for key in trace:
        for name, cache in (("FIFO",fifo),("LRU",lru)):
            if key in cache:
                stats[name][0]+=1
                if name=="LRU":
                    cache.move_to_end(key)
            else:
                stats[name][1]+=1
                if len(cache)>=cap:
                    cache.popitem(last=False)
                cache[key]=None
            if len(cache)>cap:
                raise AssertionError("cache exceeds fixed capacity")
    for name,(hit,miss) in stats.items():
        if hit+miss!=len(trace):
            raise AssertionError("cache accounting violation "+name)
    return {
        "assertions":len(trace)*2,
        "fifo_misses":stats["FIFO"][1],"lru_misses":stats["LRU"][1],
        "scope":"Deterministic Python FIFO/LRU miss accounting at equal page capacity; no real I/O or ARC comparison"
    }


def r05_prediction_cost_guard(seed):
    """Synthetic phase workload; never prefetch under low confidence/negative gain."""
    rng=random.Random(seed)
    events=[(i//80)*17 for i in range(400)]
    events += [rng.randrange(500) for _ in range(400)]
    recent=deque(maxlen=32)
    attempted=0
    admitted=0
    false_prefetch=0
    guarded_negative=0
    for target in events:
        if len(recent)>=8:
            dominant=max(set(recent),key=lambda v:(sum(z==v for z in recent),-v))
            confidence=sum(x==dominant for x in recent)/len(recent)
            net_gain=(confidence*4.0)-(1-confidence)*7.0-1.0
            allowed=confidence>=0.8 and net_gain>0
            attempted+=1
            if allowed:
                admitted+=1
                false_prefetch+=int(dominant!=target)
                if net_gain<=0:
                    raise AssertionError("R05 admitted negative prediction")
            else:
                guarded_negative+=1
        recent.append(target)
    if admitted==0 or guarded_negative==0:
        raise AssertionError("R05 synthetic controls failed to exercise both branches")
    return {
        "assertions":attempted,
        "admitted":admitted,"rejected":guarded_negative,"wrong_predictions":false_prefetch,
        "scope":"Synthetic phase-change prediction guard; cost parameters assumed, NOT real SSD prefetch"
    }


def r06_sqlite_concurrency(seed):
    """Independent SQLite writers and read-snapshot behavior; not OpDB isolation."""
    del seed
    with tempfile.TemporaryDirectory(prefix="opdb-r06-") as d:
        path=str(Path(d)/"write.sqlite")
        master=sqlite3.connect(path, isolation_level=None)
        master.execute("PRAGMA journal_mode=WAL")
        master.execute("CREATE TABLE counter(value INTEGER NOT NULL)")
        master.execute("INSERT INTO counter VALUES(0)")
        master.close()
        def worker(_):
            con=sqlite3.connect(path,timeout=12,isolation_level=None)
            con.execute("PRAGMA busy_timeout=12000")
            try:
                for _ in range(24):
                    con.execute("BEGIN IMMEDIATE")
                    try:
                        val=con.execute("SELECT value FROM counter").fetchone()[0]
                        con.execute("UPDATE counter SET value=?",(val+1,))
                        con.execute("COMMIT")
                    except BaseException:
                        con.execute("ROLLBACK")
                        raise
            finally:
                con.close()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(worker,range(4)))
        reader=sqlite3.connect(path,isolation_level=None)
        writer=sqlite3.connect(path,isolation_level=None)
        try:
            reader.execute("BEGIN")
            observed=reader.execute("SELECT value FROM counter").fetchone()[0]
            if observed!=96:
                raise AssertionError("R06 confirmed write lost")
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE counter SET value=value+9")
            writer.execute("COMMIT")
            old=reader.execute("SELECT value FROM counter").fetchone()[0]
            if old!=96:
                raise AssertionError("R06 snapshot changed under active reader")
            reader.execute("COMMIT")
            fresh=reader.execute("SELECT value FROM counter").fetchone()[0]
            if fresh!=105:
                raise AssertionError("R06 snapshot did not advance after commit")
            if reader.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("R06 integrity failure")
        finally:
            writer.close()
            reader.close()
    return {
        "assertions":100,
        "scope":"SQLite WAL concurrent writers + snapshot visibility; NOT independent OpDB linearizability"
    }


def r08_tail_latency(seed):
    """Measure queries and DDL in the same event stream; assert quantile accounting."""
    rng=random.Random(seed)
    con=sqlite3.connect(":memory:",cached_statements=0)
    try:
        con.execute("CREATE TABLE kv(id INTEGER PRIMARY KEY, tenant INTEGER, bucket INTEGER,v INTEGER)")
        con.executemany("INSERT INTO kv VALUES(?,?,?,?)",[(i,rng.randrange(16),rng.randrange(128),rng.randrange(100)) for i in range(1500)])
        con.commit()
        events=[]
        for idx in range(160):
            t0=time.perf_counter_ns()
            if idx==35:
                con.execute("CREATE INDEX idx_t_b ON kv(tenant,bucket)")
            elif idx==85:
                con.execute("DROP INDEX idx_t_b")
            elif idx==130:
                con.execute("CREATE INDEX idx_t_b ON kv(tenant,bucket)")
            else:
                t,b=rng.randrange(16),rng.randrange(128)
                con.execute("SELECT COALESCE(SUM(v),0) FROM kv WHERE tenant=? AND bucket=?",(t,b)).fetchone()[0]
            events.append(max(0,time.perf_counter_ns()-t0))
        ordered=sorted(events)
        q=lambda p:ordered[max(0,math.ceil(len(ordered)*p)-1)]/1000.0
        p50,p95,p99,mx=q(.50),q(.95),q(.99),ordered[-1]/1000.0
        if not(0<=p50<=p95<=p99<=mx):
            raise AssertionError("R08 quantile accounting invalid")
        return {
            "assertions":len(events),"p50_us":round(p50,3),"p95_us":round(p95,3),
            "p99_us":round(p99,3),"max_us":round(mx,3),
            "scope":"SQLite/Python timing includes 3 inline CREATE/DROP INDEX operations; noisy CI, no SLA claim"
        }
    finally:
        con.close()


def r09_admission_controller(seed):
    """Exercise accept/reject/fallback decisions using declared synthetic costs."""
    del seed
    def admission(expected_queries, scan_cost, lens_cost, build_cost, maintenance, verification, confidence, valid):
        savings=expected_queries*(scan_cost-lens_cost)
        full_cost=build_cost+maintenance+verification
        accepted=bool(valid and confidence>=0.9 and savings>full_cost)
        return accepted, savings-full_cost
    cases=[
        ((200,40,3,1200,60,50,0.98,True),True),
        ((20,40,3,1200,60,50,0.98,True),False),
        ((200,40,3,1200,60,50,0.2,True),False),
        ((200,40,3,1200,60,50,0.98,False),False),
        ((200,5,5,0,0,0,1.0,True),False)
    ]
    for args,expected in cases:
        admitted,net=admission(*args)
        if admitted!=expected or (admitted and net<=0):
            raise AssertionError("R09 cost/validity guard regression")
    return {
        "assertions":len(cases),
        "negative_and_invalid_cases":sum(1 for _,accepted in cases if not accepted),
        "scope":"Illustrative synthetic cost/validity admission model; NOT integrated adaptive OpDB controller"
    }


EXTENDED_PROBES={
    "R01":r01_repeated_computation,"R02":r02_logical_write_cost,
    "R04":r04_cache_policies,"R05":r05_prediction_cost_guard,
    "R06":r06_sqlite_concurrency,"R08":r08_tail_latency,
    "R09":r09_admission_controller
}
MODEL_TRACKS={"R04","R05","R09"}
