"""TASK-016: where does NumericTruthStore.apply spend time in a 1,000-row batch?

A proxy around the store's sqlite3 connection times every statement and groups
it by kind. Statement time is wall-clock inside execute(); "python" is the rest
of apply() (validation, dict building, argument lists). COMMIT is listed apart.
Usage: python experiments/m16_numeric_profile.py --rows 100000 --batches 30 --seed 16
"""
import argparse, os, random, statistics, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import NumericTruthStore

GROUPS, BATCH, SPAN = 1000, 1000, 1 << 40
enc = lambda x: x.to_bytes(8, "big", signed=True)


def kind(sql):
    s = " ".join(sql.split())[:60]
    for tag, pat in (("commit", "COMMIT"), ("begin", "BEGIN"),
                     ("source old-value lookup", "SELECT k,typeof(v),v FROM opdb_source_kv"),
                     ("lens group lookup", "SELECT g,n,s FROM opdb_nlens_group"),
                     ("source upsert", "INSERT INTO opdb_source_kv"),
                     ("source delete", "DELETE FROM opdb_source_kv"),
                     ("commit_seq update", "UPDATE opdb_meta"),
                     ("val delete", "DELETE FROM opdb_nlens_val"),
                     ("val insert", "INSERT INTO opdb_nlens_val"),
                     ("group upsert", "INSERT OR REPLACE INTO opdb_nlens_group"),
                     ("group delete", "DELETE FROM opdb_nlens_group"),
                     ("nlens meta update", "UPDATE opdb_nlens_meta"),
                     ("data_version/seq reads", "PRAGMA"), ("data_version/seq reads", "SELECT commit_seq")):
        if s.startswith(pat):
            return tag
    return "other: " + s


class Proxy:
    def __init__(self, db, acc):
        self._db, self._acc = db, acc

    def execute(self, sql, *a):
        t = time.perf_counter_ns()
        try:
            return self._db.execute(sql, *a)
        finally:
            self._acc[kind(sql)] = self._acc.get(kind(sql), 0) + time.perf_counter_ns() - t

    def __getattr__(self, n):
        return getattr(self._db, n)


def batch(rng, keys, mode, fresh):
    if mode == "insert":
        return [("put", f"grp{(fresh[0] + i) % GROUPS}/n{fresh[0] + i}", enc(rng.randrange(-SPAN, SPAN))) for i in range(BATCH)], fresh.__setitem__(0, fresh[0] + BATCH)
    ks = rng.sample(keys, BATCH)
    if mode == "overwrite":
        return [("put", k, enc(rng.randrange(-SPAN, SPAN))) for k in ks], None
    return [("delete", k) for k in ks], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100000)
    ap.add_argument("--batches", type=int, default=30)
    ap.add_argument("--seed", type=int, default=16)
    a = ap.parse_args()
    for mode in ("insert", "overwrite", "delete"):
        rng = random.Random(a.seed)
        with tempfile.TemporaryDirectory() as d:
            st = NumericTruthStore(os.path.join(d, "p.db"))
            keys = [f"grp{i % GROUPS}/{i}" for i in range(a.rows)]
            for i in range(0, a.rows, 5000):
                st.apply([("put", k, enc(rng.randrange(-SPAN, SPAN))) for k in keys[i:i + 5000]])
            acc, st._db = {}, Proxy(st._db, {})
            acc = st._db._acc
            fresh, wall = [a.rows + 10**9], []
            for _ in range(a.batches):
                ops, _x = batch(rng, keys, mode, fresh)
                t = time.perf_counter_ns()
                st.apply(ops)
                wall.append(time.perf_counter_ns() - t)
            tot = sum(wall)
            print(f"\n{mode}, {a.rows} rows, {a.batches} batches of {BATCH}: "
                  f"median {statistics.median(wall)/1e6:.2f} ms, total {tot/1e6:.0f} ms")
            sql = sum(acc.values())
            for k, v in sorted(acc.items(), key=lambda kv: -kv[1]):
                print(f"  {k:28s} {v/1e6/a.batches:8.3f} ms/batch  {100*v/tot:5.1f}%")
            print(f"  {'python (rest of apply)':28s} {(tot-sql)/1e6/a.batches:8.3f} ms/batch  {100*(tot-sql)/tot:5.1f}%")
            st._db = st._db._db
            st.close()


main()
