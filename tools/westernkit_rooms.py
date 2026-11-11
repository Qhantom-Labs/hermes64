"""WESTERNKIT room compiler: assemble plugin rooms from frontier kit pieces BY DATA on the FRONTIER GRID.

A room plan names kit build keys (kits/library/westernkit-sockets.json "pieces") and where they snap: cell blocks,
cells, lot lines, declared doors, wall sockets or (free props only) metres. compile_room() turns it into what the
plugin's normal path consumes: a spec room (grid_size, doors, props, cameras) and its presentation row (pieces with
positions / yaw, look profile, kit_shell). Every placement is checked against the socket manifest before anything is
written:

- every declared door sits on a door socket of a placed piece (a building frontage, an interior shell, a fence
  gateway, a mine portal or a tunnel end) exactly on the room.gd door anchor (0.4 m in from the plot edge), facing out
  of the room; every door socket carries a declared door (no dark doorways without a frame, no frames on bare walls);
- boardwalk / platform "walk" sockets pair with an opposite walk socket (closed runs end in end_w / end_e modules);
- track and tunnel sockets pair with an opposite socket of the same type on the same point (rail and mine track, the
  trestle deck and tunnels never end in the open);
- porch roofs, balconies and galleries ("*_fit" sockets) sit on a building frontage of at least their span;
- lamp sockets on interior shells carry the plan's wall lantern (mounted automatically);
- grid pieces (lot line, cell, cell block, door anchor) snap to the grid and turn in 90-degree steps only;
- the triangle estimate (manifest tris + door frames + the sky dome on exteriors + people) stays inside the
  6,000-triangle room cap.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.westernkit_rooms check PLAN.json   # compile one plan, print the report
"""
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SOCKETS = R / "kits" / "library" / "westernkit-sockets.json"
CELL, APRON, WALL_T = 4.0, 0.5, 0.12
ANCHOR_IN = 0.4                 # room.gd door anchor: 0.4 m in from the plot edge
WALL = {"n": "north", "s": "south", "e": "east", "w": "west"}
DOOR_YAW = {"north": 0.0, "south": 180.0, "west": 90.0, "east": -90.0}     # room.gd arch.door yaw
FACE_IN_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                 # wall-face prop on a wall facing <key>
LOT_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                     # lot-line piece with its back to <key>
DOOR_FRAME = "wtown.doorway"
BACKDROP = "wsky.dome"
TRI_CAP = 6000
PERSON_TRIS = 760          # measured runtime person (protagonist 732-760 tris, actors 650-756); + floor collision
COLLISION_TRIS = 12
GRID_ANCHORS = ("cell_block_centre", "cell_centre", "lot_line", "door_anchor")
PAIRED = ("walk", "track", "tunnel")
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
        raise PlanError("not a WESTERNKIT kit piece: %r (kit-only rooms; see westernkit-sockets.json)" % key)
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


def half_step(v, what):
    if abs(v * 2 - round(v * 2)) > 1e-9:
        raise PlanError("non-interlocking: %s %.3f is off the frontier grid (cells in 0.5 steps)" % (what, v))
    return v


