"""TASK-013: split the cost of one 1,000-operation PersistentTruthStore batch.
Usage: python experiments/m3_write_profile.py [rows...]   (JSON lines)
Phases are timed by re-running the same statements as PersistentTruthStore.apply
inside one BEGIN IMMEDIATE ... ROLLBACK on a private connection, so they are an
approximation of the real path, not an instrumented copy of it. Shapes: new keys,
overwrites, deletes, mixed. 'total_apply_ms' is the real apply() median."""
import json, os, platform, random, sqlite3, statistics, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import PersistentTruthStore, TruthStore
from m3_persistent_bench import build


def ops_for(shape, rnd, r, rows):
    if shape == "new":
        return [("put", f"g{i % 50}/n{r}-{i}", b"x" * 10) for i in range(1000)]
    ids = rnd.sample(range(rows), 1000)
    key = lambda i: f"g{i % 1000}/{i}"
    if shape == "overwrite":
        return [("put", key(i), b"y" * 10) for i in ids]
    if shape == "delete":
        return [("delete", key(i)) for i in ids]
    return [("put", f"g{i % 50}/m{r}-{i}", b"x") if i % 3 == 0 else
            (("put", key(ids[i]), b"z") if i % 3 == 1 else ("delete", key(ids[i])))
            for i in range(1000)]


def p95(xs):
    xs = sorted(xs); return xs[min(len(xs) - 1, int(0.95 * len(xs)))]


def run(rows, shape, reps, out_phases):
    res = {}
    for name, make in (("persistent", PersistentTruthStore),
                       ("memory_lens", lambda p: TruthStore(p, lens=True)),
                       ("source_only", lambda p: TruthStore(p))):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "db"); build(p, rows)
            if name == "persistent":   # build() writes Source raw while closed: rebuild the Lens first
                q = PersistentTruthStore(p); q.rebuild(); q.close()
            s = make(p); rnd = random.Random(1); t_all = []
            for r in range(reps):
                ops = ops_for(shape, rnd, r, rows)
                t = time.perf_counter(); s.apply(ops); t_all.append(time.perf_counter() - t)
            s.close()
            res[name] = {"median_ms": round(statistics.median(t_all) * 1000, 2),
                         "p95_ms": round(p95(t_all) * 1000, 2),
                         "raw_ms": [round(x * 1000, 1) for x in t_all]}
    return res


def phases(rows, reps):
    """Time pieces of the persisted write path (new-key batches)."""
    from opdb.lens import group_of
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "db"); build(p, rows)
        db = sqlite3.connect(p, isolation_level=None, cached_statements=0)
        db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=FULL")
        acc = {k: [] for k in ("lookup", "source_execute_loop", "source_executemany",
                               "lens_upserts_loop", "neg_check", "delete_zero", "meta_update", "rollback_stand_in_for_commit")}
        for r in range(reps):
            ops = [("put", f"g{i % 50}/q{r}-{i}", b"x" * 10) for i in range(1000)]
            def tm(key, fn):
                t = time.perf_counter(); fn(); acc[key].append(time.perf_counter() - t)
            for variant in ("loop", "many"):
                db.execute("BEGIN IMMEDIATE")
                keys = [o[1] for o in ops]
                if variant == "loop":
                    tm("lookup", lambda: [db.execute("SELECT k,typeof(v),length(v) FROM opdb_source_kv WHERE k IN (%s)" % ",".join("?" * len(c)), c).fetchall()
                                          for c in (keys[:500], keys[500:])])
                    def f():
                        for o in ops:
                            db.execute("INSERT INTO opdb_source_kv(k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (o[1], o[2]))
                    tm("source_execute_loop", f)
                else:
                    tm("source_executemany", lambda: db.executemany("INSERT INTO opdb_source_kv(k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", ((o[1], o[2]) for o in ops)))
                tm("meta_update", lambda: db.execute("UPDATE opdb_meta SET commit_seq=commit_seq+1 WHERE singleton=1"))
                if variant == "loop":
                    def f():
                        for g in range(50):
                            db.execute("INSERT INTO opdb_lens_group(g,n,b) VALUES (?,?,?) ON CONFLICT(g) DO UPDATE SET n=n+?, b=b+?", (f"g{g}", 20, 200, 20, 200))
                    tm("lens_upserts_loop", f)
                tm("neg_check", lambda: db.execute("SELECT 1 FROM opdb_lens_group WHERE n<0 OR b<0 LIMIT 1").fetchone())
                tm("delete_zero", lambda: db.execute("DELETE FROM opdb_lens_group WHERE n=0"))
                t = time.perf_counter(); db.execute("ROLLBACK"); acc["rollback_stand_in_for_commit"].append(time.perf_counter() - t)
        db.close()
    return {k: (round(statistics.median(v) * 1000, 3) if v else "unavailable") for k, v in acc.items()}


def main(sizes, reps=30):
    cpu = open("/proc/cpuinfo").read().split("model name")[1].split(":")[1].split("\n")[0].strip()
    print(json.dumps({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version, "cpu": cpu,
                      "cpus": os.cpu_count(), "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}))
    for rows in sizes:
        print(json.dumps({"rows": rows, "phase_median_ms_new_keys_rolled_back": phases(rows, reps)}))
        for shape in ("new", "overwrite", "delete", "mixed"):
            print(json.dumps({"rows": rows, "shape": shape, **run(rows, shape, reps, None)}))


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [10000, 100000])
