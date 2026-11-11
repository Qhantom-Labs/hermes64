"""MEDIEVALKIT room compiler: assemble plugin rooms from kit pieces BY DATA on the MEDIEVAL GRID.

A room plan names kit build keys (kits/library/medievalkit-sockets.json "pieces") and where they snap: cell blocks,
cells, cell edges, declared doors (`door_to`: the piece's door socket lands on that door), other pieces' sockets
(`attach`: wall_end to wall_end, towers to the gate block) or (free / lot / landmark pieces only) metres.
compile_room() turns it into the two things the plugin's normal path consumes: a spec room (grid_size, doors, props,
cameras) and its presentation row (pieces with positions/yaw, look profile, kit_shell). Every placement is checked
against the socket manifest (connector rules) before anything is written:

- every declared door sits on a door socket of a placed piece (the door face point 1 m in from the plot edge, the same
  for room shells, town-wall posterns, buildings in doorway mode, the gate block's inner wall and the keep), and every
  socket that needs arch.door carries a declared door (no uncut frames, no holes without frames);
- torch / lantern / hearth sockets carry their mount (cst.sconce / mprop.lantern_hung / vlg.hearth, placed
  automatically), wall mounts go on named wall sockets;
- portcullis / drawbridge sockets carry their state-pair piece (optionally flag-swapped: closed -> raised);
- cell-anchored pieces can only be placed on the grid (cell / block / edge) or on another piece's socket, never by
  free metres; grid pieces turn in 90-degree steps;
- the triangle estimate (manifest tris + door frames + people) stays inside the 6,000-triangle room cap.

  PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.medievalkit_rooms check PLAN.json   # compile one plan, print the report
"""
import json
import math
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
SOCKETS = R / "kits" / "library" / "medievalkit-sockets.json"
CELL, APRON, WALL_T = 4.0, 0.5, 0.5
WALL = {"n": "north", "s": "south", "e": "east", "w": "west"}
DOOR_YAW = {"north": 0.0, "south": 180.0, "west": 90.0, "east": -90.0}     # room.gd arch.door yaw
FACE_IN_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                 # wall-face prop on a wall facing <key>
EDGE_YAW = {"n": 0.0, "s": 180.0, "e": -90.0, "w": 90.0}                    # cell_edge piece standing on a side
DOOR_FRAME = "vlg.doorway"
TRI_CAP = 6000
PERSON_TRIS = 760          # measured runtime person (protagonist 732-760 tris); + floor collision
COLLISION_TRIS = 12
CELL_ANCHORS = ("cell_block_centre", "cell_centre", "cell_edge")
MOUNTS = {"torch": "cst.sconce", "lantern": "mprop.lantern_hung", "hearth": "vlg.hearth"}
STATE_PIECES = {"portcullis": "cst.portcullis", "drawbridge": "cst.drawbridge"}
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
        raise PlanError("not a MEDIEVALKIT kit piece: %r (kit-only rooms; see medievalkit-sockets.json)" % key)
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


