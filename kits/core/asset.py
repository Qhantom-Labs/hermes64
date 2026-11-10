"""Generator output types + registry (theme-agnostic)."""
from . import schema as S

PREFIX = {"solid": "kit_", "shell": "kit_shell_", "card": "kit_card_"}


class Node:
    def __init__(self, name, mesh, kind="solid", origin=(0.0, 0.0, 0.0), parent=None, double_sided=False):
        if kind not in PREFIX:
            raise ValueError("bad node kind %r" % kind)
        self.name = PREFIX[kind] + name
        self.mesh = mesh
        self.kind = kind
        self.origin = tuple(float(c) for c in origin)
        self.parent = parent
        self.double_sided = double_sided


class Asset:
    def __init__(self, nodes, meta=None):
        self.nodes = [n for n in nodes if n is not None and n.mesh is not None and n.mesh.f]
        self.meta = meta or {}
        self.character = None  # set by character generators (rig/skin/anim spec)

    def tri_count(self):
        t = sum(n.mesh.tri_count() for n in self.nodes)
        if self.character:
            t += sum(n.mesh.tri_count() for n in self.character.get("extra_nodes", []))
        return t


class GenSpec:
    def __init__(self, gid, version, cls, props, description, build, rules=None, wall_mounted=False,
                 origin="floor_center", sweep_fixed=None):
        self.id = gid
        self.version = version
        self.cls = cls
        self.schema = S.obj(props)
        self.description = description
        self.build = build
        self.rules = rules
        self.wall_mounted = wall_mounted
        self.origin = origin
        self.sweep_fixed = sweep_fixed or {}

    def defaults(self):
        return S.defaults(self.schema)


REGISTRY = {}


def register(gid, version, cls, props, description, rules=None, wall_mounted=False, origin="floor_center",
             sweep_fixed=None):
    def deco(fn):
        if gid in REGISTRY:
            raise RuntimeError("duplicate generator id %s" % gid)
        REGISTRY[gid] = GenSpec(gid, version, cls, props, description, fn, rules, wall_mounted, origin, sweep_fixed)
        return fn
    return deco
