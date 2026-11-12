"""SCIFIKIT room / region compiler: assemble plugin rooms from kit pieces BY DATA on the STATION GRID (4 m cells) and the
TERRAIN GRID (8 m tiles).

A room plan names kit build keys (kits/library/scifikit-sockets.json "pieces") and where they snap: cell blocks, cells,
cell edges, terrain tiles, declared doors, wall sockets or (free props only) metres. compile_room() turns it into the
two things the plugin's normal path consumes: a spec room (grid_size, doors, props, cameras) and its presentation row
(pieces with positions/yaw/kind, look profile, kit_shell). Every placement is checked against the socket manifest
(connector rules) before anything is written:

- every declared door sits on a door socket of a placed piece (door anchor: 0.4 m in from the plot edge, cell
  midline) and every door socket of a structure piece carries a declared door (no uncut frames, no holes without
  frames); exteriors may open a door on any door-anchor piece standing there (an outpost airlock);
- corridor sockets pair with an opposite corridor socket on the same cell edge (exteriors may declare corridor
  "mouths" that open onto terrain);
- window sockets carry the stn.viewport of the same kind (mounted automatically);
- wall mounts go on named wall sockets, back on the inner wall face;
- terrain tiles snap to the 8 m tile grid and neighbouring tiles share edges of the same type and level (ramps the
  same from/to, trails on both sides);
- grid pieces (cell / block / edge / tile anchors) can only be placed on the grid, never by free metres, and turn in
  90-degree steps;
- the triangle estimate (manifest tris + door frames + backdrop + people) stays inside the 6,000-triangle room cap.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.scifikit_rooms check PLAN.json   # compile one plan, print the report
"""
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SOCKETS = R / "kits" / "library" / "scifikit-sockets.json"
CELL, APRON, WALL_T, TILE = 4.0, 0.5, 0.5, 8.0
WALL = {"n": "north", "s": "south", "e": "east", "w": "west"}
DOOR_YAW = {"north": 0.0, "south": 180.0, "west": 90.0, "east": -90.0}     # room.gd arch.door yaw
FACE_IN_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                  # wall-face prop on a <side> wall, facing in
EDGE_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                    # cell_edge piece standing on a side
DOOR_FRAME = "stn.doorway"
BACKDROP = "skyx.starfield"
TRI_CAP = 6000
PERSON_TRIS = 760          # measured runtime person (protagonist 732-760 tris, actors 650-756); + floor collision
COLLISION_TRIS = 12
GRID_ANCHORS = ("cell_block_centre", "cell_centre", "cell_edge", "terrain_tile")
VIEWPORT_FOR = {"band": "stn.viewport", "port": "stn.viewport__port", "tall": "stn.viewport__tall"}
TOL = 0.011


class PlanError(ValueError):
    pass


_MAN = {}


def manifest():
    if not _MAN:
        _MAN.update(json.loads(SOCKETS.read_text(encoding="utf-8")))
    return _MAN


def piece_info(key):
    pieces = manifest()["pieces"]
    if key not in pieces:
        raise PlanError("not a SCIFIKIT kit piece: %r (kit-only rooms; see scifikit-sockets.json)" % key)
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


def edge_sig(e):
    """Comparable signature of a terrain edge (type, levels, trail)."""
    if e["type"] == "ground":
        return ("ground", round(float(e["level"]), 3), bool(e.get("trail")))
    return (e["type"], round(float(e["from"]), 3), round(float(e["to"]), 3), bool(e.get("trail")))


