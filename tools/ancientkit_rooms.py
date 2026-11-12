"""ANCIENTKIT room compiler: assemble plugin rooms / regions from kit pieces BY DATA on the RUIN GRID.

A room plan names kit build keys (kits/library/ancientkit-sockets.json "pieces") and where they snap: cell blocks,
cells, cell edges, cell corners, declared doors, wall sockets or (free pieces only) metres. compile_room() turns it
into the two things the plugin's normal path consumes: a spec room (grid_size, doors, props, cameras) and its
presentation row (pieces with positions / yaw / kind, look profile, kit_shell). Every placement is checked against the
socket manifest before anything is written:

- every declared door sits on a door socket of a placed piece (same wall line, same point, facing the plot) and every
  door socket of a placed piece carries a declared door (no uncut frames, no holes without frames);
- edge pieces (walls, ramparts, cliffs) chain: two pieces on the same wall line must meet socket to socket or leave
  a whole number of cells between them;
- grid pieces snap to the grid (block / cell / edge / corner) and turn in 90-degree steps, never by free metres;
- wall mounts (banners, vines) hang on a wall socket of a placed wall facing the plot;
- each region declares exactly one landmark piece (kind "landmark", read by the style gate's landmark audit);
- the triangle estimate (manifest tris + door frames + sky set + people) stays inside the 6,000-triangle room cap.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.ancientkit_rooms check PLAN.json   # compile one plan, print the report
"""
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SOCKETS = R / "kits" / "library" / "ancientkit-sockets.json"
CELL, APRON, WALL_T = 4.0, 0.5, 0.5
WALL = {"n": "north", "s": "south", "e": "east", "w": "west"}
DOOR_YAW = {"north": 0.0, "south": 180.0, "west": 90.0, "east": -90.0}     # room.gd arch.door yaw
EDGE_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                    # cell_edge piece standing on a side, front inward
FACE_IN_YAW = EDGE_YAW
CORNER_YAW = {"ne": 0.0, "nw": 90.0, "sw": 180.0, "se": -90.0}
DOOR_FRAME = "ruin.gate"          # bound to arch.door: room.gd places it on every data door
SKY_SET = "land.sky__mesas"       # bound to sky.backdrop (tri estimate only)
TRI_CAP = 6000
PERSON_TRIS = 760                 # measured runtime person (protagonist 732-760 tris); + floor collision
COLLISION_TRIS = 12
CELL_ANCHORS = ("cell_block_centre", "cell_centre", "cell_edge")
GRID_ANCHORS = CELL_ANCHORS + ("corner", "door_anchor", "wall_face")
STRUCT_KIND = {"cell_block_centre": "floor", "cell_centre": "floor", "cell_edge": "wall", "corner": "wall"}
TOL = 0.011
_MAN = {}


class PlanError(ValueError):
    pass


def manifest():
    if not _MAN:
        _MAN.update(json.loads(SOCKETS.read_text(encoding="utf-8")))
    return _MAN


def piece_info(key):
    pieces = manifest()["pieces"]
    if key not in pieces:
        raise PlanError("not an ANCIENTKIT kit piece: %r (kit-only rooms; see ancientkit-sockets.json)" % key)
    return pieces[key]


def rot(x, z, yaw):
    a = math.radians(yaw)
    c, s = math.cos(a), math.sin(a)
    return (x * c + z * s, -x * s + z * c)


VEC = {"n": (0.0, -1.0), "s": (0.0, 1.0), "e": (1.0, 0.0), "w": (-1.0, 0.0)}
OPPOSITE = {"n": "s", "s": "n", "e": "w", "w": "e", "up": "down", "down": "up"}


def rot_facing(f, yaw):
    if f not in VEC:
        return f
    x, z = rot(VEC[f][0], VEC[f][1], yaw)
    return min(VEC, key=lambda k: (VEC[k][0] - x) ** 2 + (VEC[k][1] - z) ** 2)


def snap(v):
    return round(v + 0.0, 3)


