"""TASK-012 measurements. Usage: python experiments/m3_persistent_bench.py [rows...]
Prints JSON lines with raw per-run numbers."""
import json, os, platform, sqlite3, statistics, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import PersistentTruthStore, TruthStore


def build(path, rows):
    PersistentTruthStore(path).close()
    con = sqlite3.connect(path)
    con.executemany("INSERT INTO opdb_source_kv VALUES (?,?)",
                    ((f"g{i % 1000}/{i}", b"v" * (i % 7)) for i in range(rows)))
    con.commit(); con.close()


def batch_overhead(make, path, reps=15):
    s = make(path); times = []
    for r in range(reps):
        ops = [("put", f"g{i % 50}/b{r}-{i}", b"x" * 10) for i in range(1000)]
        t = time.perf_counter(); s.apply(ops); times.append(time.perf_counter() - t)
    s.close(); return times


def main(sizes):
    print(json.dumps({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "cpu": platform.processor() or open("/proc/cpuinfo").read().split("model name")[1].split(":")[1].split("\n")[0].strip(),
        "cpus": os.cpu_count(), "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}))
    for rows in sizes:
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "db")
            build(p, rows)
            t = time.perf_counter(); s = PersistentTruthStore(p); s.rebuild(); rebuild = time.perf_counter() - t; s.close()
            opens = []
            for _ in range(15):
                t = time.perf_counter(); s = PersistentTruthStore(p); opens.append(time.perf_counter() - t)
                assert s.open_mode == "PERSISTED"; s.close()
            opens.sort()
            res = {"rows": rows, "rebuild_s": round(rebuild, 4), "open_s_raw": [round(x, 5) for x in opens],
                   "open_median_s": round(statistics.median(opens), 5), "open_p95_s": round(opens[int(0.95 * len(opens)) - 1 + (len(opens) * 95 % 100 > 0)], 5),
                   "file_bytes": os.path.getsize(p) + (os.path.getsize(p + "-wal") if os.path.exists(p + "-wal") else 0)}
            if rows <= 100000:
                a = batch_overhead(lambda x: PersistentTruthStore(x), p)
                q = os.path.join(d, "legacy"); build(q, rows)
                b = batch_overhead(lambda x: TruthStore(x, lens=True), q)
                res.update(batch1000_persistent_ms_median=round(statistics.median(a) * 1000, 2),
                           batch1000_legacy_lens_ms_median=round(statistics.median(b) * 1000, 2),
                           batch1000_persistent_ms_raw=[round(x * 1000, 1) for x in a],
                           batch1000_legacy_lens_ms_raw=[round(x * 1000, 1) for x in b])
            print(json.dumps(res))


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [10000, 100000, 1000000])