class Room:
    def __init__(self, plan):
        self.plan = plan
        cx, cy = plan["plot_cells"]
        self.cells = (cx, cy)
        self.w, self.d = CELL * cx + 2 * APRON, CELL * cy + 2 * APRON
        self.pieces, self.sockets = [], []
        self.tris = 0

    # ------------------------------------------------------------ grid helpers (plot metres, Godot x east / z south)
    def grid(self, gx, gy):
        return (APRON + CELL * gx, APRON + CELL * gy)

    def cell_centre(self, x, y):
        return self.grid(x + 0.5, y + 0.5)

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
                                     index=len(self.pieces) - 1, yaw=yaw))
        return row

    def place(self, spec):
        key = spec["key"]
        info = piece_info(key)
        anchor = info["anchor"]
        yaw = float(spec.get("yaw", 0.0))
        if yaw % 90 and anchor in GRID_ANCHORS:
            raise PlanError("non-interlocking: grid piece %s at yaw %s (grid pieces turn in 90-degree steps)" % (key, yaw))
        kind = spec.get("kind")
        y = float(spec.get("y", 0.0))
        if "block" in spec:
            if anchor != "cell_block_centre":
                raise PlanError("%s is not a cell-block piece (anchor %s)" % (key, anchor))
            sx, sy = info["cells"]
            if int(yaw) % 180:
                sx, sy = sy, sx
            half_step(spec["block"][0], "block x")
            half_step(spec["block"][1], "block y")
            x, z = self.grid(spec["block"][0] + sx / 2.0, spec["block"][1] + sy / 2.0)
            return self.add(key, x, z, yaw, y=y, kind=kind or "shell", extra=spec.get("extra"))
        if "cell" in spec:
            if anchor != "cell_centre":
                raise PlanError("%s cannot snap to a cell (anchor %s)" % (key, anchor))
            x, z = self.cell_centre(*spec["cell"])
            return self.add(key, x, z, yaw, y=y, kind=kind or "shell", extra=spec.get("extra"))
        if "lot" in spec:
            # [gx, gy, side]: origin on the grid point (gx, gy) in cells (0.5 steps along the line), back to <side>
            if anchor != "lot_line":
                raise PlanError("%s is not a lot-line piece (anchor %s)" % (key, anchor))
            gx, gy, side = spec["lot"]
            if side in "ns":
                half_step(gx, "lot x")
                if abs(gy - round(gy)) > 1e-9:
                    raise PlanError("non-interlocking: %s lot line y %.2f is not a cell boundary" % (key, gy))
            else:
                half_step(gy, "lot y")
                if abs(gx - round(gx)) > 1e-9:
                    raise PlanError("non-interlocking: %s lot line x %.2f is not a cell boundary" % (key, gx))
            x, z = self.grid(gx, gy)
            return self.add(key, x, z, LOT_YAW[side] + yaw, y=y, kind=kind or "wall", extra=spec.get("extra"))
        if "at_m" in spec:
            if anchor in GRID_ANCHORS:
                raise PlanError("non-interlocking: %s is a grid piece (anchor %s) and must snap to the grid (block / cell / "
                                "lot), not free metres" % (key, anchor))
            x, z = spec["at_m"]
            return self.add(key, x, z, yaw, y=y, kind=kind, mounted=bool(spec.get("mounted", False)), extra=spec.get("extra"))
        raise PlanError("%s: no placement (block / cell / lot / at_m / wall / door)" % key)

    def find(self, kind, x, z, tol=TOL):
        return [s for s in self.sockets if s["type"] == kind and abs(s["at"][0] - x) < tol and abs(s["at"][2] - z) < tol]

    def door_anchor(self, wall, position):
        p = position + 0.5
        return {"north": (p, ANCHOR_IN), "south": (p, self.d - ANCHOR_IN), "west": (ANCHOR_IN, p),
                "east": (self.w - ANCHOR_IN, p)}[wall]