class Room:
    def __init__(self, plan):
        self.plan = plan
        cx, cy = plan["plot_cells"]
        self.cells = (cx, cy)
        self.w, self.d = CELL * cx + 2 * APRON, CELL * cy + 2 * APRON
        self.pieces, self.sockets = [], []
        self.tris = 0
        self.edges = {}          # wall line key -> list of (lo, hi) spans along the line

    def cell_centre(self, x, y):
        return (APRON + CELL * (x + 0.5), APRON + CELL * (y + 0.5))

    def block_centre(self, x, y, sx, sy):
        return (APRON + CELL * (x + sx / 2.0), APRON + CELL * (y + sy / 2.0))

    def edge_point(self, x, y, side):
        cxm, czm = self.cell_centre(x, y)
        return {"n": (cxm, czm - CELL / 2), "s": (cxm, czm + CELL / 2), "e": (cxm + CELL / 2, czm), "w": (cxm - CELL / 2, czm)}[side]

    def add(self, key, x, z, yaw=0.0, y=0.0, kind=None, mounted=False, extra=None):
        info = piece_info(key)
        row = {"asset": key, "position": [snap(x), snap(y), snap(z)], "scale": [1, 1, 1], "yaw": float(yaw)}
        if kind:
            row["kind"] = kind
        if mounted:
            row["mounted"] = True
        if extra:
            row.update(extra)
        self.pieces.append(row)
        self.tris += int(info["tris"] or 0)
        for s in info["sockets"]:
            px, py, pz = s["position"]
            rx, rz = rot(px, pz, yaw)
            self.sockets.append(dict(s, at=(x + rx, y + py, z + rz), facing_w=rot_facing(s["facing"], yaw), piece=key,
                                     index=len(self.pieces) - 1))
        return row

    def place(self, spec):
        key = spec["key"]
        info = piece_info(key)
        anchor = info["anchor"] or "free"
        yaw = float(spec.get("yaw", 0.0))
        if yaw % 90 and anchor in GRID_ANCHORS:
            raise PlanError("non-interlocking: grid piece %s at yaw %s (grid pieces turn in 90-degree steps)" % (key, yaw))
        kind = spec.get("kind")
        if "block" in spec:
            if anchor != "cell_block_centre":
                raise PlanError("%s is not a cell-block piece (anchor %s)" % (key, anchor))
            sx, sy = info["cells"]
            if int(yaw) % 180:
                sx, sy = sy, sx
            x, z = self.block_centre(spec["block"][0], spec["block"][1], sx, sy)
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind or STRUCT_KIND[anchor])
        if "cell" in spec:
            if anchor not in ("cell_centre", "cell_block_centre"):
                raise PlanError("%s cannot snap to a cell (anchor %s)" % (key, anchor))
            x, z = self.cell_centre(*spec["cell"])
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind or STRUCT_KIND[anchor])
        if "edge" in spec:
            if anchor != "cell_edge":
                raise PlanError("%s is not a cell-edge piece (anchor %s)" % (key, anchor))
            cx, cy, side = spec["edge"]
            x, z = self.edge_point(cx, cy, side)
            if spec.get("offset_half"):
                # half pieces (2 m) sit on the half-cell lattice along the edge
                dx, dz = rot(float(spec["offset_half"]) * CELL / 4, 0.0, EDGE_YAW[side])
                x, z = x + dx, z + dz
            return self.add(key, x, z, EDGE_YAW[side] + yaw, y=float(spec.get("y", 0.0)), kind=kind or "wall")
        if "corner" in spec:
            if anchor not in ("corner", "cell_edge"):
                raise PlanError("%s is not a corner piece (anchor %s)" % (key, anchor))
            cx, cy, c = spec["corner"]
            ccx, ccz = self.cell_centre(cx, cy)
            x = ccx + (CELL / 2 if "e" in c else -CELL / 2)
            z = ccz + (-CELL / 2 if "n" in c else CELL / 2)
            return self.add(key, x, z, CORNER_YAW[c] + yaw, y=float(spec.get("y", 0.0)), kind=kind or "wall")
        if "at_m" in spec:
            if anchor in GRID_ANCHORS:
                raise PlanError("non-interlocking: %s is a grid piece (anchor %s) and must snap to a cell/block/edge/corner, "
                                "not free metres" % (key, anchor))
            x, z = spec["at_m"]
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind, mounted=bool(spec.get("mounted", False)))
        raise PlanError("%s: no placement (block / cell / edge / corner / at_m)" % key)

    def find(self, kind, x, z, tol=TOL):
        return [s for s in self.sockets if s["type"] == kind and abs(s["at"][0] - x) < tol and abs(s["at"][2] - z) < tol]

    def door_face_point(self, wall, position):
        p = position + 0.5
        return {"north": (p, APRON + WALL_T), "south": (p, self.d - APRON - WALL_T), "west": (APRON + WALL_T, p),
                "east": (self.w - APRON - WALL_T, p)}[wall]


