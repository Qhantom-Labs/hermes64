"""Dump every registered generator's param schema (id, class, defaults, enums, ranges) as JSON.
  blender -b --factory-startup --python tools/schemadump.py -- OUT.json"""
import json
import os
import sys

LANE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LANE)

from core import pipeline  # noqa: E402


def main(argv):
    out = argv[0]
    reg = pipeline.load_generators()
    d = {}
    for gid in sorted(reg):
        spec = reg[gid]
        d[gid] = {"version": spec.version, "class": spec.cls, "description": spec.description,
                  "has_rules": spec.rules is not None, "wall_mounted": spec.wall_mounted, "schema": spec.schema}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, sort_keys=True, default=str)
    print("SCHEMADUMP", out, len(d))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:]))
