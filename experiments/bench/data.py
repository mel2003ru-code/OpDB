"""Deterministic benchmark rows."""
import hashlib
import random


def make_rows(n, seed, value_bytes=16, numeric=False):
    """Return n (key, value) pairs; key 'grp<i>/<n>' with i = n % 1000, value from a seeded generator.

    numeric=True with value_bytes == 8 gives 8-byte big-endian signed integers within +-2**40, the format of
    the numeric Lens (values near the 64-bit limits would overflow group sums)."""
    rows = []
    for i in range(n):
        key = "grp%d/%d" % (i % 1000, i)
        rng = random.Random(seed * 1000003 + i)
        if numeric and value_bytes == 8:
            value = rng.randint(-2 ** 40, 2 ** 40).to_bytes(8, "big", signed=True)
        else:
            value = rng.randbytes(value_bytes)
        rows.append((key, value))
    return rows


def digest(rows):
    """sha256 hex digest over all keys and values in order."""
    h = hashlib.sha256()
    for key, value in rows:
        k = key.encode("utf-8")
        h.update(len(k).to_bytes(4, "little") + k + len(value).to_bytes(4, "little") + value)
    return h.hexdigest()