def check_edge_chains(rm):
    """Edge sockets of pieces on the same line meet socket to socket (or keep a whole number of cells apart)."""
    ends = [s for s in rm.sockets if s["type"] in ("edge", "ground_edge")]
    for s in ends:
        mates = [t for t in ends if t is not s and t["type"] == s["type"] and abs(t["at"][0] - s["at"][0]) < TOL
                 and abs(t["at"][2] - s["at"][2]) < TOL]
        for t in mates:
            # straight joints face each other, corner joints are perpendicular (a pier covers them); two ends facing
            # the same way from one point mean the pieces overlap along the line
            if t["facing_w"] == s["facing_w"]:
                raise PlanError("non-interlocking: %s and %s overlap at (%.2f, %.2f) instead of meeting end to end" % (
                    s["piece"], t["piece"], s["at"][0], s["at"][2]))
        # an end that meets nothing must lie on the cell lattice (an open ruin end), never mid-cell
        for v in (s["at"][0] - APRON, s["at"][2] - APRON):
            if abs(v / (CELL / 2) - round(v / (CELL / 2))) * (CELL / 2) > TOL:
                raise PlanError("non-interlocking: edge socket of %s at (%.2f, %.2f) is off the half-cell lattice" % (
                    s["piece"], s["at"][0], s["at"][2]))


