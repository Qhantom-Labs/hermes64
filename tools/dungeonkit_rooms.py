"""DUNGEONKIT room compiler: assemble plugin rooms from kit pieces BY DATA on the DUNGEON GRID.

A room plan names kit build keys (kits/library/dungeonkit-sockets.json "pieces") and where they snap: cell blocks,
cells, cell edges, declared doors, wall sockets or (free props only) metres. compile_room() turns it into the two
things the plugin's normal path consumes: a spec room (grid_size, doors, props, cameras) and its presentation row
(pieces with positions/yaw, look profile, kit_shell). Every placement is checked against the socket manifest
(connector rules) before anything is written:

- every declared door sits on a door socket of a placed piece (same wall, same point) and every door socket carries a
  declared door (no uncut frames, no holes without frames);
- corridor sockets pair with an opposite corridor socket on the same cell edge;
- room pit sockets (open cells) are filled by a dgn.pit / dgn.stairs cell;
- torch sockets carry a sconce (mounted automatically with the plan's torch piece);
- cell-anchored pieces can only be placed on the grid (cell / block / edge), never by free metres;
- the triangle estimate (manifest tris + door frames + people) stays inside the 6,000-triangle room cap.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.dungeonkit_rooms check PLAN.json   # compile one plan, print the report
"""
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SOCKETS = R / "kits" / "library" / "dungeonkit-sockets.json"
CELL, APRON, WALL_T = 4.0, 0.5, 0.5
WALL = {"n": "north", "s": "south", "e": "east", "w": "west"}
DOOR_YAW = {"north": 0.0, "south": 180.0, "west": 90.0, "east": -90.0}     # room.gd arch.door yaw
FACE_IN_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                 # wall-face prop on a wall facing <key>
EDGE_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                    # cell_edge piece standing on a side
CORNER_YAW = {"ne": 0.0, "nw": 90.0, "sw": 180.0, "se": -90.0}
DOOR_FRAME = "dgn.doorway"
TRI_CAP = 6000
PERSON_TRIS = 760          # measured runtime person (protagonist 732-760 tris, actors 650-756); + floor collision
COLLISION_TRIS = 12
CELL_ANCHORS = ("cell_block_centre", "cell_centre", "cell_edge")
OPEN_FILL = ("dgn.pit", "dgn.stairs", "dgn.floor", "tmpl.floor")
TOL = 0.011


class PlanError(ValueError):
    pass


_MAN = {}


def manifest():
    if not _MAN:
        _MAN.update(json.loads(SOCKETS.read_text(encoding='utf-8')))
    return _MAN