class Room:
    def __init__(self, plan):
        self.plan = plan
        cx, cy = plan["plot_cells"]
        self.cells = (cx, cy)
        self.w, self.d = CELL * cx + 2 * APRON, CELL * cy + 2 * APRON
        self.pieces, self.sockets, self.tiles = [], [], {}
        self.tris = 0

    # ------------------------------------------------------------ grid helpers (plot metres, Godot x east / z south)
    def cell_centre(self, x, y):
        return (APRON + CELL * (x + 0.5), APRON + CELL * (y + 0.5))

    def block_centre(self, x, y, sx, sy):
        return (APRON + CELL * (x + sx / 2.0), APRON + CELL * (y + sy / 2.0))

    def tile_centre(self, i, j):
        return (APRON + TILE * (i + 0.5), APRON + TILE * (j + 0.5))

    def edge_point(self, x, y, side):
        cxm, czm = self.cell_centre(x, y)
        return {"n": (cxm, czm - CELL / 2), "s": (cxm, czm + CELL / 2), "e": (cxm + CELL / 2, czm), "w": (cxm - CELL / 2, czm)}[side]

    def door_anchor(self, wall, position):
        p = position + APRON
        return {"north": (p, 0.4), "south": (p, self.d - 0.4), "west": (0.4, p), "east": (self.w - 0.4, p)}[wall]

    def add(self, key, x, z, yaw=0.0, y=0.0, kind=None, mounted=False, extra=None):
        info = piece_info(key)
        sc = float((extra or {}).pop("scale", 1.0)) if extra else 1.0
        if sc != 1.0 and info["anchor"] != "viewer":
            raise PlanError("only sky pieces (viewer anchor) may be scaled: %s" % key)
        row = {"asset": key, "position": [snap(x), snap(y), snap(z)], "scale": [sc, sc, sc], "yaw": float(yaw)}
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
                                     anchor=info["anchor"], index=len(self.pieces) - 1))
        return row

    def place(self, spec):
        key = spec["key"]
        info = piece_info(key)
        anchor = info["anchor"]
        yaw = float(spec.get("yaw", 0.0))
        if yaw % 90 and (anchor in GRID_ANCHORS or anchor in ("door_anchor", "wall_face")):
            raise PlanError("non-interlocking: grid piece %s at yaw %s (grid pieces turn in 90-degree steps)" % (key, yaw))
        kind = spec.get("kind")
        y = float(spec.get("y", 0.0))
        extra = dict(spec.get("extra") or {})
        if "scale" in spec:
            extra["scale"] = float(spec["scale"])
        if spec.get("when"):
            piece_info(spec["when"]["asset"])
            extra.update(flag=spec["when"]["flag"], asset_when_set=spec["when"]["asset"])
        if "block" in spec:
            if anchor != "cell_block_centre":
                raise PlanError("%s is not a cell-block piece (anchor %s)" % (key, anchor))
            sx, sy = info["cells"]
            if int(yaw) % 180:
                sx, sy = sy, sx
            x, z = self.block_centre(spec["block"][0], spec["block"][1], sx, sy)
            return self.add(key, x, z, yaw, y=y, kind=kind or "shell", extra=extra)
        if "cell" in spec:
            if anchor not in ("cell_centre", "cell_block_centre"):
                raise PlanError("%s cannot snap to a cell (anchor %s)" % (key, anchor))
            x, z = self.cell_centre(*spec["cell"])
            return self.add(key, x, z, yaw, y=y, kind=kind or "shell", extra=extra)
        if "edge" in spec:
            if anchor != "cell_edge":
                raise PlanError("%s is not a cell-edge piece (anchor %s)" % (key, anchor))
            cx, cy, side = spec["edge"]
            x, z = self.edge_point(cx, cy, side)
            return self.add(key, x, z, EDGE_YAW[side] + yaw, y=y, kind=kind or "wall", extra=extra)
        if "tile" in spec:
            if anchor != "terrain_tile":
                raise PlanError("%s is not a terrain tile (anchor %s)" % (key, anchor))
            i, j = spec["tile"]
            if (i, j) in self.tiles:
                raise PlanError("terrain tile %s placed twice" % ([i, j],))
            x, z = self.tile_centre(i, j)
            self.tiles[(i, j)] = (key, yaw)
            return self.add(key, x, z, yaw, y=y, kind=kind or "floor", extra=extra)
        if "at_m" in spec:
            if anchor in GRID_ANCHORS:
                raise PlanError("non-interlocking: %s is a grid piece (anchor %s) and must snap to a cell/block/edge/tile, "
                                "not free metres" % (key, anchor))
            x, z = spec["at_m"]
            return self.add(key, x, z, yaw, y=y, kind=kind, mounted=bool(spec.get("mounted", False)), extra=extra)
        raise PlanError("%s: no placement (block / cell / edge / tile / at_m / wall / door)" % key)

    def find(self, kind, x, z, tol=TOL):
        return [s for s in self.sockets if s["type"] == kind and abs(s["at"][0] - x) < tol and abs(s["at"][2] - z) < tol]

    # ------------------------------------------------------------ terrain edges
    def tile_edges(self, i, j):
        key, yaw = self.tiles[(i, j)]
        edges = piece_info(key).get("edges") or {}
        return {rot_facing(side, yaw): e for side, e in edges.items()}

    def check_terrain(self):
        out = 0
        for (i, j) in sorted(self.tiles):
            mine = self.tile_edges(i, j)
            for side, (di, dj) in (("e", (1, 0)), ("s", (0, 1))):
                if (i + di, j + dj) not in self.tiles:
                    continue
                theirs = self.tile_edges(i + di, j + dj)
                a, b = mine.get(side), theirs.get(OPPOSITE[side])
                if a is None or b is None:
                    raise PlanError("terrain tile %s has no %s edge data" % ([i, j], side))
                if edge_sig(a) != edge_sig(b):
                    # a rotated ramp edge runs the other way on the neighbour: from/to swap is the same physical edge
                    if not (a["type"] == b["type"] != "ground" and edge_sig(dict(a, **{"from": a["to"], "to": a["from"]})) == edge_sig(b)):
                        raise PlanError("non-interlocking: terrain tiles %s (%s) and %s (%s) disagree on their shared edge: "
                                        "%s vs %s" % ([i, j], self.tiles[(i, j)][0], [i + di, j + dj], self.tiles[(i + di, j + dj)][0],
                                                      edge_sig(a), edge_sig(b)))
                out += 1
        return out