def compile_room(plan):
    """plan -> (spec room, presentation row, report). Raises PlanError on any broken connector rule."""
    rm = Room(plan)
    for spec in plan.get("pieces", []):
        rm.place(spec)
    doors, props, used = [], [], set()
    for dr in plan.get("doors", []):
        side = dr["side"]
        wall = WALL[side]
        cell = half_step(float(dr["cell"]), "door cell")
        position = int(round(CELL * cell + 2))
        ax, az = rm.door_anchor(wall, position)
        hit = [s for s in rm.find("door", ax, az) if s["facing_w"] == side and s["piece"] != DOOR_FRAME]
        if not hit:
            raise PlanError("non-interlocking: door %s (%s cell %s) has no door socket on its anchor (%.2f, %.2f); the "
                            "wall / frontage there is uncut" % (dr["id"], wall, cell, ax, az))
        used.add(id(hit[0]))
        doors.append({"id": dr["id"], "wall": wall, "position": position, "to_room": dr["to_room"], "to_door": dr["to_door"],
                      "label": dr["label"], "conditions": dr.get("conditions", [])})
        rm.tris += int(piece_info(DOOR_FRAME)["tris"] or 0)
    for s in rm.sockets:
        if s["type"] == "door" and id(s) not in used and s["piece"] != DOOR_FRAME:
            raise PlanError("non-interlocking: %s has a door socket at (%.2f, %.2f) with no door declared there (a dark "
                            "doorway without a frame)" % (s["piece"], s["at"][0], s["at"][2]))
    # paired connectors: boardwalks / platforms, track (rail, mine, trestle) and tunnels never end in the open, except
    # a declared open end ON or beyond the plot boundary (the line runs on out of the room)
    open_ends = [tuple(e) for e in plan.get("open_ends", [])]
    for s in rm.sockets:
        if s["type"] not in PAIRED:
            continue
        mates = [t for t in rm.find(s["type"], s["at"][0], s["at"][2]) if t is not s and t["facing_w"] == OPPOSITE[s["facing_w"]]]
        x, z = s["at"][0], s["at"][2]
        edge = x <= APRON + TOL or x >= rm.w - APRON - TOL or z <= APRON + TOL or z >= rm.d - APRON - TOL
        declared = any(e[2] == s["type"] and abs(e[0] - x) < TOL and abs(e[1] - z) < TOL for e in open_ends)
        if not mates and edge and declared:
            continue
        if not mates:
            raise PlanError("non-interlocking: %s socket of %s at (%.2f, %.2f) facing %s meets nothing" % (
                s["type"], s["piece"], s["at"][0], s["at"][2], s["facing_w"]))
    # porch roofs / balconies / galleries fit a frontage (or an interior wall line) of at least their span
    for s in rm.sockets:
        if not s["type"].endswith("_fit"):
            continue
        hosts = [t for t in rm.find("frontage", s["at"][0], s["at"][2]) if t["facing_w"] == OPPOSITE[s["facing_w"]]]
        if not hosts or int(hosts[0].get("span", 0)) < int(s.get("span", 1)):
            raise PlanError("non-interlocking: %s at (%.2f, %.2f) fits no building frontage of span >= %s" % (
                s["piece"], s["at"][0], s["at"][2], s.get("span")))
    # lamp sockets carry the plan's wall lantern; named wall mounts
    lamp = plan.get("lamp", "wprop.lantern__wall")
    for s in list(rm.sockets):
        if s["type"] == "lamp":
            # the wall lantern's back plate sits 0.27 m behind its origin (the lamp): back to the wall, lamp in the room
            yaw = LOT_YAW[s["facing_w"]]
            ox, oz = rot(0.0, 0.27, yaw)
            rm.add(lamp, s["at"][0] + ox, s["at"][2] + oz, yaw, y=float(s.get("mount_height_m", 2.3)) - 0.15, mounted=True)
    for p in plan.get("props", []):
        info = piece_info(p["asset"])
        if info["anchor"] in GRID_ANCHORS:
            raise PlanError("prop %s: grid pieces are not free props" % p["id"])
        props.append({"id": p["id"], "asset": p["asset"], "position": [snap(p["at_m"][0]), 0, snap(p["at_m"][1])],
                      "rotation": [0, float(p.get("yaw", 0.0)), 0]})
        rm.tris += int(info["tris"] or 0)
    if plan.get("exterior"):
        rm.tris += int(piece_info(BACKDROP)["tris"] or 0)
    people = 1 + len(plan.get("characters", {}))
    est = rm.tris + PERSON_TRIS * people + COLLISION_TRIS
    if est > TRI_CAP:
        raise PlanError("over budget: %s estimates %d triangles (kit %d + %d people x %d) > %d" % (
            plan["id"], est, rm.tris, people, PERSON_TRIS, TRI_CAP))
    cam = plan["camera"]
    room = {"id": plan["id"], "name": plan["name"], "description": plan["description"], "grid_size": [int(rm.w), int(rm.d)],
            "kit_refs": [], "doors": doors, "cameras": [{"id": "game", "position": cam["position"], "look_at": cam["look_at"]}],
            "props": props, "character_ids": [plan.get("protagonist", "drifter")] + sorted(plan.get("characters", {}))}
    pres = {"exterior": bool(plan.get("exterior", False)), "kit_shell": True, "floor": "",
            "look_profile": plan.get("look_profile", "street"), "wall_height": plan.get("wall_height", 4.2),
            "camera": "game", "cameras": [dict(cam, id="game")], "pieces": rm.pieces}
    if plan.get("characters"):
        pres["characters"] = plan["characters"]
    report = {"id": plan["id"], "plot_m": [rm.w, rm.d], "pieces": len(rm.pieces), "kit_tris": rm.tris, "people": people,
              "tri_estimate": est, "tri_cap": TRI_CAP,
              "sockets": {k: sum(1 for s in rm.sockets if s["type"] == k) for k in sorted({s["type"] for s in rm.sockets})},
              "checks": ["doors on door sockets at the room.gd anchor", "every door socket used", "walk / track / tunnel sockets "
                         "paired", "porch / balcony fits on frontages", "lamp sockets carry lanterns", "grid pieces snapped",
                         "tri estimate <= cap"]}
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
