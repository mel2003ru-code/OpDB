"""TASK-015 (M5): same aggregate workload on plain SQLite (A, B) and OpDB (C, D).

A  sqlite3 table + covering index (g,x); aggregate by SELECT ... WHERE g=?
B  sqlite3 table + summary table kept by SQL triggers (min/max via the (g,x) index)
C  NumericTruthStore.numeric_stats          (Lens)
D  NumericTruthStore.numeric_stats_source   (Source recomputation, same file as C)

All contenders: journal_mode=WAL, synchronous=FULL (what OpDB sets itself).
Every contender is compared with an independent dict model before and after
each workload; any mismatch aborts the run. D is a full scan per call, so on
1M rows it is checked on a seeded sample of groups instead of all of them.
Usage: python experiments/m5_compare.py --sizes 10000 100000 1000000 --seed 15 --runs 15 --json out.json
"""
import argparse
import json
import os
import platform
import random
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import NumericTruthStore

GROUPS, BATCH, SPAN = 1000, 1000, 1 << 40
PRAGMAS = {"journal_mode": "WAL", "synchronous": "FULL"}


def enc(x):
    return x.to_bytes(8, "big", signed=True)


def gof(key):
    return key.split("/", 1)[0]


def fixture(n, seed):
    rng = random.Random(seed)
    return {f"grp{i % GROUPS}/{i}": rng.randrange(-SPAN, SPAN) for i in range(n)}


def model_stats(model):
    out = {}
    for k, x in model.items():
        out.setdefault(gof(k), []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in out.items()}


# ---- plain SQLite contenders -------------------------------------------
SQL_A = ("CREATE TABLE kv (k TEXT PRIMARY KEY, g TEXT NOT NULL, x INTEGER NOT NULL);"
         "CREATE INDEX kv_gx ON kv(g,x);")
SQL_B_SUMMARY = ("CREATE TABLE summ (g TEXT PRIMARY KEY, n INTEGER NOT NULL, s INTEGER NOT NULL,"
                 " mn INTEGER NOT NULL, mx INTEGER NOT NULL);")
SQL_B_TRIGGERS = """
CREATE TRIGGER kv_ai AFTER INSERT ON kv BEGIN
 INSERT INTO summ VALUES (NEW.g,1,NEW.x,NEW.x,NEW.x)
 ON CONFLICT(g) DO UPDATE SET n=n+1, s=s+NEW.x, mn=min(mn,NEW.x), mx=max(mx,NEW.x);
END;
CREATE TRIGGER kv_au AFTER UPDATE OF x ON kv BEGIN
 UPDATE summ SET s=s-OLD.x+NEW.x,
   mn=(SELECT min(x) FROM kv WHERE g=NEW.g), mx=(SELECT max(x) FROM kv WHERE g=NEW.g)
 WHERE g=NEW.g;
END;
CREATE TRIGGER kv_ad AFTER DELETE ON kv BEGIN
 UPDATE summ SET n=n-1, s=s-OLD.x,
   mn=coalesce((SELECT min(x) FROM kv WHERE g=OLD.g),0),
   mx=coalesce((SELECT max(x) FROM kv WHERE g=OLD.g),0) WHERE g=OLD.g;
 DELETE FROM summ WHERE g=OLD.g AND n=0;
END;
"""


def sql_open(path):
    db = sqlite3.connect(path, isolation_level=None)
    for k, v in PRAGMAS.items():
        db.execute(f"PRAGMA {k}={v}")
    return db