def compile_room(plan):
    """plan -> (spec room, presentation row, report). Raises PlanError on any broken connector rule."""
    rm = Room(plan)
    for spec in plan.get("pieces", []):
        rm.place(spec)
    exterior = bool(plan.get("exterior", False))
    # doors: data doors on door sockets, frames by room.gd (arch.door -> stn.doorway), inserts on the same anchor
    doors, props, used = [], [], set()
    for dr in plan.get("doors", []):
        side, cell = dr["side"], int(dr["cell"])
        wall = WALL[side]
        position = int(CELL * cell + 2)
        ax, az = rm.door_anchor(wall, position)
        hit = [s for s in rm.find("door", ax, az) if s["anchor"] != "door_anchor" and s["facing_w"] == side]
        if not hit and exterior:
            hit = [s for s in rm.find("door", ax, az) if s["anchor"] == "door_anchor"]
        if not hit:
            raise PlanError("non-interlocking: door %s (%s cell %d) has no door socket at the door anchor (%.2f, %.2f); "
                            "the wall there is uncut" % (dr["id"], wall, cell, ax, az))
        used.add(id(hit[0]))
        doors.append({"id": dr["id"], "wall": wall, "position": position, "to_room": dr["to_room"], "to_door": dr["to_door"],
                      "label": dr["label"], "conditions": dr.get("conditions", [])})
        rm.tris += int(piece_info(DOOR_FRAME)["tris"] or 0)
        if dr.get("insert"):
            ins = dr["insert"]
            extra = {}
            if dr.get("insert_when"):
                extra = {"flag": dr["insert_when"]["flag"], "asset_when_set": dr["insert_when"]["asset"]}
                piece_info(extra["asset_when_set"])
            if piece_info(ins)["anchor"] != "door_anchor":
                raise PlanError("door insert %s is not a door-anchor piece" % ins)
            rm.add(ins, ax, az, DOOR_YAW[wall], kind="insert", extra=extra)
            rm.pieces[-1].setdefault("note", "door insert on %s" % dr["id"])
            rm.sockets = [s for s in rm.sockets if s["index"] != len(rm.pieces) - 1]
    for s in rm.sockets:
        if s["type"] == "door" and id(s) not in used and s["anchor"] != "door_anchor":
            raise PlanError("non-interlocking: %s has a cut door socket at (%.2f, %.2f) with no door declared there" % (
                s["piece"], s["at"][0], s["at"][2]))
    # corridor sockets pair up; open corridor ends are errors (exteriors: declared mouths onto terrain)
    mouths = {(int(m[0]), int(m[1]), m[2]) for m in plan.get("mouths", [])} if exterior else set()
    seen_mouths = set()
    for s in rm.sockets:
        if s["type"] != "corridor":
            continue
        mates = [t for t in rm.find("corridor", s["at"][0], s["at"][2]) if t is not s and t["facing_w"] == OPPOSITE[s["facing_w"]]]
        if mates:
            continue
        cx = int(math.floor((s["at"][0] - APRON - VEC[s["facing_w"]][0] * 0.5) / CELL))
        cz = int(math.floor((s["at"][2] - APRON - VEC[s["facing_w"]][1] * 0.5) / CELL))
        if (cx, cz, s["facing_w"]) in mouths:
            seen_mouths.add((cx, cz, s["facing_w"]))
            continue
        raise PlanError("non-interlocking: corridor socket of %s at (%.2f, %.2f) facing %s meets nothing" % (
            s["piece"], s["at"][0], s["at"][2], s["facing_w"]))
    if mouths - seen_mouths:
        raise PlanError("declared corridor mouth(s) %s have no open corridor socket" % sorted(mouths - seen_mouths))
    # window sockets carry their viewport
    for s in [s for s in rm.sockets if s["type"] == "window" and s["anchor"] != "door_anchor"]:
        vp = VIEWPORT_FOR.get(s.get("kind", "band"), "stn.viewport")
        rm.add(vp, s["at"][0], s["at"][2], DOOR_YAW[WALL[s["facing_w"]]], kind="window", mounted=True)
    # wall mounts on named wall sockets (back on the inner face, facing into the room)
    for m in plan.get("wall", []):
        side, cell = m["socket"][0], int(m["socket"][1:])
        hit = [s for s in rm.sockets if s["type"] == "wall" and s["facing_w"] == side and s.get("cell") == cell]
        if not hit:
            raise PlanError("wall mount %s: no wall socket %s" % (m["key"], m["socket"]))
        if piece_info(m["key"])["anchor"] != "wall_face":
            raise PlanError("wall mount %s is not a wall-face piece" % m["key"])
        s = hit[0]
        rm.add(m["key"], s["at"][0], s["at"][2], FACE_IN_YAW[side], mounted=True)
    joined = rm.check_terrain()
    # room props (interaction targets) and people
    for p in plan.get("props", []):
        info = piece_info(p["asset"])
        if info["anchor"] in GRID_ANCHORS:
            raise PlanError("prop %s: grid pieces are not free props" % p["id"])
        props.append({"id": p["id"], "asset": p["asset"], "position": [snap(p["at_m"][0]), 0, snap(p["at_m"][1])],
                      "rotation": [0, float(p.get("yaw", 0.0)), 0]})
        rm.tris += int(info["tris"] or 0)
    if plan.get("backdrop", True):
        rm.tris += int(piece_info(BACKDROP)["tris"] or 0)
    people = 1 + len(plan.get("characters", {}))
    est = rm.tris + PERSON_TRIS * people + COLLISION_TRIS
    if est > TRI_CAP:
        raise PlanError("over budget: %s estimates %d triangles (kit %d + %d people x %d) > %d" % (
            plan["id"], est, rm.tris, people, PERSON_TRIS, TRI_CAP))
    cam = plan["camera"]
    room = {"id": plan["id"], "name": plan["name"], "description": plan["description"], "grid_size": [int(rm.w), int(rm.d)],
            "kit_refs": [], "doors": doors, "cameras": [{"id": "game", "position": cam["position"], "look_at": cam["look_at"]}],
            "props": props, "character_ids": [plan.get("protagonist", "pilot")] + sorted(plan.get("characters", {}))}
    pres = {"exterior": exterior, "kit_shell": True, "floor": "", "look_profile": plan.get("look_profile", "corridor"),
            "wall_height": plan.get("wall_height", 4.0), "camera": "game", "cameras": [dict(cam, id="game")], "pieces": rm.pieces}
    if plan.get("characters"):
        pres["characters"] = plan["characters"]
    if plan.get("interactions"):
        pres["interactions"] = plan["interactions"]
    report = {"id": plan["id"], "plot_m": [rm.w, rm.d], "pieces": len(rm.pieces), "kit_tris": rm.tris, "people": people,
              "tri_estimate": est, "tri_cap": TRI_CAP, "terrain_edges_joined": joined,
              "sockets": {k: sum(1 for s in rm.sockets if s["type"] == k) for k in sorted({s["type"] for s in rm.sockets})},
              "checks": ["doors on door sockets", "every door socket used", "corridor sockets paired", "windows carry viewports",
                         "wall mounts on wall sockets", "terrain edges agree", "grid pieces snapped", "tri estimate <= cap"]}
    return room, pres, report


def main(argv):
    if len(argv) != 2 or argv[0] != "check":
        print(__doc__)
        return 2
    plan = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    try:
        _, _, rep = compile_room(plan)
    except PlanError as e:
        print("REJECTED:", e)
        return 1
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
