"""Deterministic seeded randomness. Never uses hash() (salted per process)."""
import hashlib
import random


def sub_seed(*parts):
    h = hashlib.sha256("\x1f".join(repr(p) for p in parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "little")


def rng(*parts):
    """random.Random seeded from any tuple of tags, e.g. rng(seed, 'tree', 'branches')."""
    return random.Random(sub_seed(*parts))