class Plain:
    def __init__(self, path, triggers):
        self.path, self.triggers = path, triggers
        self.db = sql_open(path)

    def build(self, model):
        self.db.executescript(SQL_A)
        self.db.execute("BEGIN")
        self.db.executemany("INSERT INTO kv VALUES (?,?,?)",
                            ((k, gof(k), x) for k, x in model.items()))
        self.db.execute("COMMIT")
        if self.triggers:   # bulk load first, then summarise, then arm the triggers
            self.db.executescript(SQL_B_SUMMARY)
            self.db.execute("INSERT INTO summ SELECT g,count(*),sum(x),min(x),max(x) FROM kv GROUP BY g")
            self.db.executescript(SQL_B_TRIGGERS)

    def read(self, g):
        if self.triggers:
            r = self.db.execute("SELECT n,s,mn,mx FROM summ WHERE g=?", (g,)).fetchone()
            return r or (0, 0, None, None)
        n, s, mn, mx = self.db.execute(
            "SELECT count(*),sum(x),min(x),max(x) FROM kv WHERE g=?", (g,)).fetchone()
        return (n, s or 0, mn, mx)

    def apply(self, ops):
        self.db.execute("BEGIN IMMEDIATE")
        for op, k, x in ops:
            if op == "put":
                self.db.execute("INSERT INTO kv VALUES (?,?,?) ON CONFLICT(k) DO UPDATE SET x=excluded.x",
                                (k, gof(k), x))
            else:
                self.db.execute("DELETE FROM kv WHERE k=?", (k,))
        self.db.execute("COMMIT")

    def close(self):
        self.db.close()


class Lens:
    def __init__(self, path, source=False):
        self.path, self.source = path, source
        self.store = NumericTruthStore(path)

    def build(self, model):
        self.store.close()
        db = sql_open(self.path)
        db.execute("BEGIN")
        db.executemany("INSERT OR REPLACE INTO opdb_source_kv VALUES (?,?)",
                       ((k, enc(x)) for k, x in model.items()))
        db.execute("COMMIT")
        db.close()
        self.store = NumericTruthStore(self.path)
        self.store.rebuild()    # raw bulk load bypasses apply(); build the Lens explicitly

    def read(self, g):
        f = self.store.numeric_stats_source if self.source else self.store.numeric_stats
        s = f(g)
        if not self.source:
            assert s.served_from == "LENS"
        return (s.count, s.total, s.minimum, s.maximum)

    def apply(self, ops):
        self.store.apply([("put", k, enc(x)) if op == "put" else ("delete", k) for op, k, x in ops])

    def close(self):
        self.store.close()


def check(c, model, groups, label):
    want = model_stats(model)
    for g in groups:
        got = c.read(g)
        exp = want.get(g, (0, 0, None, None))
        if tuple(got) != tuple(exp):
            raise SystemExit(f"MISMATCH {label} group {g}: got {got} expected {exp}")


def apply_model(model, ops):
    for op, k, x in ops:
        if op == "put":
            model[k] = x
        else:
            model.pop(k, None)


def med(xs):
    return round(statistics.median(xs) * 1000, 3)