def yaw_facing(f_piece, f_world):
    """Yaw (multiple of 90) that turns a piece-space facing into a world facing."""
    for y in (0.0, 90.0, 180.0, -90.0):
        if rot_facing(f_piece, y) == f_world:
            return y
    raise PlanError("cannot turn facing %s to %s" % (f_piece, f_world))


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
        self.doors = {d["id"]: d for d in plan.get("doors", [])}

    def cell_centre(self, x, y):
        return (APRON + CELL * (x + 0.5), APRON + CELL * (y + 0.5))

    def block_centre(self, x, y, sx, sy):
        return (APRON + CELL * (x + sx / 2.0), APRON + CELL * (y + sy / 2.0))

    def edge_point(self, x, y, side):
        cxm, czm = self.cell_centre(x, y)
        return {"n": (cxm, czm - CELL / 2), "s": (cxm, czm + CELL / 2), "e": (cxm + CELL / 2, czm), "w": (cxm - CELL / 2, czm)}[side]

    def door_face_point(self, side, cell):
        p = CELL * cell + 2 + 0.5
        return {"n": (p, APRON + WALL_T), "s": (p, self.d - APRON - WALL_T), "w": (APRON + WALL_T, p), "e": (self.w - APRON - WALL_T, p)}[side]

    def door_anchor(self, side, cell):
        p = CELL * cell + 2 + 0.5
        return {"n": (p, 0.4), "s": (p, self.d - 0.4), "w": (0.4, p), "e": (self.w - 0.4, p)}[side]

    def add(self, key, x, z, yaw=0.0, y=0.0, kind=None, mounted=False, extra=None):
        info = piece_info(key)
        sc = (extra or {}).pop("scale", 1) if extra else 1
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
                                     index=len(self.pieces) - 1))
        return row

    def place(self, spec):
        key = spec["key"]
        info = piece_info(key)
        anchor = info["anchor"]
        yaw = float(spec.get("yaw", 0.0))
        grid_piece = anchor in CELL_ANCHORS or anchor in ("door_anchor", "wall_face", "cell_corner", "gate_anchor")
        if yaw % 90 and grid_piece:
            raise PlanError("non-interlocking: grid piece %s at yaw %s (grid pieces turn in 90-degree steps)" % (key, yaw))
        kind = spec.get("kind")
        extra = dict(spec.get("extra") or {})
        if spec.get("scale") is not None:
            if anchor != "viewer" and info.get("class") != "sky":
                raise PlanError("%s: only viewer-origin backdrops take a scale (kit pieces are metric)" % key)
            extra["scale"] = float(spec["scale"])
        if spec.get("when"):
            piece_info(spec["when"]["asset"])
            extra.update(flag=spec["when"]["flag"], asset_when_set=spec["when"]["asset"])
        y = float(spec.get("y", 0.0))
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
        if "door_to" in spec:
            dr = self.doors.get(spec["door_to"])
            if dr is None:
                raise PlanError("%s: door_to %r is not a declared door" % (key, spec["door_to"]))
            socks = [s for s in info["sockets"] if s["type"] == "door"]
            if not socks:
                raise PlanError("%s has no door socket to put on door %s" % (key, dr["id"]))
            s = socks[0]
            side = dr["side"]
            yw = yaw_facing(s["facing"], OPPOSITE[side]) if not spec.get("shell_facing") else yaw_facing(s["facing"], side)
            fx, fz = self.door_face_point(side, int(dr["cell"]))
            rx, rz = rot(s["position"][0], s["position"][2], yw)
            return self.add(key, fx - rx, fz - rz, yw, y=y, kind=kind or "landmark", extra=extra)
        if "attach" in spec:
            idx, sock_i = spec["attach"]
            tgt = [s for s in self.sockets if s["index"] == idx and s["type"] == "wall_end"]
            if isinstance(sock_i, str):          # by world facing of the target socket (n / s / e / w)
                tgt = [s for s in tgt if s["facing_w"] == sock_i]
                sock_i = 0
            if sock_i >= len(tgt):
                raise PlanError("%s: attach target piece %d has no wall_end socket %s" % (key, idx, spec["attach"][1]))
            t = tgt[sock_i]
            want = OPPOSITE[t["facing_w"]]
            own = [s for s in info["sockets"] if s["type"] == "wall_end"]
            for s in own:
                try:
                    yw = yaw_facing(s["facing"], want)
                except PlanError:
                    continue
                if spec.get("yaw_hint") is not None and yw != float(spec["yaw_hint"]):
                    continue
                rx, rz = rot(s["position"][0], s["position"][2], yw)
                return self.add(key, t["at"][0] - rx, t["at"][2] - rz, yw, y=t["at"][1] - s["position"][1], kind=kind or "wall", extra=extra)
            raise PlanError("non-interlocking: %s has no wall_end socket that meets %s's socket facing %s" % (key, t["piece"], t["facing_w"]))
        if "at_m" in spec:
            if anchor in CELL_ANCHORS:
                raise PlanError("non-interlocking: %s is a grid piece (anchor %s) and must snap to a cell/block/edge or a socket, "
                                "not free metres" % (key, anchor))
            x, z = spec["at_m"]
            return self.add(key, x, z, yaw, y=y, kind=kind, mounted=bool(spec.get("mounted", False)), extra=extra)
        raise PlanError("%s: no placement (block / cell / edge / door_to / attach / at_m)" % key)

    def find(self, kind, x, z, tol=TOL):
        return [s for s in self.sockets if s["type"] == kind and abs(s["at"][0] - x) < tol and abs(s["at"][2] - z) < tol]


