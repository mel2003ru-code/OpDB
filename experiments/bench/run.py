"""Benchmark CLI. Measures; it makes no speed claim."""
import argparse
import json
import os
import random
import sys
import tempfile
import time

from experiments.bench import data, timing
from experiments.bench.opdb_contenders import OpdbNumericContender, OpdbSourceContender
from experiments.bench.sqlite_contender import SqliteContender

POINT_READS = 200
REGISTRY = {
    "sqlite": SqliteContender,
    "opdb_source": OpdbSourceContender,
    "opdb_numeric_lens": OpdbNumericContender,
}


def _make(cls, path, synchronous):
    return cls(path, synchronous=synchronous) if cls is SqliteContender else cls(path)


def _verify(contender, rows, seed):
    keys = list(range(len(rows))) if len(rows) <= 2000 else random.Random(seed).sample(range(len(rows)), 1000)
    for i in keys:
        if contender.get(rows[i][0]) != rows[i][1]:
            raise SystemExit("%s: verification failed for key %s" % (contender.name, rows[i][0]))
    if contender.count() != len(rows):
        raise SystemExit("%s: row count mismatch" % contender.name)


def _one_run(cls, rows, seed, synchronous):
    with tempfile.TemporaryDirectory() as tmp:
        contender = _make(cls, os.path.join(tmp, "bench.db"), synchronous)
        try:
            insert = timing.measure(lambda: contender.bulk_insert(rows), 1)[0]
            _verify(contender, rows, seed)
            picks = random.Random(seed + 1).choices(range(len(rows)), k=POINT_READS)
            read = timing.measure(lambda: [contender.get(rows[i][0]) for i in picks], 1)[0]
        finally:
            contender.close()
    return insert, read


def main(argv=None):
    ap = argparse.ArgumentParser(prog="experiments.bench.run")
    ap.add_argument("--sizes", default="1000")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--value-bytes", type=int, default=16)
    ap.add_argument("--synchronous", default="FULL")
    ap.add_argument("--contenders", default="sqlite", help="comma list or 'all' (default: sqlite)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    sync = args.synchronous.upper()
    if sync not in ("OFF", "NORMAL", "FULL", "EXTRA"):
        raise SystemExit("invalid --synchronous")
    names = list(REGISTRY) if args.contenders == "all" else [n for n in args.contenders.split(",") if n]
    for n in names:
        if n not in REGISTRY:
            raise SystemExit("unknown contender %s" % n)
    numeric = "opdb_numeric_lens" in names and args.value_bytes == 8
    report = {
        "schema": 1,
        "command": list(sys.argv) if argv is None else ["run"] + list(argv),
        "seed": args.seed,
        "synchronous": sync,
        "value_bytes": args.value_bytes,
        "numeric_values": numeric,
        "machine": timing.machine_info(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_digest": {},
        "results": [],
    }
    for size in [int(s) for s in args.sizes.split(",") if s]:
        rows = data.make_rows(size, args.seed, args.value_bytes, numeric=numeric)
        report["data_digest"][str(size)] = data.digest(rows)
        for name in names:
            cls = REGISTRY[name]
            applicable = getattr(cls, "applicable", lambda value_bytes: True)
            if not applicable(args.value_bytes):
                report["results"].append({"contender": name, "size": size, "status": "NOT_APPLICABLE",
                                          "reason": "needs %d-byte values, got %d" % (8, args.value_bytes)})
                print("%-18s %8d NOT_APPLICABLE" % (name, size))
                continue
            inserts, reads = [], []
            for _ in range(args.runs):
                insert, read = _one_run(cls, rows, args.seed, sync)
                inserts.append(insert)
                reads.append(read)
            for workload, samples in (("bulk_insert", inserts), ("point_read", reads)):
                row = {"contender": name, "size": size, "workload": workload, "verified": True}
                row.update(timing.summarize(samples))
                report["results"].append(row)
                print("%-18s %8d %-12s median %9.2f ms  min %9.2f  max %9.2f" % (
                    name, size, workload, row["median_ms"], row["min_ms"], row["max_ms"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
