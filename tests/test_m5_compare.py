"""TASK-015: contenders A (index), B (triggers), C (Lens), D (Source) vs a plain dict model
written here, independent of the harness code."""
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
spec = importlib.util.spec_from_file_location("m5_compare", os.path.join(ROOT, "experiments", "m5_compare.py"))
m5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m5)


def expected(model):
    by = {}
    for k, x in model.items():
        by.setdefault(k.split("/", 1)[0], []).append(x)
    return {g: (len(v), sum(v), min(v), max(v)) for g, v in by.items()}


class CompareTest(unittest.TestCase):
    def check_all(self, cont, model, label):
        want = expected(model)
        groups = [f"grp{i}" for i in range(m5.GROUPS)] + ["grp-missing"]
        for g in groups:
            exp = want.get(g, (0, 0, None, None))
            for name, c in cont.items():
                if name == "D" and not (g in ("grp-missing", "grp7") or int(g[3:]) < 60 if g != "grp-missing" else True):
                    continue   # D is a full scan per call: check it on groups 0-59 and 7
                self.assertEqual(tuple(c.read(g)), exp, f"{label} {name} {g}")

    def test_agree_after_batches(self):
        for seed in (1, 2, 3, 4, 5, 6):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as d:
                rng = random.Random(seed)
                model = {f"grp{i % m5.GROUPS}/{i}": rng.randrange(-2**40, 2**40) for i in range(2000)}
                a = m5.Plain(os.path.join(d, "a"), False)
                b = m5.Plain(os.path.join(d, "b"), True)
                c = m5.Lens(os.path.join(d, "c"))
                dd = m5.Lens.__new__(m5.Lens)
                for x in (a, b, c):
                    x.build(model)
                dd.path, dd.source, dd.store = c.path, True, c.store
                cont = {"A": a, "B": b, "C": c, "D": dd}
                self.check_all(cont, model, "initial")
                # delete the only min and the only max of some groups, and a whole group
                want = expected(model)
                dels = []
                for g in ("grp3", "grp4", "grp5"):
                    ks = [k for k in model if k.split("/")[0] == g]
                    dels += [min(ks, key=model.get), max(ks, key=model.get)]
                dels += [k for k in model if k.split("/")[0] == "grp7"]
                ops = [("delete", k, None) for k in dels]
                puts = [("put", f"grp{i % 50}/new{i}", rng.randrange(-2**40, 2**40)) for i in range(300)]
                over = [("put", k, rng.randrange(-2**40, 2**40)) for k in rng.sample(sorted(model), 300)]
                ext = [("put", f"grp9/ext{j}", v) for j, v in enumerate((2**41, -2**41))]
                for batch in (ops, puts, over, ext, [("delete", k, None) for k in ("grp9/ext0", "grp9/ext1")]):
                    for x in (a, b, c):
                        x.apply(batch)
                    for op, k, v in batch:
                        if op == "put":
                            model[k] = v
                        else:
                            model.pop(k, None)
                    self.check_all(cont, model, "after batch")
                    if batch is ops:
                        self.assertNotIn("grp7", expected(model))
                self.assertEqual(c.store.numeric_stats("grp7").served_from, "LENS")
                for x in (a, b, c):
                    x.close()

    def test_json_output_complete(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "r.json")
            subprocess.run([sys.executable, os.path.join(ROOT, "experiments", "m5_compare.py"),
                            "--sizes", "2000", "--runs", "2", "--seed", "3", "--json", out],
                           check=True, capture_output=True, timeout=300)
            r = json.load(open(out))
            self.assertEqual(r["pragmas"], {"journal_mode": "WAL", "synchronous": "FULL"})
            for key in ("python", "sqlite", "sha", "cpu"):
                self.assertTrue(r["machine"][key])
            s = r["sizes"][0]
            for name in "ABCD":
                self.assertGreater(s["reads_ms"][name], 0)
                self.assertGreater(s["bytes"][name], 0)
                self.assertGreater(s["open_ms"][name], 0)
            for kind in ("insert", "overwrite", "delete"):
                for name in "ABC":
                    self.assertGreater(s["writes_ms"][kind][name], 0)


if __name__ == "__main__":
    unittest.main()