def piece_info(key):
    pieces = manifest()["pieces"]
    if key not in pieces:
        raise PlanError("not a DUNGEONKIT kit piece: %r (kit-only rooms; see dungeonkit-sockets.json)" % key)
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
        self.pieces, self.sockets, self.notes = [], [], []
        self.tris = 0

    # ------------------------------------------------------------ grid helpers (plot metres, Godot x east / z south)
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
        anchor = info["anchor"]
        yaw = float(spec.get("yaw", 0.0))
        if yaw % 90 and (anchor in CELL_ANCHORS or anchor in ("door_anchor", "wall_face", "corner")):
            raise PlanError("non-interlocking: grid piece %s at yaw %s (grid pieces turn in 90-degree steps)" % (key, yaw))
        kind = spec.get("kind")
        mounted = bool(spec.get("mounted", False))
        if spec.get("when"):
            piece_info(spec["when"]["asset"])
            spec = dict(spec, extra=dict(spec.get("extra") or {}, flag=spec["when"]["flag"], asset_when_set=spec["when"]["asset"]))
        if "block" in spec:
            if anchor != "cell_block_centre":
                raise PlanError("%s is not a cell-block piece (anchor %s)" % (key, anchor))
            sx, sy = info["cells"]
            if int(yaw) % 180:
                sx, sy = sy, sx
            x, z = self.block_centre(spec["block"][0], spec["block"][1], sx, sy)
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind or "shell", extra=spec.get("extra"))
        if "cell" in spec:
            if anchor not in ("cell_centre", "cell_block_centre"):
                raise PlanError("%s cannot snap to a cell (anchor %s)" % (key, anchor))
            x, z = self.cell_centre(*spec["cell"])
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind or "shell", extra=spec.get("extra"))
        if "edge" in spec:
            if anchor != "cell_edge":
                raise PlanError("%s is not a cell-edge piece (anchor %s)" % (key, anchor))
            cx, cy, side = spec["edge"]
            x, z = self.edge_point(cx, cy, side)
            return self.add(key, x, z, EDGE_YAW[side] + yaw, y=float(spec.get("y", 0.0)), kind=kind or "wall")
        if "corner" in spec:
            cx, cy, c = spec["corner"]
            ccx, ccz = self.cell_centre(cx, cy)
            h = CELL / 2 - WALL_T
            x = ccx + (h if "e" in c else -h)
            z = ccz + (-h if "n" in c else h)
            return self.add(key, x, z, CORNER_YAW[c], kind=kind, mounted=True)
        if "at_m" in spec:
            if anchor in CELL_ANCHORS:
                raise PlanError("non-interlocking: %s is a grid piece (anchor %s) and must snap to a cell/block/edge, "
                                "not free metres" % (key, anchor))
            x, z = spec["at_m"]
            return self.add(key, x, z, yaw, y=float(spec.get("y", 0.0)), kind=kind, mounted=mounted,
                            extra=spec.get("extra"))
        raise PlanError("%s: no placement (block / cell / edge / corner / at_m / socket / door)" % key)

    # ------------------------------------------------------------ connector rules
    def find(self, kind, x, z, tol=TOL):
        return [s for s in self.sockets if s["type"] == kind and abs(s["at"][0] - x) < tol and abs(s["at"][2] - z) < tol]

    def door_face_point(self, wall, position):
        p = position + 0.5
        return {"north": (p, APRON + WALL_T), "south": (p, self.d - APRON - WALL_T), "west": (APRON + WALL_T, p),
                "east": (self.w - APRON - WALL_T, p)}[wall]


