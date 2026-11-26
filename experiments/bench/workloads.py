"""Read workloads and their plain-Python model answers."""
import random

GROUPS = 1000
THRESHOLD = 128


def pick_groups(seed, count=50):
    """`count` distinct group numbers in 0..999, deterministic for a seed."""
    return random.Random(seed * 7919 + 13).sample(range(GROUPS), count)


def _group_rows(rows, group):
    prefix = "grp%d/" % group
    return [v for k, v in rows if k.startswith(prefix)]


def expected_range_count(rows, group):
    return len(_group_rows(rows, group))


def expected_filter_count(rows, group, threshold=THRESHOLD):
    return sum(1 for v in _group_rows(rows, group) if v and v[0] < threshold)
