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


def peak_rss_kib():
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmHWM:'):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def reset_peak_rss():
    try:
        Path('/proc/self/clear_refs').write_text('5\n')
        return True
    except OSError:
        return False


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
                rss_reset = reset_peak_rss()
                print(f"RUN n={n} value_bytes={size} repeat={repeat} seed={SEED} estimated_peak_bytes={need} free_bytes={free} peak_rss_reset={rss_reset}")
                if free < need:
                    print("RESULT SKIPPED_INSUFFICIENT_DISK"); continue
                with tempfile.TemporaryDirectory(prefix="opdb-sqlite-bench-") as directory:
                    db = Path(directory)/"kv.sqlite3"
                    conn = sqlite3.connect(db)
                    conn.execute("CREATE TABLE kv (k BLOB PRIMARY KEY, v BLOB NOT NULL)")
                    journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
                    synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
                    keys = [key(i) for i in range(n)]; seq = order(n)
                    values = [value(i,size) for i in range(n)]
                    expected = {}
                    peak_rss = peak_rss_kib()
                    print(f"  sqlite_journal_mode={journal} synchronous={synchronous} (0=OFF,1=NORMAL,2=FULL,3=EXTRA); one transaction per phase")
                    started = time.perf_counter()
                    for i in seq:
                        conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)",(keys[i],values[i]))
                    conn.commit()
                    put_ms=(time.perf_counter()-started)*1000
                    expected.update((keys[i],values[i]) for i in seq)
                    peak_rss = max(filter(None, (peak_rss, peak_rss_kib())), default=None)
                    print(f"  put_total_ms={put_ms:.3f} file_bytes={db.stat().st_size}")
                    def verify():
                        for k in keys:
                            row=conn.execute("SELECT v FROM kv WHERE k=?",(k,)).fetchone()
                            if (row[0] if row else None)!=expected.get(k): raise RuntimeError("ORACLE_MISMATCH")
                    verify()
                    started=time.perf_counter()
                    for i in seq:
                        row=conn.execute("SELECT v FROM kv WHERE k=?",(keys[i],)).fetchone()
                        if row is None or row[0] != expected[keys[i]]: raise RuntimeError("ORACLE_MISMATCH_GET")
                    print(f"  get_existing_total_ms={(time.perf_counter()-started)*1000:.3f}")
                    peak_rss = max(filter(None, (peak_rss, peak_rss_kib())), default=None)
                    started=time.perf_counter()
                    for i in range(n,2*n):
                        if conn.execute("SELECT v FROM kv WHERE k=?",(key(i),)).fetchone() is not None:
                            raise RuntimeError("UNEXPECTED_MISSING_KEY")
                    print(f"  get_missing_total_ms={(time.perf_counter()-started)*1000:.3f}")
                    peak_rss = max(filter(None, (peak_rss, peak_rss_kib())), default=None)
                    overwrite_values=[value(i+n,size) for i in range(n)]
                    started=time.perf_counter()
                    for i in seq:
                        conn.execute("INSERT OR REPLACE INTO kv VALUES (?,?)",(keys[i],overwrite_values[i]))
                    conn.commit(); overwrite_ms=(time.perf_counter()-started)*1000
                    expected.update((keys[i],overwrite_values[i]) for i in seq)
                    verify()
                    started=time.perf_counter()
                    for i in seq[::2]:
                        conn.execute("DELETE FROM kv WHERE k=?",(keys[i],))
                    conn.commit(); delete_ms=(time.perf_counter()-started)*1000
                    for i in seq[::2]: expected.pop(keys[i])
                    verify(); conn.close()
                    peak_rss = max(filter(None, (peak_rss, peak_rss_kib())), default=None)
                    size_after=db.stat().st_size
                    conn=sqlite3.connect(db); verify(); conn.close()
                    peak_rss = max(filter(None, (peak_rss, current_rss_kib())), default=None)
                    print(f"  overwrite_total_ms={overwrite_ms:.3f} delete_total_ms={delete_ms:.3f} after_overwrite_delete_file_bytes={size_after} peak_rss_kib={peak_rss}")
                    print("RESULT PASS independent Python dict checked after every phase and reopen; SQLite uses one transaction per write phase, unlike Rust's unsynced per-call put")


if __name__=="__main__": main()