def compile_room(plan):
    """plan -> (spec room, presentation row, report). Raises PlanError on any broken connector rule."""
    rm = Room(plan)
    for spec in plan.get("pieces", []):
        rm.place(spec)
    doors, props = [], []
    used = set()
    for dr in plan.get("doors", []):
        side, cell = dr["side"], int(dr["cell"])
        wall = WALL[side]
        position = int(CELL * cell + 2)
        fx, fz = rm.door_face_point(side, cell)
        hit = [s for s in rm.find("door", fx, fz) if s["facing_w"] in (side, OPPOSITE[side]) and s["piece"] != DOOR_FRAME]
        if not hit:
            raise PlanError("non-interlocking: door %s (%s cell %d) has no door socket at (%.2f, %.2f); the wall there is "
                            "uncut" % (dr["id"], wall, cell, fx, fz))
        used.add(id(hit[0]))
        doors.append({"id": dr["id"], "wall": wall, "position": position, "to_room": dr["to_room"], "to_door": dr["to_door"],
                      "label": dr["label"], "conditions": dr.get("conditions", [])})
        rm.tris += int(piece_info(DOOR_FRAME)["tris"] or 0)
    for s in rm.sockets:
        if s["type"] == "door" and s.get("needs") == "arch.door" and id(s) not in used:
            raise PlanError("non-interlocking: %s has a cut door socket at (%.2f, %.2f) with no door declared there" % (
                s["piece"], s["at"][0], s["at"][2]))
    # state-pair sockets carry their piece (optionally flag-swapped)
    for s in list(rm.sockets):
        if s["type"] in STATE_PIECES:
            want = plan.get("states", {}).get(s["type"], {})
            key = want.get("asset", STATE_PIECES[s["type"]])
            if key.split("__")[0] != STATE_PIECES[s["type"]]:
                raise PlanError("%s socket takes %s, not %s" % (s["type"], STATE_PIECES[s["type"]], key))
            extra = {}
            if want.get("when"):
                piece_info(want["when"]["asset"])
                extra = {"flag": want["when"]["flag"], "asset_when_set": want["when"]["asset"]}
            rm.add(key, s["at"][0], s["at"][2], FACE_IN_YAW[OPPOSITE[s["facing_w"]]] if s["facing_w"] in VEC else 0.0,
                   y=s["at"][1], kind="insert", extra=extra)
    # torch / lantern / hearth sockets get their mount; wall mounts on named wall sockets
    for s in list(rm.sockets):
        if s["type"] in MOUNTS and s.get("piece") != MOUNTS[s["type"]]:
            rm.add(plan.get("mounts", {}).get(s["type"], MOUNTS[s["type"]]), s["at"][0], s["at"][2], FACE_IN_YAW[s["facing_w"]], mounted=True)
    for m in plan.get("wall", []):
        side, cell = m["socket"][0], int(m["socket"][1:])
        hit = [s for s in rm.sockets if s["type"] in ("wall", "window") and s["facing_w"] == side and s.get("cell") == cell
               and s["type"] == m.get("on", "wall")]
        if not hit:
            raise PlanError("wall mount %s: no %s socket %s" % (m["key"], m.get("on", "wall"), m["socket"]))
        s = hit[0]
        rm.add(m["key"], s["at"][0], s["at"][2], FACE_IN_YAW[side], mounted=True)
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
            "props": props, "character_ids": [plan.get("protagonist", "wayfarer")] + sorted(plan.get("characters", {}))}
    pres = {"exterior": bool(plan.get("exterior", False)), "kit_shell": True, "floor": "",
            "look_profile": plan.get("look_profile", "village"), "wall_height": plan.get("wall_height", 4.5),
            "camera": "game", "cameras": [dict(cam, id="game")], "pieces": rm.pieces}
    if plan.get("characters"):
        pres["characters"] = plan["characters"]
    if plan.get("interactions"):
        pres["interactions"] = plan["interactions"]
    report = {"id": plan["id"], "plot_m": [rm.w, rm.d], "pieces": len(rm.pieces), "kit_tris": rm.tris, "people": people,
              "tri_estimate": est, "tri_cap": TRI_CAP,
              "sockets": {k: sum(1 for s in rm.sockets if s["type"] == k) for k in sorted({s["type"] for s in rm.sockets})},
              "checks": ["doors on door sockets", "every arch.door socket used", "state-pair sockets filled",
                         "torch / lantern / hearth sockets mounted", "grid pieces snapped", "tri estimate <= cap"]}
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