def run_size(n, seed, runs, tmp):
    rng = random.Random(seed * 7 + n)
    model = fixture(n, seed)
    all_groups = [f"grp{i}" for i in range(GROUPS)] + ["grp-missing"]
    sample = rng.sample(all_groups, 20)
    paths = {c: os.path.join(tmp, f"{n}_{c}.db") for c in "ABC"}
    A, B, C = Plain(paths["A"], False), Plain(paths["B"], True), Lens(paths["C"])
    D = Lens.__new__(Lens)
    t0 = time.perf_counter()
    for c in (A, B, C):
        c.build(model)
    D.path, D.source, D.store = paths["C"], True, C.store
    full_d = all_groups if n <= 10000 else sample
    cont = {"A": A, "B": B, "C": C, "D": D}
    for name, c in cont.items():
        check(c, model, full_d if name == "D" else all_groups, f"{name} initial")
    out = {"rows": n, "build_s": round(time.perf_counter() - t0, 2), "reads_ms": {}, "writes_ms": {},
           "bytes": {}, "open_ms": {}, "raw": {}}
    probe = [rng.choice(all_groups[:-1]) for _ in range(runs)]
    for name, c in cont.items():             # one-group aggregate read
        reps = runs if name == "D" else max(runs, 200)
        xs = []
        for i in range(reps):
            g = probe[i % runs]
            t = time.perf_counter(); c.read(g); xs.append(time.perf_counter() - t)
        out["reads_ms"][name] = med(xs); out["raw"][f"read_{name}"] = [round(x * 1000, 4) for x in xs]
    # write workloads (A, B, C; D shares C's file). Same operations for all.
    keys = sorted(model)
    nxt = n
    wl = {"insert": [], "overwrite": [], "delete": []}
    for r in range(runs):
        new = [("put", f"grp{(nxt + i) % GROUPS}/{nxt + i}", rng.randrange(-SPAN, SPAN)) for i in range(BATCH)]
        nxt += BATCH
        wl["insert"].append(new)
        pick = rng.sample(keys, BATCH)
        wl["overwrite"].append([("put", k, rng.randrange(-SPAN, SPAN)) for k in pick])
        wl["delete"].append([("delete", k, None) for k in rng.sample(keys, BATCH)])
    for kind in wl:
        t = {c: [] for c in "ABC"}
        for r in range(runs):
            ops = wl[kind][r]
            before = dict(model)
            for name in "ABC":
                c = cont[name]
                s = time.perf_counter(); c.apply(ops); t[name].append(time.perf_counter() - s)
            apply_model(model, ops)
            if r == runs - 1 or r == 0:
                for name in "ABC":
                    check(cont[name], model, all_groups, f"{name} after {kind}")
                check(D, model, sample, f"D after {kind}")
            # restore untimed so every run starts from the same size
            undo = ([("delete", k, None) for _, k, _ in ops] if kind == "insert" else
                    [("put", k, before[k]) for _, k, _ in ops if k in before])
            for name in "ABC":
                cont[name].apply(undo)
            apply_model(model, undo)
        out["writes_ms"][kind] = {c: med(t[c]) for c in "ABC"}
        out["raw"][f"write_{kind}"] = {c: [round(x * 1000, 3) for x in t[c]] for c in "ABC"}
    for name in "ABC":
        check(cont[name], model, all_groups, f"{name} final")
    for c in (A, B, C):
        c.close()
    for c, p in paths.items():
        out["bytes"][c] = sum(os.path.getsize(p + s) for s in ("", "-wal") if os.path.exists(p + s))
    out["bytes"]["D"] = out["bytes"]["C"]
    # open an existing file + first read
    for name in "ABC":
        xs = []
        for _ in range(runs):
            t = time.perf_counter()
            if name == "C":
                st = NumericTruthStore(paths["C"]); assert st.open_mode == "PERSISTED"
                st.numeric_stats("grp1"); st.close()
            else:
                p = Plain(paths[name], name == "B"); p.read("grp1"); p.close()
            xs.append(time.perf_counter() - t)
        out["open_ms"][name] = med(xs)
        out["raw"][f"open_{name}"] = [round(x * 1000, 3) for x in xs]
    out["open_ms"]["D"] = out["open_ms"]["C"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[10000, 100000, 1000000])
    ap.add_argument("--seed", type=int, default=15)
    ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--json")
    a = ap.parse_args()
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                         cwd=os.path.dirname(__file__)).stdout.strip()
    cpu = next((l.split(":")[1].strip() for l in open("/proc/cpuinfo") if "model name" in l), "?") \
        if os.path.exists("/proc/cpuinfo") else platform.processor()
    res = {"machine": {"cpu": cpu, "cpus": os.cpu_count(), "platform": platform.platform(),
                       "python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "sha": sha},
           "pragmas": PRAGMAS, "seed": a.seed, "runs": a.runs, "batch": BATCH, "groups": GROUPS, "sizes": []}
    with tempfile.TemporaryDirectory() as tmp:
        for n in a.sizes:
            res["sizes"].append(run_size(n, a.seed, a.runs, tmp))
            print(json.dumps({k: v for k, v in res["sizes"][-1].items() if k != "raw"}), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1)


if __name__ == "__main__":
    main()
