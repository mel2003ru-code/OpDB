"""TASK-016: median and p95 per contender/workload from m5_compare.py raw JSON files.
Usage: python experiments/m16_summarize.py run1.json run2.json"""
import json, sys


def p95(xs):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(0.95 * (len(xs) - 1))))]


def med(xs):
    xs = sorted(xs); n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


print("| run | rows | workload | A med/p95 | B med/p95 | C med/p95 | batches |")
print("| --- | --- | --- | --- | --- | --- | --- |")
for i, path in enumerate(sys.argv[1:], 1):
    for s in json.load(open(path))["sizes"]:
        for kind in ("insert", "overwrite", "delete"):
            raw = s["raw"][f"write_{kind}"]
            cells = " | ".join(f"{med(raw[c]):.1f} / {p95(raw[c]):.1f}" for c in "ABC")
            print(f"| {i} | {s['rows']} | {kind} | {cells} | {len(raw['A'])} |")
