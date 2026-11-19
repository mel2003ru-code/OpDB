"""TASK-017: cost of NumericTruthStore.rebuild() and of opening an untrusted file.

Modes:
  --phases  split one rebuild into its steps. The steps reproduce the
            pre-TASK-017 rebuild() on the store's own connection (same SQL,
            same order), plus the sorted-insert candidate, timed one by one,
            then rolled back; the real rebuild() of the checked-out code is
            timed too.
  default   time rebuild() and first open of an untrusted file, --runs times.
Files are built by inserting Source rows with plain SQL, then opening the store
once (which rebuilds). Usage:
  python experiments/m17_rebuild_bench.py --rows 100000 --runs 7 --out r.json
"""
import argparse, json, os, platform, random, sqlite3, statistics, subprocess
import sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import NumericTruthStore
from opdb.core import _key
from opdb.numeric import _decode, _group, INT64_MIN, INT64_MAX, SCHEMA_VERSION

GROUPS, SPAN = 1000, 1 << 40


def build(path, rows, seed):
    rng = random.Random(seed)
    NumericTruthStore(path).close()           # creates the schema
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("BEGIN")
    con.executemany("INSERT INTO opdb_source_kv(k,v) VALUES (?,?)",
                    ((f"grp{rng.randrange(GROUPS)}/{i}",
                      rng.randrange(-SPAN, SPAN).to_bytes(8, "big", signed=True))
                     for i in range(rows)))
    con.execute("UPDATE opdb_meta SET commit_seq=commit_seq+1")
    con.execute("COMMIT")
    con.close()
    st = NumericTruthStore(path)              # first rebuild; makes it trusted
    assert st.open_mode == "REBUILT", st.open_mode
    st.close()


def make_untrusted(path):
    con = sqlite3.connect(path, isolation_level=None)
    con.execute("UPDATE opdb_nlens_meta SET lens_seq=lens_seq-1")
    con.close()


def phases(path):
    st = NumericTruthStore(path)
    db, fn, out = st._db, st._fn, {}
    t = time.perf_counter_ns

    def mark(name, t0):
        out[name] = (t() - t0) / 1e6
        return t()

    t0 = t()
    db.execute("BEGIN IMMEDIATE")
    t0 = mark("begin", t0)
    raw = db.execute("SELECT k,typeof(v),v FROM opdb_source_kv").fetchall()
    t0 = mark("source scan (fetch rows)", t0)
    rows = []
    for k, kind, v in raw:
        _key(k)
        if kind != "blob":
            raise RuntimeError
        rows.append((_group(fn, k), k, _decode(v)))
    t0 = mark("key validation, grouping, decode (Python)", t0)
    groups, vals = {}, []
    for g, k, x in rows:
        p = groups.setdefault(g, [0, 0])
        p[0] += 1
        p[1] += x
        vals.append((g, x, k))
    assert all(INT64_MIN <= p[1] <= INT64_MAX for p in groups.values())
    t0 = mark("in-memory aggregation", t0)
    db.execute("DELETE FROM opdb_nlens_group")
    t0 = mark("DELETE opdb_nlens_group", t0)
    db.execute("DELETE FROM opdb_nlens_val")
    t0 = mark("DELETE opdb_nlens_val", t0)
    db.executemany("INSERT INTO opdb_nlens_group VALUES (?,?,?)",
                   ((g, p[0], p[1]) for g, p in groups.items()))
    t0 = mark("INSERT opdb_nlens_group", t0)
    db.executemany("INSERT INTO opdb_nlens_val VALUES (?,?,?)", vals)
    t0 = mark("INSERT opdb_nlens_val (Source order, as before TASK-017)", t0)
    db.execute("DELETE FROM opdb_nlens_val")
    t0 = t()
    vals.sort()
    t0 = mark("sort vals (Python, candidate)", t0)
    db.executemany("INSERT INTO opdb_nlens_val VALUES (?,?,?)", vals)
    t0 = mark("INSERT opdb_nlens_val (sorted)", t0)
    db.execute("INSERT OR REPLACE INTO opdb_nlens_meta VALUES (1,?,?,?,?)",
               (SCHEMA_VERSION, st._seq(), st._name, len(vals)))
    t0 = mark("meta write", t0)
    db.execute("ROLLBACK")      # COMMIT cost is measured on the real rebuild()
    out["COMMIT"] = "unavailable here (see rebuild() total minus the steps)"
    t1 = t()
    st.rebuild()
    out["real rebuild() total"] = (t() - t1) / 1e6
    st.close()
    return out


def timed(path, runs):
    st = NumericTruthStore(path)
    reb = []
    for _ in range(runs):
        t0 = time.perf_counter_ns()
        st.rebuild()
        reb.append((time.perf_counter_ns() - t0) / 1e6)
    st.close()
    opn = []
    for _ in range(runs):
        make_untrusted(path)
        t0 = time.perf_counter_ns()
        st = NumericTruthStore(path)
        opn.append((time.perf_counter_ns() - t0) / 1e6)
        assert st.open_mode == "REBUILT", st.open_mode
        st.close()
    return {"rebuild_ms": reb, "untrusted_open_ms": opn}


def machine():
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                         text=True, cwd=os.path.dirname(__file__)).stdout.strip()
    cpu = ""
    try:
        cpu = next(l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo")
                   if l.startswith("model name"))
    except (OSError, StopIteration):
        pass
    return {"sha": sha, "cpu": cpu, "cpus": os.cpu_count(),
            "os": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, nargs="+", default=[10000, 100000])
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--phases", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    res = {"machine": machine(), "runs": a.runs, "results": {}}
    for n in a.rows:
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r.db")
            build(path, n, a.seed)
            r = phases(path) if a.phases else timed(path, a.runs)
        if not a.phases:
            for k in list(r):
                r[k + "_median"] = statistics.median(r[k])
                r[k + "_worst"] = max(r[k])
        res["results"][n] = r
        print(n, json.dumps({k: v for k, v in r.items()
                             if not isinstance(v, list)}), flush=True)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
