"""TASK-014 measurements. Usage: python experiments/m4_numeric_bench.py [rows...]
Prints JSON lines with raw per-run numbers (ms)."""
import json, os, platform, sqlite3, statistics, subprocess, sys, tempfile, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from opdb import NumericTruthStore, TruthStore

RUNS = 15


def build(path, rows):
    TruthStore(path).close()
    con = sqlite3.connect(path)
    con.executemany("INSERT INTO opdb_source_kv VALUES (?,?)",
                    ((f"g{i % 1000}/{i}", ((i * 7919) % 100003 - 50000).to_bytes(8, "big", signed=True))
                     for i in range(rows)))
    con.commit(); con.close()


def ms(x):
    return round(x * 1000, 3)


def timed(fn, runs=RUNS):
    out = []
    for _ in range(runs):
        t = time.perf_counter(); fn(); out.append(time.perf_counter() - t)
    return out


def batches(store, tag):
    out = []
    for r in range(RUNS):
        ops = [("put", f"g{i % 50}/{tag}{r}-{i}", (i - 500).to_bytes(8, "big", signed=True)) for i in range(1000)]
        t = time.perf_counter(); store.apply(ops); out.append(time.perf_counter() - t)
    return out


def main(sizes):
    print(json.dumps({"python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "cpu": open("/proc/cpuinfo").read().split("model name")[1].split(":")[1].split("\n")[0].strip(),
        "cpus": os.cpu_count(), "sha": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()}))
    for rows in sizes:
        with tempfile.TemporaryDirectory() as d:
            p, q = os.path.join(d, "num"), os.path.join(d, "plain")
            build(p, rows); build(q, rows)
            t = time.perf_counter(); s = NumericTruthStore(p); build_s = time.perf_counter() - t
            assert s.open_mode == "REBUILT"
            read_lens = timed(lambda: s.numeric_stats("g7"), RUNS * 20)
            assert s.numeric_stats("g7").served_from == "LENS"
            read_src = timed(lambda: s.numeric_stats_source("g7"))
            nb = batches(s, "n"); s.close()
            t = time.perf_counter(); s = NumericTruthStore(p); open_s = time.perf_counter() - t
            assert s.open_mode == "PERSISTED"; s.close()
            plain = TruthStore(q); pb = batches(plain, "n"); plain.close()
            print(json.dumps({"rows": rows, "first_build_s": round(build_s, 3), "reopen_s": round(open_s, 5),
                "read_lens_ms_median": ms(statistics.median(read_lens)),
                "read_source_ms_median": ms(statistics.median(read_src)),
                "batch1000_numeric_ms_median": ms(statistics.median(nb)),
                "batch1000_plain_source_ms_median": ms(statistics.median(pb)),
                "read_lens_ms_raw": [ms(x) for x in read_lens[:RUNS]], "read_source_ms_raw": [ms(x) for x in read_src],
                "batch1000_numeric_ms_raw": [ms(x) for x in nb], "batch1000_plain_ms_raw": [ms(x) for x in pb],
                "file_bytes_numeric": os.path.getsize(p), "file_bytes_plain": os.path.getsize(q)}))


if __name__ == "__main__":
    main([int(x) for x in sys.argv[1:]] or [10000, 100000, 1000000])
