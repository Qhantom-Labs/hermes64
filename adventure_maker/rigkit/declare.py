"""Clip-form declarations a converter or builder writes into a character GLB (rig contract amendment, lane CHARBIND).

declare_seat(glb, clips, height_m) -> bytes
    Marks seated clips: animation extras hermes64_seat {height_m: seat top above the character origin's floor}. The rig
    kit validator then holds those clips to the seated rule (one fixed horizontal root placement, never below the
    floor) instead of the standing floor / root-motion rules. Only the JSON chunk changes; the binary is copied.

A run flight phase is declared by the base_v1 locomotion bake itself (root extras hermes64_locomotion run.flight_keys,
run clip extras hermes64_locomotion = base id); there is no separate call for it.
"""
import copy
from pathlib import Path

from . import gltf
from .validate import SEAT_KEY, SEAT_HEIGHT_M


def declare_seat(glb, clips, height_m):
    raw = bytes(glb) if isinstance(glb, (bytes, bytearray, memoryview)) else Path(glb).read_bytes()
    h = float(height_m)
    if not SEAT_HEIGHT_M[0] <= h <= SEAT_HEIGHT_M[1]:
        raise ValueError('seat height %.3f m is outside %s m' % (h, list(SEAT_HEIGHT_M)))
    doc, binary = gltf.parse(raw)
    names = [a.get('name') for a in doc.get('animations', [])]
    missing = [c for c in clips if c not in names]
    if missing or not clips:
        raise ValueError('no clip named %s in this file (it has %s)' % (', '.join(missing) or '(none given)', names))
    doc = copy.deepcopy(doc)
    for a in doc['animations']:
        if a.get('name') in clips:
            a['extras'] = dict(a.get('extras') or {}, **{SEAT_KEY: {'height_m': round(h, 4)}})
    return gltf.encode(doc, binary)
