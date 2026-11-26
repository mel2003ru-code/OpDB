"""Benchmark CLI. Measures; it makes no speed claim."""
import argparse
import json
import os
import random
import sys
import tempfile
import time

from experiments.bench import data, timing
from experiments.bench.sqlite_contender import SqliteContender

POINT_READS = 200


def _verify(contender, rows, seed):
    keys = list(range(len(rows))) if len(rows) <= 2000 else random.Random(seed).sample(range(len(rows)), 1000)
    for i in keys:
        if contender.get(rows[i][0]) != rows[i][1]:
            raise SystemExit("verification failed for key %s" % rows[i][0])
    if contender.count() != len(rows):
        raise SystemExit("row count mismatch")


def _one_run(rows, seed, synchronous):
    with tempfile.TemporaryDirectory() as tmp:
        contender = SqliteContender(os.path.join(tmp, "bench.db"), synchronous=synchronous)
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
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    sync = args.synchronous.upper()
    if sync not in ("OFF", "NORMAL", "FULL", "EXTRA"):
        raise SystemExit("invalid --synchronous")
    report = {
        "schema": 1,
        "command": list(sys.argv) if argv is None else ["run"] + list(argv),
        "seed": args.seed,
        "synchronous": sync,
        "machine": timing.machine_info(),
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_digest": {},
        "results": [],
    }
    for size in [int(s) for s in args.sizes.split(",") if s]:
        rows = data.make_rows(size, args.seed, args.value_bytes)
        report["data_digest"][str(size)] = data.digest(rows)
        inserts, reads = [], []
        for _ in range(args.runs):
            insert, read = _one_run(rows, args.seed, sync)
            inserts.append(insert)
            reads.append(read)
        for workload, samples in (("bulk_insert", inserts), ("point_read", reads)):
            row = {"contender": "sqlite", "size": size, "workload": workload, "verified": True}
            row.update(timing.summarize(samples))
            report["results"].append(row)
            print("%-8s %8d %-12s median %9.2f ms  min %9.2f  max %9.2f" % (
                row["contender"], size, workload, row["median_ms"], row["min_ms"], row["max_ms"]))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