def compile_room(plan):
    """plan -> (spec room, presentation row, report). Raises PlanError on any broken connector rule."""
    rm = Room(plan)
    for spec in plan.get("pieces", []):
        rm.place(spec)
    # doors: data doors on door sockets, frames by room.gd (arch.door -> dgn.doorway), inserts on the same anchor
    doors, props = [], []
    used = set()
    for dr in plan.get("doors", []):
        side, cell = dr["side"], int(dr["cell"])
        wall = WALL[side]
        position = int(CELL * cell + 2)
        fx, fz = rm.door_face_point(wall, position)
        hit = [s for s in rm.find("door", fx, fz) if s["facing_w"] == side]
        ax = position + 0.5 if wall in ("north", "south") else (0.4 if wall == "west" else rm.w - 0.4)
        az = position + 0.5 if wall in ("east", "west") else (0.4 if wall == "north" else rm.d - 0.4)
        if not hit and plan.get("exterior"):
            # exteriors: a cave mouth (or any opening socket) on the door anchor, opening toward the plot
            hit = [s for s in rm.find("cave_mouth", ax, az) if s["facing_w"] == OPPOSITE[side]]
        if not hit:
            raise PlanError("non-interlocking: door %s (%s cell %d) has no door socket at (%.2f, %.2f); the wall there is "
                            "uncut" % (dr["id"], wall, cell, fx, fz))
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
            info = piece_info(ins)
            if info["anchor"] != "door_anchor":
                raise PlanError("door insert %s is not a door-anchor piece" % ins)
            rm.add(ins, ax, az, DOOR_YAW[wall], kind="insert", extra=extra)
            rm.pieces[-1].setdefault("note", "door insert on %s" % dr["id"])
    for s in rm.sockets:
        if s["type"] == "door" and id(s) not in used and s["piece"] != DOOR_FRAME and not s.get("fits"):
            raise PlanError("non-interlocking: %s has a cut door socket at (%.2f, %.2f) with no door declared there" % (
                s["piece"], s["at"][0], s["at"][2]))
    # corridor sockets pair up; open corridor ends are errors
    for s in rm.sockets:
        if s["type"] != "corridor":
            continue
        mates = [t for t in rm.find("corridor", s["at"][0], s["at"][2]) if t is not s and t["facing_w"] == OPPOSITE[s["facing_w"]]]
        if not mates:
            raise PlanError("non-interlocking: corridor socket of %s at (%.2f, %.2f) facing %s meets nothing" % (
                s["piece"], s["at"][0], s["at"][2], s["facing_w"]))
    # pit sockets need a pit / stairs cell
    for s in rm.sockets:
        if s["type"] != "pit":
            continue
        fill = [p for p in rm.pieces if p["asset"].split("__")[0] in OPEN_FILL and
                abs(p["position"][0] - s["at"][0]) < TOL and abs(p["position"][2] - s["at"][2]) < TOL]
        if not fill:
            raise PlanError("non-interlocking: open room cell at (%.2f, %.2f) has no %s piece" % (s["at"][0], s["at"][2], " / ".join(OPEN_FILL)))
    # torch sockets get the plan's sconce; wall mounts on named wall sockets
    torch = plan.get("torch", "dprop.sconce")
    for s in list(rm.sockets):
        if s["type"] == "torch":
            rm.add(torch, s["at"][0], s["at"][2], FACE_IN_YAW[s["facing_w"]], mounted=True)
    for m in plan.get("wall", []):
        side, cell = m["socket"][0], int(m["socket"][1:])
        hit = [s for s in rm.sockets if s["type"] == "wall" and s["facing_w"] == side and s.get("cell") == cell]
        if not hit:
            raise PlanError("wall mount %s: no wall socket %s" % (m["key"], m["socket"]))
        s = hit[0]
        rm.add(m["key"], s["at"][0], s["at"][2], FACE_IN_YAW[side], mounted=True)
    # room props (interaction targets) and people
    for p in plan.get("props", []):
        info = piece_info(p["asset"])
        if info["anchor"] in CELL_ANCHORS:
            raise PlanError("prop %s: grid pieces are not free props" % p["id"])
        props.append({"id": p["id"], "asset": p["asset"], "position": [snap(p["at_m"][0]), 0, snap(p["at_m"][1])],
                      "rotation": [0, float(p.get("yaw", 0.0)), 0]})
        rm.tris += int(info["tris"] or 0)
    people = 1 + len(plan.get("characters", {}))
    est = rm.tris + PERSON_TRIS * people + COLLISION_TRIS
    if est > TRI_CAP:
        raise PlanError("over budget: %s estimates %d triangles (kit %d + %d people x %d) > %d" % (
            plan["id"], est, rm.tris, people, PERSON_TRIS, TRI_CAP))
    cam = plan["camera"]
    room = {"id": plan["id"], "name": plan["name"], "description": plan["description"], "grid_size": [int(rm.w), int(rm.d)],
            "kit_refs": [], "doors": doors, "cameras": [{"id": "game", "position": cam["position"], "look_at": cam["look_at"]}],
            "props": props, "character_ids": [plan.get("protagonist", "pilgrim")] + sorted(plan.get("characters", {}))}
    # kit_shell: the kit pieces bring the walls and the socket-checked door openings (room.gd adds no placeholder walls
    # and treats the arch.door frames as cut); exteriors open their doors through cave mouths
    pres = {"exterior": bool(plan.get("exterior", False)), "kit_shell": True, "floor": "",
            "look_profile": plan.get("look_profile", "dungeon"), "wall_height": plan.get("wall_height", 4.5),
            "camera": "game", "cameras": [dict(cam, id="game")], "pieces": rm.pieces}
    if plan.get("characters"):
        pres["characters"] = plan["characters"]
    if plan.get("interactions"):
        pres["interactions"] = plan["interactions"]
    report = {"id": plan["id"], "plot_m": [rm.w, rm.d], "pieces": len(rm.pieces), "kit_tris": rm.tris, "people": people,
              "tri_estimate": est, "tri_cap": TRI_CAP,
              "sockets": {k: sum(1 for s in rm.sockets if s["type"] == k) for k in sorted({s["type"] for s in rm.sockets})},
              "checks": ["doors on door sockets", "every door socket used", "corridor sockets paired", "pit cells filled",
                         "torch sockets carry sconces", "grid pieces snapped", "tri estimate <= cap"]}
    return room, pres, report


def main(argv):
    if len(argv) != 2 or argv[0] != "check":
        print(__doc__)
        return 2
    plan = json.loads(Path(argv[1]).read_text(encoding='utf-8'))
    try:
        _, _, rep = compile_room(plan)
    except PlanError as e:
        print("REJECTED:", e)
        return 1
    print(json.dumps(rep, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
