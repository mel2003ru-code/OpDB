"""TASK-013: batched statements in PersistentTruthStore.apply.
Oracles: Source recomputation (group_stats_source) and a plain Python dict."""
import os
import random
import sqlite3
import tempfile
import unittest

from opdb import PersistentTruthStore

GROUPS = ["a", "b", "é", "日本", "", "g/x"] + [f"grp{i}" for i in range(400)]


def model_stats(model):
    out = {}
    for k, v in model.items():
        g = k.split("/", 1)[0]
        n, b = out.get(g, (0, 0))
        out[g] = (n + 1, b + len(v))
    return out


class WriteBatching(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def check(self, store, model):
        exp = model_stats(model)
        for g in set(exp) | {"a", "b", "é", "zzz", "grp1", "grp399"}:
            ref = store.group_stats_source(g)
            got = store.group_stats(g)
            self.assertEqual(got.served_from, "LENS", g)
            self.assertEqual((got.row_count, got.value_bytes),
                             (ref.row_count, ref.value_bytes), g)
            self.assertEqual((got.row_count, got.value_bytes), exp.get(g, (0, 0)), g)
        lens = {g: (n, b) for g, n, b in store._db.execute(
            "SELECT g,n,b FROM opdb_lens_group")}
        self.assertEqual(lens, exp)           # no stray or zero-count rows
        src = dict(store._db.execute("SELECT k,v FROM opdb_source_kv"))
        self.assertEqual(src, model)

    def test_30_seeds_with_big_batches_and_reopen(self):
        for seed in range(30):
            path = os.path.join(self.tmp.name, f"s{seed}.db")
            rnd, model = random.Random(seed), {}
            store = PersistentTruthStore(path)
            for step in range(8):
                ops = []
                n_ops = rnd.choice([1, 5, 40, 299, 300, 301, 650, 1000])
                for _ in range(n_ops):
                    key = rnd.choice(GROUPS) + rnd.choice(["/1", "/2", "/3/4", "/k%d" % rnd.randint(0, 60)])
                    if key.startswith("/"):
                        key = "k" + key
                    r = rnd.random()
                    if r < 0.3:                       # delete (often absent)
                        ops.append(("delete", key)); model.pop(key, None)
                    else:                             # put / overwrite / reinsert
                        val = bytes(rnd.randint(0, 9) for _ in range(rnd.choice([0, 0, 1, 7, 50])))
                        ops.append(("put", key, val)); model[key] = val
                        if r > 0.9:                   # same key twice in a batch
                            ops.append(("put", key, val + b"!")); model[key] = val + b"!"
                        elif r > 0.8:                 # delete then put again
                            ops.append(("delete", key)); ops.append(("put", key, b"re")); model[key] = b"re"
                store.apply(ops)
                self.check(store, model)
                if step % 3 == 2:
                    store.close()
                    store = PersistentTruthStore(path)
                    self.assertEqual(store.open_mode, "PERSISTED", seed)
                    self.check(store, model)
            store.close()

    def test_delete_whole_group_removes_lens_row(self):
        with PersistentTruthStore(os.path.join(self.tmp.name, "d.db")) as s:
            s.apply([("put", f"a/{i}", b"x") for i in range(700)])
            s.apply([("delete", f"a/{i}") for i in range(700)])
            self.check(s, {})

    def test_error_in_later_chunk_rolls_back_everything(self):
        class Boom:
            def __init__(self, db, nth):
                self.db, self.nth, self.seen = db, nth, 0

            def execute(self, sql, *a):
                if "INSERT INTO opdb_source_kv" in sql:
                    self.seen += 1
                    if self.seen == self.nth:
                        raise sqlite3.OperationalError("injected")
                return self.db.execute(sql, *a)

            def __getattr__(self, name):
                return getattr(self.db, name)

        path = os.path.join(self.tmp.name, "r.db")
        s = PersistentTruthStore(path)
        base = {f"a/{i}": b"1" for i in range(10)}
        s.apply([("put", k, v) for k, v in base.items()])
        ops = [("put", f"b/{i}", b"22") for i in range(700)] + [("delete", "a/1")]
        real = s._db
        s._db = Boom(real, 3)             # third chunk of the 700-row put run
        with self.assertRaises(sqlite3.OperationalError):
            s.apply(ops)
        s._db = real
        self.check(s, base)               # Source and Lens both unchanged
        s.apply(ops)
        model = dict(base); model.pop("a/1")
        model.update({f"b/{i}": b"22" for i in range(700)})
        self.check(s, model)
        s.close()
        with PersistentTruthStore(path) as r:
            self.assertEqual(r.open_mode, "PERSISTED")
            self.check(r, model)

    def test_second_store_and_outside_write(self):
        path = os.path.join(self.tmp.name, "o.db")
        a = PersistentTruthStore(path)
        a.apply([("put", "a/1", b"x")])
        b = PersistentTruthStore(path)
        b.apply([("put", "a/2", b"yy"), ("put", "c/1", b"")])
        self.assertEqual(a.group_stats("a").row_count, 2)   # a notices b's commit
        con = sqlite3.connect(path)
        con.execute("INSERT INTO opdb_source_kv VALUES ('a/3', x'010203')")
        con.commit(); con.close()
        a.apply([("put", "a/4", b"z")])                      # foreign write -> rebuilt
        self.check(a, {"a/1": b"x", "a/2": b"yy", "c/1": b"", "a/3": b"\x01\x02\x03", "a/4": b"z"})
        a.close(); b.close()


if __name__ == "__main__":
    unittest.main()
