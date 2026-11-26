"""Deterministic benchmark rows."""
import hashlib
import random


def make_rows(n, seed, value_bytes=16):
    """Return n (key, value) pairs; key 'grp<i>/<n>' with i = n % 1000, value from a seeded generator."""
    rows = []
    for i in range(n):
        key = "grp%d/%d" % (i % 1000, i)
        value = random.Random(seed * 1000003 + i).randbytes(value_bytes)
        rows.append((key, value))
    return rows


def digest(rows):
    """sha256 hex digest over all keys and values in order."""
    h = hashlib.sha256()
    for key, value in rows:
        k = key.encode("utf-8")
        h.update(len(k).to_bytes(4, "little") + k + len(value).to_bytes(4, "little") + value)
    return h.hexdigest()