def compile_room(plan):
    """plan -> (spec room, presentation row, report). Raises PlanError on any broken connector rule."""
    rm = Room(plan)
    landmark = 0
    for spec in plan.get("pieces", []):
        row = rm.place(spec)
        landmark += row.get("kind") == "landmark"
    if landmark != 1:
        raise PlanError("%s declares %d landmark pieces (exactly one: kind 'landmark')" % (plan["id"], landmark))
    check_edge_chains(rm)
    doors, props = [], []
    used = set()
    for dr in plan.get("doors", []):
        side, cell = dr["side"], int(dr["cell"])
        wall = WALL[side]
        position = int(CELL * cell + 2)
        fx, fz = rm.door_face_point(wall, position)
        hit = [s for s in rm.find("door", fx, fz) if s["facing_w"] == OPPOSITE[side]]
        if not hit:
            raise PlanError("non-interlocking: door %s (%s cell %d) has no door socket facing the plot at (%.2f, %.2f); the "
                            "wall there is uncut" % (dr["id"], wall, cell, fx, fz))
        for s in hit:
            used.add(id(s))
        # the same cut seen from the outer face
        ox = fx + (VEC[side][0] * 2 * WALL_T)
        oz = fz + (VEC[side][1] * 2 * WALL_T)
        for s in rm.find("door", ox, oz):
            used.add(id(s))
        doors.append({"id": dr["id"], "wall": wall, "position": position, "to_room": dr["to_room"], "to_door": dr["to_door"],
                      "label": dr["label"], "conditions": dr.get("conditions", [])})
        rm.tris += int(piece_info(DOOR_FRAME)["tris"] or 0)
        if dr.get("insert"):
            # a door-anchor piece around / in the standard frame (monumental pylon, sealed slab state)
            ins = dr["insert"]
            if piece_info(ins)["anchor"] != "door_anchor":
                raise PlanError("door insert %s is not a door-anchor piece" % ins)
            ax = position + 0.5 if wall in ("north", "south") else (0.4 if wall == "west" else rm.w - 0.4)
            az = position + 0.5 if wall in ("east", "west") else (0.4 if wall == "north" else rm.d - 0.4)
            row = rm.add(ins, ax, az, DOOR_YAW[wall], kind="wall")
            row["note"] = "door insert on %s" % dr["id"]
            for s in rm.sockets:
                if s["piece"] == ins and s["index"] == len(rm.pieces) - 1 and s["type"] == "door":
                    used.add(id(s))
    for s in rm.sockets:
        if s["type"] == "door" and id(s) not in used and not s.get("fits"):
            raise PlanError("non-interlocking: %s has a cut door socket at (%.2f, %.2f) with no door declared there" % (
                s["piece"], s["at"][0], s["at"][2]))
    for m in plan.get("wall", []):
        cx, cy, side = m["edge"]
        x, z = rm.edge_point(cx, cy, side)
        fx, fz = x - VEC[side][0] * WALL_T, z - VEC[side][1] * WALL_T
        hit = [s for s in rm.find("wall", fx, fz) if s["facing_w"] == OPPOSITE[side]]
        if not hit:
            raise PlanError("wall mount %s: no wall socket facing the plot on edge %s" % (m["key"], m["edge"]))
        if piece_info(m["key"])["anchor"] != "wall_face":
            raise PlanError("wall mount %s is not a wall-face piece" % m["key"])
        rm.add(m["key"], fx, fz, FACE_IN_YAW[side], mounted=True, kind="dressing", extra={"wall_ok": True})
    for p in plan.get("props", []):
        info = piece_info(p["asset"])
        if info["anchor"] in CELL_ANCHORS:
            raise PlanError("prop %s: grid pieces are not free props" % p["id"])
        props.append({"id": p["id"], "asset": p["asset"], "position": [snap(p["at_m"][0]), float(p.get("y", 0.0)), snap(p["at_m"][1])],
                      "rotation": [0, float(p.get("yaw", 0.0)), 0]})
        rm.tris += int(info["tris"] or 0)
    sky = int(piece_info(plan.get("sky_set", SKY_SET))["tris"] or 0)
    people = 1 + len(plan.get("characters", {}))
    est = rm.tris + sky + PERSON_TRIS * people + COLLISION_TRIS
    if est > TRI_CAP:
        raise PlanError("over budget: %s estimates %d triangles (kit %d + sky %d + %d people x %d) > %d" % (
            plan["id"], est, rm.tris, sky, people, PERSON_TRIS, TRI_CAP))
    cam = plan["camera"]
    room = {"id": plan["id"], "name": plan["name"], "description": plan["description"], "grid_size": [int(rm.w), int(rm.d)],
            "kit_refs": [], "doors": doors, "cameras": [{"id": "game", "position": cam["position"], "look_at": cam["look_at"]}],
            "props": props, "character_ids": [plan.get("protagonist", "wayfarer")] + sorted(plan.get("characters", {}))}
    pres = {"exterior": bool(plan.get("exterior", False)), "kit_shell": True, "floor": "",
            "look_profile": plan.get("look_profile", "approach"), "wall_height": plan.get("wall_height", 4.5),
            "camera": "game", "cameras": [dict(cam, id="game")], "pieces": rm.pieces}
    if plan.get("characters"):
        pres["characters"] = plan["characters"]
    if plan.get("interactions"):
        pres["interactions"] = plan["interactions"]
    report = {"id": plan["id"], "plot_m": [rm.w, rm.d], "pieces": len(rm.pieces), "kit_tris": rm.tris, "sky_tris": sky, "people": people,
              "tri_estimate": est, "tri_cap": TRI_CAP,
              "sockets": {k: sum(1 for s in rm.sockets if s["type"] == k) for k in sorted({s["type"] for s in rm.sockets})},
              "checks": ["doors on door sockets", "every door socket used", "edge pieces chained on the half-cell lattice",
                         "grid pieces snapped (90-degree turns)", "wall mounts on wall sockets", "one landmark", "tri estimate <= cap"]}
    return room, pres, report


def main(argv):
    if len(argv) != 2 or argv[0] != "check":
        print(__doc__)
        return 2
    try:
        room, pres, rep = compile_room(json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    except PlanError as e:
        print("REJECTED:", e)
        return 1
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
