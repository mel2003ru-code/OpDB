"""Timing helpers: wall-clock milliseconds."""
import os
import platform
import sqlite3
import statistics
import sys
import time


def measure(fn, runs, timer=time.perf_counter_ns):
    """Call fn() `runs` times; return the durations in milliseconds."""
    samples = []
    for _ in range(runs):
        start = timer()
        fn()
        samples.append((timer() - start) / 1e6)
    return samples


def summarize(samples):
    return {
        "runs": list(samples),
        "median_ms": statistics.median(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
    }


def machine_info():
    return {
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
    }
