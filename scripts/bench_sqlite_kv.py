#!/usr/bin/env python3
"""Same deterministic KV operation sequence as rust/opdb-core/examples/bench_v0.rs."""
import os
import argparse
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time

SEED = 2_026_11_23
SIZES = (10_000, 100_000, 1_000_000)
VALUE_SIZES = (16, 256)


def key(i):
    x = i ^ SEED
    x ^= x >> 30; x = (x * 0xbf58476d1ce4e5b9) & ((1 << 64)-1)
    x ^= x >> 27; x = (x * 0x94d049bb133111eb) & ((1 << 64)-1); x ^= x >> 31
    return f"k-{x:016x}-{i:08x}".encode()


def value(i, size):
    return bytes((i * 31 + j * 17 + SEED) & 255 for j in range(size))


def order(n):
    values = list(range(n)); state = SEED
    for i in range(n-1, 0, -1):
        state ^= (state << 13) & ((1 << 64)-1); state ^= state >> 7
        state ^= (state << 17) & ((1 << 64)-1); state &= (1 << 64)-1
        j = state % (i+1); values[i], values[j] = values[j], values[i]
    return values


def estimate(n, size):
    return int(((n*2+n//2)*(13+32+size)+12)*1.5 + .999999)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--sizes",default="10000,100000,1000000")
    parser.add_argument("--value-sizes",default="16,256")
    parser.add_argument("--repeats",type=int,default=3)
    args=parser.parse_args()
    sizes=tuple(int(x) for x in args.sizes.split(","))
    value_sizes=tuple(int(x) for x in args.value_sizes.split(","))
    print(f"python={__import__('sys').version.split()[0]} sqlite={sqlite3.sqlite_version} seed={SEED}")
    for n in sizes:
        for size in value_sizes:
            for repeat in range(1, args.repeats+1):
                need = estimate(n, size)
                free = shutil.disk_usage(tempfile.gettempdir()).free
                print(f"RUN n={n} value_bytes={size} repeat={repeat} seed={SEED} estimated_peak_bytes={need} free_bytes={free}")
                if free < need:
                    print("RESULT SKIPPED_INSUFFICIENT_DISK"); continue
                with tempfile.TemporaryDirectory(prefix="opdb-sqlite-bench-") as directory:
                    db = Path(directory)/"kv.sqlite3"
                    conn = sqlite3.connect(db)
                    conn.execute("CREATE TABLE kv (k BLOB PRIMARY KEY, v BLOB NOT NULL)")
                    keys = [key(i) for i in range(n)]; seq = order(n)
                    expected = {}
                    started = time.perf_counter()
                    for i in seq:
                        k, v = keys[i], value(i,size)
                        conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)",(k,v)); expected[k]=v
                    conn.commit()
                    print(f"  put_total_ms={(time.perf_counter()-started)*1000:.3f} file_bytes={db.stat().st_size}")
                    def verify():
                        for k in keys:
                            row=conn.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone()
                            if (row[0] if row else None)!=expected.get(k): raise RuntimeError("ORACLE_MISMATCH")
                    verify()
                    started=time.perf_counter()
                    for i in seq: conn.execute("SELECT v FROM kv WHERE k=?",(keys[i],)).fetchone()
                    print(f"  get_existing_total_ms={(time.perf_counter()-started)*1000:.3f}")
                    started=time.perf_counter()
                    for i in range(n,2*n): conn.execute("SELECT v FROM kv WHERE k=?",(key(i),)).fetchone()
                    print(f"  get_missing_total_ms={(time.perf_counter()-started)*1000:.3f}")
                    started=time.perf_counter()
                    for i in seq: conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)",(keys[i],value(i,size)))
                    for i in seq[::2]:
                        conn.execute("DELETE FROM kv WHERE k=?",(keys[i],));expected.pop(keys[i])
                    conn.commit(); verify(); conn.close()
                    size_after=db.stat().st_size
                    conn=sqlite3.connect(db); verify(); conn.close()
                    print(f"  after_overwrite_delete_file_bytes={size_after} phase_total_ms={(time.perf_counter()-started)*1000:.3f}")
                    print("RESULT PASS independent Python dict checked after every phase and reopen; SQLite default synchronous/journal settings; SQLite commit sync semantics differ from Rust put")


if __name__=="__main__": main()
