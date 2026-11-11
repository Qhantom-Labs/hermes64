"""Place archetypes -> room plans (PLACEMAKER). "Make this type of place" without hand-laying every piece.

An archetype (kits/places/<id>.json, contract contracts/place/1.0.0.json, format hermes64-place/1) is DATA: footprint
options with a socket-checked kit skeleton (shell / ground / door pieces in the kit compiler's own plan syntax), zones
(entrance, path, focal, fight floor, nooks), prop groups by catalog TAG with a placement rule, count range, spacing and
height tier, lighting / look profile, default mood, texture roles, door / spawn conventions and a clearance rule.

make_plan(archetype, params) is a deterministic, seeded placement grammar. Its output is a NORMAL room plan for the
kit's existing compiler (tools.medievalkit_rooms / westernkit_rooms / cyberkit_rooms); compile() runs that compiler
and static_checks() runs the arena clearance / reachability check (tools.room_clearance) plus layout numbers.

  python3 -B -m adventure_maker.place list
  python3 -B -m adventure_maker.place plan wizard_tower_interior --seed 3 --size small --clutter 2 [--mood purple_dusk]
  python3 -B -m adventure_maker.place check wizard_tower_interior --seed 3

Refusals are PlaceError with one plain line. Nothing here renders, writes files or names a story.
"""
import contextlib
import glob
import hashlib
import importlib
import json
import math
import random
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
PLACES_DIR = R / "kits" / "places"
FORMAT = "hermes64-place/1"
PLAN_FORMAT = "hermes64-place-plan/1"
KITS = {"medieval": ("tools.medievalkit_rooms", "medievalkit"), "western": ("tools.westernkit_rooms", "westernkit"),
        "cyber": ("tools.cyberkit_rooms", "cyberkit")}
RULES = ("focal-point", "centre", "against-wall", "wall-mount", "flanking-door", "flanking-focal", "along-path",
         "on-path", "ring-focal", "cluster", "scatter", "perimeter", "ceiling", "on-top", "frontage-row")
TIERS = ("floor", "table", "wall", "ceiling", "lot")
SIZES = ("small", "medium", "large")
CLUTTER_MAX = 3
PERSON_TRIS, TRI_CAP = 760, 6000
FLAT_M = 0.12                         # room_clearance: lower pieces never block
GAP_M = 0.12                          # air between neighbours
PROTAGONIST = "pilgrim"               # the cyber compiler's fixed protagonist id; used for every kit so specs agree
MOODS_BASE = "base"


class PlaceError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------- data access
_CACHE = {}


def _json(path):
    path = str(path)
    if path not in _CACHE:
        _CACHE[path] = json.loads(Path(path).read_text(encoding='utf-8'))
    return _CACHE[path]


def manifest():
    """Every kit piece key (presets included) -> (kit file stem, socket row)."""
    if "manifest" not in _CACHE:
        out = {}
        for f in sorted(glob.glob(str(R / "kits" / "library" / "*-sockets.json"))):
            stem = Path(f).name.split("-")[0]
            for k, v in json.loads(Path(f).read_text(encoding='utf-8'))["pieces"].items():
                out.setdefault(k, (stem, v))
        _CACHE["manifest"] = out
    return _CACHE["manifest"]


def tags():
    return _json(R / "catalog" / "tags.json")


def tag_rows():
    if "tag_rows" not in _CACHE:
        _CACHE["tag_rows"] = {r["id"]: r for r in tags()["rows"]}
    return _CACHE["tag_rows"]


def vocabulary_kinds():
    return set(tags()["vocabulary"]["kinds"])


def bindings(pack):
    p = R / "packs" / pack / "bindings.json"
    if not p.is_file():
        raise PlaceError("pack %r has no bindings (packs/%s/bindings.json); install or pick a shipped pack" % (pack, pack))
    return _json(p)["assets"]


def glb_for_key(key, pack=None):
    """A built GLB for a key: the pack's own, else any shipped pack's (geometry is the same across packs)."""
    if pack:
        row = bindings(pack).get(key)
        if row:
            return R / row["glb"]
    if "glb_index" not in _CACHE:
        idx = {}
        for f in sorted(glob.glob(str(R / "packs" / "*" / "bindings.json"))):
            for k, row in json.loads(Path(f).read_text(encoding='utf-8')).get("assets", {}).items():
                idx.setdefault(k, R / row["glb"])
        _CACHE["glb_index"] = idx
    p = _CACHE["glb_index"].get(key)
    if p is None or not Path(p).is_file():
        raise PlaceError("no built GLB for %s in any shipped pack (its size is unknown, so it cannot be placed)" % key)
    return p


def bounds(key, pack=None):
    from tools.room_clearance import glb_bounds
    return glb_bounds(glb_for_key(key, pack))


def list_archetypes():
    return sorted(Path(f).stem for f in glob.glob(str(PLACES_DIR / "*.json")))


def load_archetype(name):
    if isinstance(name, dict):
        return name
    p = PLACES_DIR / ("%s.json" % name)
    if not p.is_file():
        raise PlaceError("unknown place archetype %r (have: %s)" % (name, ", ".join(list_archetypes())))
    return json.loads(p.read_text(encoding='utf-8'))


# ----------------------------------------------------------------------------------------------- validation
REQUIRED = ("format", "id", "name", "description", "kit", "base_pack", "look_profile", "exterior", "default_mood",
            "moods", "footprints", "zones", "groups", "lighting", "texture_roles", "spawn", "clearance", "params")


def validate(doc):
    """Raise PlaceError (one line) if the archetype is malformed. Returns the doc."""
    if not isinstance(doc, dict):
        raise PlaceError("archetype must be a JSON object")
    for k in REQUIRED:
        if k not in doc:
            raise PlaceError("archetype %s: missing field %r" % (doc.get("id", "?"), k))
    aid = doc["id"]
    if doc["format"] != FORMAT:
        raise PlaceError("archetype %s: format must be %s" % (aid, FORMAT))
    if doc["kit"] not in KITS:
        raise PlaceError("archetype %s: kit %r is not one of %s" % (aid, doc["kit"], ", ".join(KITS)))
    unknown = sorted(set(doc) - set(REQUIRED) - {"genres", "wants", "notes", "max_coverage"})
    if unknown:
        raise PlaceError("archetype %s: unknown field %r" % (aid, unknown[0]))
    if not doc["footprints"]:
        raise PlaceError("archetype %s: needs at least one footprint" % aid)
    for fp in doc["footprints"]:
        for k in ("size", "plot_cells", "skeleton", "floor_rect_m", "doors", "entrance", "focal_m", "min_clear_m"):
            if k not in fp:
                raise PlaceError("archetype %s footprint %s: missing %r" % (aid, fp.get("size", "?"), k))
        if fp["size"] not in SIZES:
            raise PlaceError("archetype %s: footprint size %r is not one of %s" % (aid, fp["size"], "/".join(SIZES)))
    if doc["default_mood"] not in doc["moods"]:
        raise PlaceError("archetype %s: default_mood %r is not in its moods" % (aid, doc["default_mood"]))
    kinds = vocabulary_kinds()
    man = manifest()
    ids = set()
    for g in doc["groups"]:
        gid = g.get("id", "?")
        if gid in ids:
            raise PlaceError("archetype %s: duplicate group %r" % (aid, gid))
        ids.add(gid)
        if g.get("rule") not in RULES:
            raise PlaceError("archetype %s group %s: rule %r is not one of %s" % (aid, gid, g.get("rule"), ", ".join(RULES)))
        if g.get("tier", "floor") not in TIERS:
            raise PlaceError("archetype %s group %s: tier %r is not one of %s" % (aid, gid, g.get("tier"), ", ".join(TIERS)))
        cnt = g.get("count")
        if not (isinstance(cnt, list) and len(cnt) == 2 and 0 <= cnt[0] <= cnt[1] <= 64):
            raise PlaceError("archetype %s group %s: count must be [min, max] with 0 <= min <= max <= 64" % (aid, gid))
        tag = g.get("tag") or {}
        words = tag.get("kind") or []
        words = [words] if isinstance(words, str) else words
        if not words and not tag.get("keys"):
            raise PlaceError("archetype %s group %s: tag needs kind words or keys" % (aid, gid))
        for w in words:
            if w not in kinds:
                from adventure_maker import taxonomy
                near = [k for k in sorted(kinds) if k[:3] == w[:3]][:3]
                raise PlaceError("archetype %s group %s: unknown tag %r (not in catalog/tags.json kinds%s)" % (
                    aid, gid, w, "; nearest: " + ", ".join(near) if near else ""))
        for k in tag.get("keys", []) + g.get("prefer", []):
            if k not in man:
                raise PlaceError("archetype %s group %s: %s is not a kit piece" % (aid, gid, k))
        if g["rule"] == "on-top" and g.get("on") not in ids:
            raise PlaceError("archetype %s group %s: on-top needs 'on' = an earlier group id" % (aid, gid))
    return doc


# ----------------------------------------------------------------------------------------------- params
def resolve_params(doc, params):
    p = dict(params or {})
    unknown = sorted(set(p) - {"size", "mood", "clutter", "seed", "light", "contrast", "spacing", "camera_pull", "wants"})
    if unknown:
        raise PlaceError("unknown parameter %r (size, mood, clutter, seed, light, contrast, spacing, camera_pull, wants)" % unknown[0])
    sizes = [f["size"] for f in doc["footprints"]]
    size = p.get("size") or doc["params"].get("size") or sizes[0]
    if size not in sizes:
        raise PlaceError("%s has no %r footprint (have: %s)" % (doc["id"], size, ", ".join(sizes)))
    clutter = p.get("clutter", doc["params"].get("clutter", 1))
    if not isinstance(clutter, int) or isinstance(clutter, bool) or not 0 <= clutter <= CLUTTER_MAX:
        raise PlaceError("clutter must be a whole number 0-%d, got %r" % (CLUTTER_MAX, clutter))
    seed = p.get("seed", 1)
    if not isinstance(seed, int) or isinstance(seed, bool) or not 0 <= seed < 2 ** 31:
        raise PlaceError("seed must be a whole number 0..2^31-1, got %r" % (seed,))
    mood = p.get("mood") or doc["default_mood"]
    if mood not in doc["moods"]:
        raise PlaceError("mood %r is not offered by %s (offered: %s)" % (mood, doc["id"], ", ".join(sorted(doc["moods"]))))
    light = float(p.get("light", 1.0))
    if not 0.85 <= light <= 1.15:
        raise PlaceError("light must be 0.85-1.15 (bounded; the look profile sets the light), got %s" % light)
    contrast = float(p.get("contrast", 0.0))
    if not 0.0 <= contrast <= 0.2:
        raise PlaceError("contrast must be 0-0.2 (ambient energy down, key up by that share), got %s" % contrast)
    spacing = float(p.get("spacing", 1.0))
    if not 1.0 <= spacing <= 1.6:
        raise PlaceError("spacing must be 1.0-1.6, got %s" % spacing)
    pull = float(p.get("camera_pull", 0.0))
    if not 0.0 <= pull <= 0.3:
        raise PlaceError("camera_pull must be 0-0.3, got %s" % pull)
    wants = [str(w) for w in p.get("wants", [])][:12]
    return {"size": size, "mood": mood, "clutter": clutter, "seed": seed, "light": round(light, 3),
            "contrast": round(contrast, 3),
            "spacing": round(spacing, 3), "camera_pull": round(pull, 3), "wants": wants}


def mood_pack(doc, mood):
    """(pack id, how): 'base' -> the archetype's base pack; a hand pack name; or a derived <base>_<mood> id."""
    m = doc["moods"][mood]
    if m == MOODS_BASE or mood == MOODS_BASE:
        return doc["base_pack"], "base"
    if m.startswith("pack:"):
        return m[5:], "hand"
    if m == "derive":
        return "%s_%s" % (doc["base_pack"], mood), "derive"
    raise PlaceError("%s mood %s: value must be 'base', 'derive' or 'pack:<id>'" % (doc["id"], mood))


def check_mood(doc, mood):
    """Off-palette guard: a derived mood must exist in the mood list and pass derive_checked for the base pack."""
    pack, how = mood_pack(doc, mood)
    if how != "derive":
        if how == "hand":
            bindings(pack)
        return {"pack": pack, "how": how}
    if str(R) not in sys.path:
        sys.path.insert(0, str(R))
    if str(R / "kits") not in sys.path:
        sys.path.append(str(R / "kits"))          # after R: kits/tools must not shadow the repo's tools package
    from core import mood as moodlib
    if mood not in moodlib.MOODS:
        raise PlaceError("mood %r is not in the mood list (kits/core/mood.py MOODS)" % mood)
    key = ("mood_check", doc["base_pack"], mood)
    if key not in _CACHE:
        from tools import mood_pack as mp
        try:
            derived, _sp, _view, rep = mp.derive_all(doc["base_pack"], mood, textures=False)
            _CACHE[key] = {"pack": pack, "how": how, "strength": rep.get("strength"), "clamped": rep.get("clamped")}
        except (Exception, SystemExit) as e:      # derive_checked refuses with a reason; keep it one line
            msg = str(e).splitlines()[0] if str(e) else type(e).__name__
            if msg.startswith("REFUSED: "):
                msg = msg.split(": ", 2)[-1]
            _CACHE[key] = {"error": msg[:200]}
    res = _CACHE[key]
    if "error" in res:
        raise PlaceError("mood %s refused for %s: %s" % (mood, doc["base_pack"], res["error"]))
    return res


# ----------------------------------------------------------------------------------------------- tag -> pieces
def _anchor_ok(anchor, rule):
    if rule == "wall-mount":
        return anchor == "wall_face"
    if rule == "ceiling":
        return anchor in ("ceiling_hook", "free")
    if rule == "frontage-row":
        return anchor == "lot_line"
    return anchor == "free"


def _preset_ok(key, pack):
    """A recipe builds in the target pack only if its preset (the part after '__') is one of that pack's kit_presets."""
    gid, _, pre = key.partition("__")
    if not pre:
        return True
    p = R / "kits" / "packs" / pack / "pack.json"
    return p.is_file() and pre in _json(p).get("kit_presets", {}).get(gid, {})


def candidates(doc, group, pack):
    """Ordered [(key, source)] for a group: source 'kit' (built in the pack) or 'recipe' (a registered generator the
    render step builds into the pack). Foreign pieces only where the kit compiler accepts them (not cyber)."""
    man = manifest()
    built = bindings(pack)
    tag = group.get("tag") or {}
    words = tag.get("kind") or []
    words = [words] if isinstance(words, str) else words
    rows = tag_rows()
    own = KITS[doc["kit"]][1]
    keys = list(tag.get("keys", []))
    if words:
        for k in sorted(man):
            row = rows.get(k.split("__")[0])
            if not row or not set(words) & set(row.get("kind", [])):
                continue
            if tag.get("place") and tag["place"] not in row.get("place", []):
                continue
            keys.append(k)
    out, seen = [], set()
    avoid = set(group.get("avoid", []))
    order = list(group.get("prefer", [])) + keys
    for k in order:
        if k in seen or k in avoid or k not in man:
            continue
        seen.add(k)
        stem, info = man[k]
        if not _anchor_ok(info.get("anchor"), group["rule"]):
            continue
        if group["rule"] == "frontage-row" and any(s["type"] == "door" for s in info["sockets"]):
            continue                      # a door socket needs a declared door: rows use closed frontages
        if k in built:
            src = "kit"
        elif stem != own and doc["kit"] == "cyber":
            continue
        elif rows.get(k.split("__")[0], {}).get("source") == "generator" and _preset_ok(k, pack):
            src = "recipe"
        else:
            continue
        try:
            glb_for_key(k, pack)          # its size must be measurable from a built GLB
        except PlaceError:
            continue
        out.append((k, src))
    pref = set(group.get("prefer", []))
    out.sort(key=lambda t: (0 if t[0] in pref else 1, 0 if t[1] == "kit" else 1))
    if pref:     # keep author order inside the preferred block
        head = [t for k in group.get("prefer", []) for t in out if t[0] == k]
        out = head + [t for t in out if t[0] not in pref]
    return out


def gap_rows(words, brief=None):
    from adventure_maker import taxonomy
    return [taxonomy.gap_row(w) for w in words]


# ----------------------------------------------------------------------------------------------- geometry
def _r3(v):
    return round(float(v) + 0.0, 3)


def face_yaw(dx, dz):
    """Yaw (degrees) that turns a piece's +z front toward (dx, dz) (room_clearance / compiler rotation)."""
    return _r3(math.degrees(math.atan2(dx, dz)))


def rect_of(key, x, z, yaw, pack):
    from tools.room_clearance import footprint
    return footprint({"position": [x, 0, z], "yaw": yaw}, bounds(key, pack))


def _overlap(a, b, pad=0.0):
    return a[0] - pad < b[2] and b[0] - pad < a[2] and a[1] - pad < b[3] and b[1] - pad < a[3]


def _inside(r, box, margin=0.0):
    return r[0] >= box[0] + margin and r[1] >= box[1] + margin and r[2] <= box[2] - margin and r[3] <= box[3] - margin


def _seg_dist(px, pz, a, b):
    ax, az = a
    bx, bz = b
    vx, vz = bx - ax, bz - az
    L2 = vx * vx + vz * vz
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (pz - az) * vz) / L2))
    return math.hypot(px - (ax + t * vx), pz - (az + t * vz))


def _rect_path_dist(r, path):
    """Smallest distance from a rect to a polyline (sampled on the rect outline + centre)."""
    pts = [(r[0], r[1]), (r[2], r[1]), (r[0], r[3]), (r[2], r[3]), ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2),
           ((r[0] + r[2]) / 2, r[1]), ((r[0] + r[2]) / 2, r[3]), (r[0], (r[1] + r[3]) / 2), (r[2], (r[1] + r[3]) / 2)]
    best = 1e9
    for p in pts:
        for a, b in zip(path, path[1:]):
            best = min(best, _seg_dist(p[0], p[1], a, b))
    # a rect straddling the line: check the line crosses it
    for a, b in zip(path, path[1:]):
        for t in [i / 20 for i in range(21)]:
            x, z = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if r[0] <= x <= r[2] and r[1] <= z <= r[3]:
                return 0.0
    return best


WALL_NORMAL = {"n": (0.0, 1.0), "s": (0.0, -1.0), "w": (1.0, 0.0), "e": (-1.0, 0.0)}     # inward


def door_point(fp, door):
    """Inner door point (on the floor rect edge) of a footprint door row {side, at_m}."""
    x0, z0, x1, z1 = fp["floor_rect_m"]
    side, a = door["side"], float(door["at_m"])
    return {"n": (a, z0), "s": (a, z1), "w": (x0, a), "e": (x1, a)}[side]


# ----------------------------------------------------------------------------------------------- the grammar
class _Layout:
    def __init__(self, doc, fp, params, pack):
        self.doc, self.fp, self.params, self.pack = doc, fp, params, pack
        self.F = tuple(fp["floor_rect_m"])
        self.solids = []       # (rect, key, group)
        self.flats = []
        self.rows = []         # placements
        self.wall_used = set()
        self.tris = 0
        self.trims, self.short = [], []
        z = doc["zones"]
        ent = fp["entrance"]
        self.entrance = door_point(fp, ent)
        nx, nz = WALL_NORMAL[ent["side"]]
        self.ent_dir = (nx, nz)
        self.focal = tuple(fp["focal_m"])
        path_w = float(fp.get("path_width_m", z.get("path_width_m", 1.6)))
        self.path_half = path_w / 2.0
        start = (self.entrance[0] + nx * 0.6, self.entrance[1] + nz * 0.6)
        self.path = [start] + [tuple(p) for p in fp.get("path_via_m", [])] + [self.focal_front()]
        ed = float(z.get("entrance_depth_m", 2.0))
        ew = float(z.get("entrance_width_m", 2.4))
        ex, ez = self.entrance
        if ent["side"] in "ns":
            zz = (ez, ez + ed) if ent["side"] == "n" else (ez - ed, ez)
            self.entrance_rect = (ex - ew / 2, zz[0], ex + ew / 2, zz[1])
        else:
            xx = (ex, ex + ed) if ent["side"] == "w" else (ex - ed, ex)
            self.entrance_rect = (xx[0], ez - ew / 2, xx[1], ez + ew / 2)
        self.door_rects = [self.entrance_rect]
        for d in fp["doors"]:
            if d is ent or d.get("id") == ent.get("id"):
                continue
            px, pz = door_point(fp, d)
            dnx, dnz = WALL_NORMAL[d["side"]]
            r = (min(px, px + dnx * ed) - (ew / 2 if d["side"] in "ns" else 0), min(pz, pz + dnz * ed) - (ew / 2 if d["side"] in "we" else 0),
                 max(px, px + dnx * ed) + (ew / 2 if d["side"] in "ns" else 0), max(pz, pz + dnz * ed) + (ew / 2 if d["side"] in "we" else 0))
            self.door_rects.append(r)
        fc = fp.get("fight_m") or [(self.F[0] + self.F[2]) / 2, (self.F[1] + self.F[3]) / 2]
        fs = float(fp.get("fight_clear_m", z.get("fight_clear_m", 0.0)))
        self.fight_rect = (fc[0] - fs / 2, fc[1] - fs / 2, fc[0] + fs / 2, fc[1] + fs / 2) if fs > 0 else None
        nk = float(z.get("nook_m", 2.6))
        x0, z0, x1, z1 = tuple(fp.get("place_rect_m", self.F)) if doc["exterior"] else self.F
        self.nooks = {"nw": (x0, z0, x0 + nk, z0 + nk), "ne": (x1 - nk, z0, x1, z0 + nk),
                      "sw": (x0, z1 - nk, x0 + nk, z1), "se": (x1 - nk, z1 - nk, x1, z1)}
        man = manifest()
        skel_tris = sum(int(man[p["key"]][1]["tris"] or 0) for p in fp["skeleton"] if p["key"] in man)
        people = 1
        overhead = int(doc["clearance"].get("overhead_tris", 120))
        self.budget = TRI_CAP - skel_tris - people * PERSON_TRIS - overhead - int(doc["clearance"].get("reserve_tris", 300))
        self.skel_tris = skel_tris

    def focal_front(self):
        fx, fz = self.focal
        ex, ez = self.entrance
        d = math.hypot(ex - fx, ez - fz) or 1.0
        reach = float(self.fp.get("focal_reach_m", 1.6))
        return (_r3(fx + (ex - fx) / d * reach), _r3(fz + (ez - fz) / d * reach))

    def zone_of(self, x, z):
        if _overlap((x, z, x, z), self.entrance_rect):
            return "entrance"
        if math.hypot(x - self.focal[0], z - self.focal[1]) <= float(self.fp.get("focal_reach_m", 1.6)) + 0.4:
            return "focal"
        if any(_seg_dist(x, z, a, b) <= self.path_half for a, b in zip(self.path, self.path[1:])):
            return "path"
        if self.fight_rect and _overlap((x, z, x, z), self.fight_rect):
            return "fight"
        if any(_overlap((x, z, x, z), r) for r in self.nooks.values()):
            return "nook"
        return "open"

    def fits(self, key, x, z, yaw, group, allow=()):
        r = rect_of(key, x, z, yaw, self.pack)
        b = bounds(key, self.pack)
        flat = (b[4] - b[1]) < FLAT_M
        margin = float(group.get("wall_gap_m", 0.05))
        box = self.F if not self.doc["exterior"] else tuple(self.fp.get("place_rect_m", self.F))
        if group.get("area") == "walk":
            box = tuple(self.fp.get("walk_rect_m", self.F))
        if group.get("rule") == "perimeter":
            box = tuple(self.fp.get("perimeter_rect_m", box))
        if group.get("inside", True) and not _inside(r, box, margin):
            return None, "outside"
        if group.get("keep_from_entrance_m") and math.hypot(x - self.entrance[0], z - self.entrance[1]) < float(
                group["keep_from_entrance_m"]):
            return None, "near entrance"            # e.g. light sources glaring into the entrance camera
        pad = float(group.get("spacing_m", 0.4)) * self.params["spacing"] / 2.0
        pool = self.flats if flat else self.solids
        for o, _k, _g in pool:
            if _overlap(r, o, max(pad, GAP_M)):
                return None, "overlap"
        if not flat:
            for dr in self.door_rects:
                if "entrance" not in allow and _overlap(r, dr, 0.1):
                    return None, "door zone"
            if "path" not in allow and _rect_path_dist(r, self.path) < self.path_half + 0.05:
                return None, "path"
            if self.fight_rect and "fight" not in allow and _overlap(r, self.fight_rect):
                return None, "fight floor"
        return (r, flat), None

    def add(self, key, src, x, z, yaw, group, y=0.0, mounted=False, extra=None, fit=None):
        man = manifest()
        tris = int(man[key][1]["tris"] or 0)
        if self.tris + tris > self.budget:
            self.trims.append({"group": group["id"], "key": key, "why": "triangle budget"})
            return False
        if fit is not None:
            r, flat = fit
            (self.flats if flat else self.solids).append((r, key, group["id"]))
        self.tris += tris
        row = {"group": group["id"], "key": key, "source": src, "at_m": [_r3(x), _r3(z)], "yaw": _r3(yaw),
               "y": _r3(y), "tier": group.get("tier", "floor"), "zone": self.zone_of(x, z)}
        if mounted:
            row["mounted"] = True
        if extra:
            row.update(extra)
        self.rows.append(row)
        return True


def _count(group, clutter):
    lo, hi = group["count"]
    return lo + int(round((hi - lo) * clutter / float(CLUTTER_MAX)))


def _pick(rng, cands, group):
    n = max(1, min(len(cands), int(group.get("variety", 1))))
    return cands[rng.randrange(n)] if n > 1 else cands[0]


def _seed_int(*parts):
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:12], 16)


def _place_group(L, group, cands, rng):
    rule = group["rule"]
    n = _count(group, L.params["clutter"])
    if n == 0:
        return 0
    placed = 0
    F = L.F
    sp = float(group.get("spacing_m", 0.6)) * L.params["spacing"]

    def try_at(key, src, x, z, yaw, allow=(), y=0.0, mounted=False, extra=None):
        fit, why = L.fits(key, x, z, yaw, group, allow) if not mounted else ((None, True), None)
        if fit is None:
            return False
        return L.add(key, src, x, z, yaw, group, y=y, mounted=mounted, extra=extra, fit=None if mounted else fit)

    def depth_of(key, yaw=0.0):
        b = bounds(key, L.pack)
        return (b[5] - b[2]), (b[3] - b[0])       # depth (local z), width (local x)

    if rule in ("focal-point", "centre"):
        x, z = L.focal if rule == "focal-point" else ((F[0] + F[2]) / 2, (F[1] + F[3]) / 2)
        ex, ez = L.entrance
        yaw = face_yaw(ex - x, ez - z) if group.get("face", "entrance") == "entrance" else float(group.get("yaw", 0))
        if group.get("snap90", True):
            yaw = _r3(round(yaw / 90.0) * 90.0)
        for key, src in cands[:max(1, int(group.get("variety", 1)))]:
            if try_at(key, src, x, z, yaw, allow=("path", "fight", "entrance"), extra={"landmark": True}):
                return 1
        return 0
    if rule == "ring-focal":
        fx, fz = L.focal
        rad = float(group.get("radius_m", 1.8))
        phase = rng.random() * 360.0
        for i in range(n * 3):
            if placed >= n:
                break
            a = math.radians(phase + 360.0 * i / max(n, 1) + (i // n) * 17.0)
            x, z = fx + rad * math.sin(a), fz + rad * math.cos(a)
            key, src = _pick(rng, cands, group)
            yaw = face_yaw(fx - x, fz - z)
            if try_at(key, src, x, z, yaw, allow=("path", "fight")):
                placed += 1
        return placed
    if rule in ("flanking-door", "flanking-focal"):
        if rule == "flanking-door":
            cx, cz = L.entrance
            nx, nz = L.ent_dir
            depth = float(group.get("depth_m", 1.4))
            cx, cz = cx + nx * depth, cz + nz * depth
        else:
            cx, cz = L.focal
            nx, nz = L.ent_dir
        tx, tz = -nz, nx                          # lateral axis
        lat = float(group.get("lateral_m", 2.0))
        key, src = _pick(rng, cands, group)
        pairs = max(1, n // 2)
        for k in range(pairs):
            ok = 0
            for s in (-1, 1):
                x, z = cx + tx * s * (lat + k * sp), cz + tz * s * (lat + k * sp)
                yaw = face_yaw(-nx, -nz) if rule == "flanking-focal" else face_yaw(nx, nz)
                for turn in (0.0, 180.0, 90.0, -90.0):        # off-centre pieces: first yaw that fits
                    if try_at(key, src, x, z, _r3(((yaw + turn + 180.0) % 360.0) - 180.0),
                              allow=("path",) if rule == "flanking-focal" else ()):
                        ok += 1
                        break
            placed += ok
        return placed
    if rule == "along-path":
        key, src = _pick(rng, cands, group)
        d0, w0 = depth_of(key)
        lat = L.path_half + max(d0, w0) / 2.0 + float(group.get("lateral_extra_m", 0.3))
        segs = list(zip(L.path, L.path[1:]))
        total = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs) or 1.0
        pairs = max(1, n // 2)
        step = total / (pairs + 1)
        for k in range(1, pairs + 1):
            t, acc = k * step, 0.0
            a, b = segs[-1]
            px, pz, dx, dz = b[0], b[1], 0.0, 1.0
            for a, b in segs:
                L_ = math.hypot(b[0] - a[0], b[1] - a[1])
                if acc + L_ >= t:
                    u = (t - acc) / (L_ or 1)
                    px, pz = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
                    dx, dz = (b[0] - a[0]) / (L_ or 1), (b[1] - a[1]) / (L_ or 1)
                    break
                acc += L_
            for s in (-1, 1):
                x, z = px - dz * s * lat, pz + dx * s * lat
                if try_at(key, src, x, z, face_yaw(dz * s, -dx * s)):
                    placed += 1
        return placed
    if rule == "on-path":
        key, src = _pick(rng, cands, group)
        b = bounds(key, L.pack)
        if (b[4] - b[1]) >= FLAT_M:
            L.short.append({"group": group["id"], "why": "on-path pieces must be flat (< %.2f m); %s is not" % (FLAT_M, key)})
            return 0
        a, c = L.path[0], L.path[-1]
        x, z = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
        yaw = face_yaw(c[0] - a[0], c[1] - a[1])
        yaw = _r3(round(yaw / 90.0) * 90.0)
        return 1 if try_at(key, src, x, z, yaw, allow=("path", "fight", "entrance")) else 0
    if rule == "against-wall":
        walls = group.get("walls", ["n", "s", "e", "w"])
        slots = []
        x0, z0, x1, z1 = F
        for side in walls:
            for key, src in cands[:max(1, int(group.get("variety", 1)))]:
                d0, w0 = depth_of(key)
                off = d0 / 2.0 + float(group.get("wall_gap_m", 0.08)) + 0.02
                nx, nz = WALL_NORMAL[side]
                along = (x0 + w0 / 2 + 0.1, x1 - w0 / 2 - 0.1) if side in "ns" else (z0 + w0 / 2 + 0.1, z1 - w0 / 2 - 0.1)
                stp = max(w0 + sp, 0.5)
                a = along[0]
                while a <= along[1] + 1e-6:
                    if side in "ns":
                        x, z = a, (z0 + off if side == "n" else z1 - off)
                    else:
                        x, z = (x0 + off if side == "w" else x1 - off), a
                    slots.append((side, key, src, _r3(x), _r3(z), face_yaw(nx, nz)))
                    a += stp
        rng.shuffle(slots)
        for side, key, src, x, z, yaw in slots:
            if placed >= n:
                break
            if try_at(key, src, x, z, yaw):
                placed += 1
        return placed
    if rule == "wall-mount":
        socks = sorted(s for s in L.fp.get("wall_sockets", {}) if s not in L.wall_used and s[0] in group.get("walls", "nsew"))
        rng.shuffle(socks)
        for s in socks:
            if placed >= n:
                break
            key, src = _pick(rng, cands, group)
            x, z = L.fp["wall_sockets"][s]
            nx, nz = WALL_NORMAL[s[0]]
            # floor in front of a wall mount stays free of against-wall furniture (no table through a shelf)
            res_r = (x - 0.9, z - 0.9, x + 0.9, z + 0.9)
            if any(_overlap(res_r, o) for o, _k, g in L.solids if g not in ("skeleton", "wallmount")):
                continue                           # a floor piece already stands in front of this socket
            if L.doc["kit"] == "medieval":
                ok = L.add(key, src, x, z, face_yaw(nx, nz), group, mounted=True, extra={"socket": s})
            else:                                  # free metres on the wall line, mounted
                ok = L.add(key, src, x + nx * 0.12, z + nz * 0.12, face_yaw(nx, nz), group,
                           y=float(group.get("mount_y", 2.4)), mounted=True)
            L.wall_used.add(s)
            if ok:
                L.solids.append((res_r, "reserved:" + s, "wallmount"))
                placed += 1
        return placed
    if rule == "ceiling":
        y = float(group.get("mount_y", L.fp.get("ceiling_y", 4.0)))
        pts = [L.focal_front()] + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(L.path, L.path[1:])]
        for (x, z) in pts:
            if placed >= n:
                break
            key, src = _pick(rng, cands, group)
            if L.add(key, src, x, z, 0.0, group, y=y, mounted=True):
                placed += 1
        return placed
    if rule == "on-top":
        hosts = [r for r in L.rows if r["group"] == group["on"]]
        rng.shuffle(hosts)
        for h in hosts:
            if placed >= n:
                break
            hb = bounds(h["key"], L.pack)
            key, src = _pick(rng, cands, group)
            ox = 0.0 if group.get("centred") else (rng.random() - 0.5) * 0.4 * (hb[3] - hb[0])
            ang = math.radians(h["yaw"])
            x = h["at_m"][0] + ox * math.cos(ang)
            z = h["at_m"][1] - ox * math.sin(ang)
            if L.add(key, src, x, z, h["yaw"], group, y=h["y"] + hb[4], mounted=True):
                placed += 1
        return placed
    if rule in ("cluster", "scatter", "perimeter"):
        if rule == "cluster":
            names = group.get("nooks") or sorted(L.nooks)
            names = list(names)
            rng.shuffle(names)
            areas = [L.nooks[k] for k in names[:max(1, int(group.get("clusters", 1)))]]
        elif rule == "perimeter":
            P = tuple(L.fp.get("perimeter_rect_m", F))
            band = float(group.get("band_m", 2.5))
            areas = [(P[0], P[1], P[2], P[1] + band), (P[0], P[3] - band, P[2], P[3]),
                     (P[0], P[1], P[0] + band, P[3]), (P[2] - band, P[1], P[2], P[3])]
        else:
            areas = [tuple(L.fp.get("place_rect_m", F))]
        tries = 0
        while placed < n and tries < 60 * n:
            tries += 1
            a = areas[tries % len(areas)]
            x = a[0] + rng.random() * (a[2] - a[0])
            z = a[1] + rng.random() * (a[3] - a[1])
            key, src = _pick(rng, cands, group)
            yaw = face_yaw(L.focal[0] - x, L.focal[1] - z) if group.get("face") == "focal" else _r3(rng.random() * 360.0 - 180.0)
            if group.get("snap90"):
                yaw = _r3(round(yaw / 90.0) * 90.0)
            if try_at(key, src, x, z, yaw):
                placed += 1
        return placed
    raise PlaceError("rule %s not handled" % rule)


def _frontage_rows(L, group, cands, rng):
    """Lot-line buildings filling each declared run (western streets): greedy seeded widths, closed frontages only."""
    man = manifest()
    out = []
    cap = L.tris + L.budget * float(group.get("budget_share", 0.6))
    fill = float(group.get("fill", 1.0))
    for run in L.fp.get("frontage_runs", []):
        side, gy, a, b = run["side"], run["line"], float(run["from"]), float(run["to"])
        pos = a
        while pos < b - 1e-6:
            room_left = b - pos
            fit = [(k, s) for k, s in cands if (man[k][1].get("cells") or [1, 1])[0] <= room_left + 1e-6]
            if not fit:
                break
            k, s = fit[rng.randrange(min(len(fit), max(1, int(group.get("variety", 4)))))]
            w = (man[k][1].get("cells") or [1, 1])[0]
            tris = int(man[k][1]["tris"] or 0)
            if fill < 1.0 and rng.random() > fill:
                pos += 1.0                          # an empty lot (seeded); the street wall keeps a gap
                continue
            if L.tris + tris > min(L.budget, cap):
                L.trims.append({"group": group["id"], "key": k, "why": "triangle budget"})
                break
            L.tris += tris
            out.append({"group": group["id"], "key": k, "source": s, "lot": [pos + w / 2.0, gy, side], "tier": "lot",
                        "zone": "frontage"})
            pos += w
    L.rows.extend(out)
    return len(out)


def make_plan(archetype, params=None):
    """Archetype (id or dict) + params -> result dict with the kit room plan ('plan') and everything the report needs.
    Deterministic: same archetype bytes + params -> same plan bytes."""
    doc = validate(load_archetype(archetype))
    p = resolve_params(doc, params)
    mood = check_mood(doc, p["mood"])
    pack = mood["pack"]
    geo_pack = doc["base_pack"]                          # sizes come from the base build (same geometry in moods)
    fp = next(f for f in doc["footprints"] if f["size"] == p["size"])
    rng = random.Random(_seed_int(doc["id"], p["seed"], p["size"]))
    L = _Layout(doc, fp, p, geo_pack)
    # skeleton solids (non-floor kit pieces inside the room) block placement too
    for sk in fp["skeleton"]:
        for r in sk.get("_solid_m", []):
            L.solids.append((tuple(r), sk["key"], "skeleton"))
    for r in fp.get("blocked_m", []):
        L.solids.append((tuple(r), "blocked", "skeleton"))
    gaps, groups_rep = [], []
    for g in doc["groups"]:
        if g.get("sizes") and p["size"] not in g["sizes"]:
            groups_rep.append({"group": g["id"], "rule": g["rule"], "wanted": 0, "placed": 0, "candidates": [],
                               "skipped": "not used at size %s" % p["size"]})
            continue
        cands = candidates(doc, g, geo_pack)
        want = _count(g, p["clutter"])
        if not cands:
            words = (g.get("tag") or {}).get("kind") or []
            words = [words] if isinstance(words, str) else words
            rows = gap_rows(words or [g["id"]])
            gaps.append({"group": g["id"], "wants": words, "rows": [{"want": r["want"], "status": r["status"],
                         "why": r["why"], "next": r["next"]} for r in rows], "left_out": want})
            groups_rep.append({"group": g["id"], "rule": g["rule"], "wanted": want, "placed": 0, "candidates": []})
            if g.get("required"):
                raise PlaceError("%s: required group %s has no piece for tag %s (gap: %s)" % (
                    doc["id"], g["id"], words, rows[0]["status"] if rows else "missing"))
            continue
        before = len(L.rows)
        if g["rule"] == "frontage-row":
            got = _frontage_rows(L, g, cands, rng)
        else:
            got = _place_group(L, g, cands, rng)
        if g.get("required") and got < max(1, g["count"][0]):
            why = [t["why"] for t in L.trims if t["group"] == g["id"]]
            raise PlaceError("%s: required group %s placed %d of %d (%s)" % (
                doc["id"], g["id"], got, max(1, g["count"][0]), "over budget" if why else "no free spot"))
        groups_rep.append({"group": g["id"], "rule": g["rule"], "wanted": want if g["rule"] != "frontage-row" else None,
                           "placed": len(L.rows) - before, "candidates": [k for k, _ in cands[:6]]})
        if g["rule"] != "frontage-row" and len(L.rows) - before < want:
            L.short.append({"group": g["id"], "wanted": want, "placed": len(L.rows) - before})
    wants = list(doc.get("wants", [])) + p["wants"]
    want_rows = [{"want": r["want"], "status": r["status"], "why": r["why"], "next": r["next"]} for r in gap_rows(wants)]
    plan = kit_plan(doc, fp, p, L)
    plan_bytes = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    res = {"format": PLAN_FORMAT, "archetype": doc["id"], "kit": doc["kit"], "params": p, "pack": pack,
           "mood": dict(mood, mood=p["mood"]), "footprint": fp["size"], "plan": plan,
           "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
           "archetype_sha256": hashlib.sha256(json.dumps(doc, sort_keys=True).encode()).hexdigest(),
           "archetype_doc": doc,
           "placements": L.rows, "groups": groups_rep, "gaps": gaps, "wants": want_rows, "trims": L.trims,
           "short": L.short, "recipes": sorted({r["key"] for r in L.rows if r["source"] == "recipe"}),
           "zones": {"floor_rect_m": list(L.F), "entrance_rect_m": [_r3(v) for v in L.entrance_rect],
                     "path_m": [[_r3(a), _r3(b)] for a, b in L.path], "path_width_m": _r3(2 * L.path_half),
                     "focal_m": list(L.focal), "focal_target_m": list(L.focal_front()),
                     "fight_rect_m": [_r3(v) for v in L.fight_rect] if L.fight_rect else None,
                     "nooks_m": {k: [_r3(x) for x in v] for k, v in L.nooks.items()},
                     "doors": [dict(d, point_m=[_r3(c) for c in door_point(fp, d)]) for d in fp["doors"]]},
           "tris": {"skeleton": L.skel_tris, "dressing": L.tris, "budget_for_dressing": L.budget},
           "layout": layout_stats(L)}
    return res


def layout_stats(L):
    x0, z0, x1, z1 = L.F
    area = max(1e-6, (x1 - x0) * (z1 - z0))
    cov = sum(max(0.0, min(r[2], x1) - max(r[0], x0)) * max(0.0, min(r[3], z1) - max(r[1], z0))
              for r, _k, g in L.solids if g not in ("skeleton", "wallmount"))
    zones = {}
    for r in L.rows:
        zones[r["zone"]] = zones.get(r["zone"], 0) + 1
    n = max(1, len(L.rows))
    ent = L.entrance_rect
    fight = L.fight_rect
    path_len = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(L.path, L.path[1:]))
    return {"floor_m2": _r3(area), "pieces": len(L.rows),
            "floor_solids": sum(1 for _r, _k, g in L.solids if g not in ("skeleton", "wallmount")),
            "density_per_10m2": _r3(10.0 * sum(1 for _r, _k, g in L.solids if g not in ("skeleton", "wallmount")) / area),
            "coverage": round(cov / area, 4),
            "zone_share": {k: round(v / float(n), 3) for k, v in sorted(zones.items())},
            "zone_area_share": {"entrance": round((ent[2] - ent[0]) * (ent[3] - ent[1]) / area, 3),
                                "path": round(path_len * 2 * L.path_half / area, 3),
                                "fight": round(((fight[2] - fight[0]) ** 2) / area, 3) if fight else 0.0}}


# ----------------------------------------------------------------------------------------------- kit plan + cameras
def cameras(doc, fp, params):
    """Standard cameras a (entrance -> focal), b / c (corners), d (focal -> entrance); interiors stay inside the room."""
    x0, z0, x1, z1 = fp["floor_rect_m"]
    ent = fp["entrance"]
    ex, ez = door_point(fp, ent)
    nx, nz = WALL_NORMAL[ent["side"]]
    fx, fz = fp["focal_m"]
    wall_h = float(fp.get("ceiling_y", 4.5))
    h = min(wall_h - 0.7, 2.4 + 0.12 * max(x1 - x0, z1 - z0)) if not doc["exterior"] else 2.8 + 0.1 * max(x1 - x0, z1 - z0)
    pull = params.get("camera_pull", 0.0)
    m = 0.45
    def clamp(x, z):
        if doc["exterior"]:
            return x, z
        return min(max(x, x0 + m), x1 - m), min(max(z, z0 + m), z1 - m)
    out = {}
    if doc["exterior"]:
        # exteriors: eye height, looking past the focal point toward the far side so the horizon and sky are framed
        dist = math.hypot(fx - ex, fz - ez) or 1.0
        ux, uz = (fx - ex) / dist, (fz - ez) / dist
        ax, az = ex + nx * (0.6 + pull * dist), ez + nz * (0.6 + pull * dist)
        if fp.get("camera_a"):
            ax, az = fp["camera_a"][0], fp["camera_a"][1]
        out["a"] = {"position": [_r3(ax), 3.0, _r3(az)], "look_at": [_r3(fx + ux * 6.0), 2.2, _r3(fz + uz * 6.0)], "fov": 60}
        corners = sorted([(x0, z0), (x1, z0), (x0, z1), (x1, z1)], key=lambda c: math.hypot(c[0] - ex, c[1] - ez))
        for name, c, o in (("b", corners[0], corners[3]), ("c", corners[1], corners[2])):
            out[name] = {"position": [_r3(c[0]), 3.2, _r3(c[1])], "look_at": [_r3(o[0] * 0.5 + fx * 0.5), 2.0,
                                                                            _r3(o[1] * 0.5 + fz * 0.5)], "fov": 60}
        out["d"] = {"position": [_r3(fx + ux * 2.0), 2.6, _r3(fz + uz * 2.0)], "look_at": [_r3(ex), 2.0, _r3(ez)], "fov": 60}
        return out
    ax, az = clamp(ex + nx * (0.5 + pull * math.hypot(fx - ex, fz - ez)), ez + nz * (0.5 + pull * math.hypot(fx - ex, fz - ez)))
    if fp.get("camera_a"):
        ax, az = fp["camera_a"][0], fp["camera_a"][1]
    out["a"] = {"position": [_r3(ax), _r3(h), _r3(az)], "look_at": [_r3(fx), 1.2, _r3(fz)], "fov": 60}
    tx, tz = -nz, nx
    corners = sorted([(x0, z0), (x1, z0), (x0, z1), (x1, z1)], key=lambda c: math.hypot(c[0] - ex, c[1] - ez))
    near = corners[:2]
    far = corners[2:]
    for name, c, o in (("b", near[0], far[1]), ("c", near[1], far[0])):
        px, pz = clamp(c[0], c[1])
        out[name] = {"position": [_r3(px), _r3(h * 0.95), _r3(pz)],
                     "look_at": [_r3((o[0] * 0.6 + fx * 0.4)), 1.2, _r3((o[1] * 0.6 + fz * 0.4))], "fov": 60}
    dx, dz = clamp(fx + nx * 0.3 - tx * 1.5, fz + nz * 0.3 - tz * 1.5)
    out["d"] = {"position": [_r3(dx), _r3(min(h, 3.0)), _r3(dz)], "look_at": [_r3(ex), 1.2, _r3(ez)], "fov": 60}
    return out


def kit_plan(doc, fp, params, L):
    """The kit compiler's own plan: skeleton + grammar placements + doors + cameras (+ look/light override)."""
    pieces = [{k: v for k, v in sk.items() if not k.startswith("_")} for sk in fp["skeleton"]]
    wall = []
    for r in L.rows:
        if r.get("socket"):
            wall.append({"key": r["key"], "socket": r["socket"]})
        elif "lot" in r:
            pieces.append({"key": r["key"], "lot": r["lot"]})
        else:
            row = {"key": r["key"], "at_m": r["at_m"], "yaw": r["yaw"]}
            if r.get("landmark"):
                row["kind"] = "landmark"
            if r["y"]:
                row["y"] = r["y"]
            if r.get("mounted"):
                row["mounted"] = True
            pieces.append(row)
    cams = cameras(doc, fp, params)
    plan = {"id": doc["id"], "name": doc["name"], "description": doc["description"], "exterior": bool(doc["exterior"]),
            "look_profile": fp.get("look_profile", doc["look_profile"]), "plot_cells": list(fp["plot_cells"]), "pieces": pieces,
            "doors": [{k: v for k, v in d.items() if k in ("id", "side", "cell")} for d in fp["doors"] if not d.get("virtual")],
            "cameras": cams, "camera": cams["a"], "protagonist": PROTAGONIST}
    for k in ("wall_height", "open_ends", "open_streets", "open_transitions", "lamp", "states", "mounts"):
        if k in fp:
            plan[k] = fp[k]
    if wall:
        plan["wall"] = wall
    if doc["kit"] == "cyber":
        plan.setdefault("open_streets", [])
        plan.setdefault("open_transitions", False)
    return plan


@contextlib.contextmanager
def _foreign(mod, keys):
    """Let a kit compiler see foreign generator pieces (recipes) for the duration of one compile."""
    added = []
    if keys and hasattr(mod, "manifest"):
        pieces = mod.manifest()["pieces"]
        man = manifest()
        for k in keys:
            if k not in pieces:
                pieces[k] = man[k][1]
                added.append(k)
    try:
        yield
    finally:
        if added:
            pieces = mod.manifest()["pieces"]
            for k in added:
                pieces.pop(k, None)


def compile(res, door_targets=None):
    """Run the kit's compiler on res['plan'] -> (room, pres, report). door_targets: door id -> (room, door, label)."""
    doc = res.get("archetype_doc") or load_archetype(res["archetype"])
    mod = importlib.import_module(KITS[doc["kit"]][0])
    plan = json.loads(json.dumps(res["plan"]))
    for d in plan["doors"]:
        t = (door_targets or {}).get(d["id"]) or ("elsewhere", d["id"], "Leave")
        d.update(to_room=t[0], to_door=t[1], label=t[2])
        if doc["kit"] == "medieval" or doc["kit"] == "western":
            d.setdefault("cell", 1)
    plan.pop("cameras", None)
    with _foreign(mod, res["recipes"]):
        try:
            room, pres, rep = mod.compile_room(plan)
        except mod.PlanError as e:
            raise PlaceError("kit compiler refused the plan: %s" % e)
    if res["params"].get("light", 1.0) != 1.0 or res["params"].get("contrast", 0.0):
        pres["look"] = light_override(res["pack"], plan["look_profile"], res["params"]["light"],
                                      contrast=res["params"].get("contrast", 0.0))
    return room, pres, rep


def light_override(pack, profile, factor, root=None, contrast=0.0):
    """Per-room look override: ambient / key / fill energies x factor (0.85-1.15); contrast c (0-0.2) also takes c of
    the ambient energy away and adds c to the key energy. Colours unchanged."""
    root = Path(root or R)
    view = json.loads((root / "packs" / pack / "view.json").read_text(encoding='utf-8'))
    prof = view["look"]["profiles"].get(profile) or view["look"]["profiles"]["interior"]
    out = {}
    for k in ("ambient", "key", "fill"):
        v = prof.get(k)
        if isinstance(v, list) and len(v) >= 2:
            c = {"ambient": 1.0 - contrast, "key": 1.0 + contrast}.get(k, 1.0)
            out[k] = [v[0], round(float(v[1]) * factor * c, 4)] + list(v[2:])
    return out


def static_checks(res, room, pres, rep):
    """Reachability + clearance (tools.room_clearance), path corridor, coverage and triangle numbers."""
    from tools.room_clearance import clearance
    doc = res.get("archetype_doc") or load_archetype(res["archetype"])
    fp = next(f for f in doc["footprints"] if f["size"] == res["footprint"])
    z = res["zones"]
    targets = {"focal": tuple(z["focal_target_m"])}
    for d in z["doors"]:
        nx, nz = WALL_NORMAL[d["side"]]
        targets["door:" + d["id"]] = (d["point_m"][0] + nx * 0.6, d["point_m"][1] + nz * 0.6)
    if z.get("fight_rect_m"):
        f = z["fight_rect_m"]
        targets["fight"] = ((f[0] + f[2]) / 2, (f[1] + f[3]) / 2)
    start = targets["door:" + fp["entrance"]["id"]]
    pack = doc["base_pack"]
    room_nodoors = dict(room, doors=[])
    b = tuple(fp.get("walk_rect_m", z["floor_rect_m"]))
    cl = clearance(room_nodoors, pres, lambda key: glb_for_key(key, pack), start=start, targets=targets, boundary=b)
    need = float(fp["min_clear_m"])
    failures = []
    for k, ok in sorted(cl["reachable"].items()):
        if not ok:
            failures.append("%s unreachable from the entrance" % k)
    if cl["clear_square_m"] + 1e-6 < need:
        failures.append("clear floor %.2f m < %.2f m" % (cl["clear_square_m"], need))
    maxcov = float(doc.get("max_coverage", 0.35))
    cov = res["layout"]["coverage"]
    if cov > maxcov:
        failures.append("clutter over budget: coverage %.3f > %.3f" % (cov, maxcov))
    if rep.get("tri_estimate", 0) > TRI_CAP:
        failures.append("triangles %d > %d" % (rep["tri_estimate"], TRI_CAP))
    return {"ok": not failures, "failures": failures, "reachable": cl["reachable"], "clear_square_m": cl["clear_square_m"],
            "clear_centre": cl["clear_centre"], "walkable_m2": cl["walkable_m2"], "solids": cl["solids"],
            "min_clear_m": need, "coverage": cov, "max_coverage": maxcov, "tri_estimate": rep.get("tri_estimate")}


def plan_and_check(archetype, params=None):
    res = make_plan(archetype, params)
    room, pres, rep = compile(res)
    st = static_checks(res, room, pres, rep)
    return res, room, pres, rep, st


def plan_bytes(res):
    return json.dumps(res["plan"], sort_keys=True, separators=(",", ":")).encode()


def report_lines(res, st=None):
    p = res["params"]
    out = ["%s  size %s  mood %s (%s)  clutter %d  seed %d  plan %s" % (
        res["archetype"], p["size"], p["mood"], res["pack"], p["clutter"], p["seed"], res["plan_sha256"][:12])]
    out.append("pieces %d (%s)  dressing tris %d / %d  coverage %.3f  density %.2f per 10 m2" % (
        res["layout"]["pieces"], ", ".join("%s %d" % (g["group"], g["placed"]) for g in res["groups"] if g["placed"]),
        res["tris"]["dressing"], res["tris"]["budget_for_dressing"], res["layout"]["coverage"],
        res["layout"]["density_per_10m2"]))
    if st:
        out.append("static: %s  clear %.2f m (need %.2f)  reachable %d/%d  tris est %s" % (
            "ok" if st["ok"] else "FAIL", st["clear_square_m"], st["min_clear_m"],
            sum(1 for v in st["reachable"].values() if v), len(st["reachable"]), st["tri_estimate"]))
        out += ["  - " + f for f in st["failures"]]
    if res["recipes"]:
        out.append("recipes (generators built into the pack): " + ", ".join(res["recipes"]))
    for g in res["gaps"]:
        out.append("gap: group %s wants %s -> %s (left out %d)" % (g["group"], "/".join(g["wants"]) or g["group"],
                                                                   "; ".join(r["status"] for r in g["rows"]), g["left_out"]))
    for w in res["wants"]:
        if w["status"] != "exists":
            out.append("not in library: %s (%s) - %s" % (w["want"], w["status"], w["next"]))
    for t in res["trims"][:6]:
        out.append("trimmed: %s %s (%s)" % (t["group"], t["key"], t["why"]))
    for s in res["short"][:6]:
        out.append("short: %s" % json.dumps(s, sort_keys=True))
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="adventure_maker.place")
    ap.add_argument("cmd", choices=["list", "plan", "check"])
    ap.add_argument("archetype", nargs="?")
    ap.add_argument("--size")
    ap.add_argument("--mood")
    ap.add_argument("--clutter", type=int)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for n in list_archetypes():
            d = load_archetype(n)
            print("%-24s %-9s sizes %-20s moods %s" % (n, d["kit"], "/".join(f["size"] for f in d["footprints"]),
                                                       ", ".join(sorted(d["moods"]))))
        return 0
    params = {k: v for k, v in (("size", a.size), ("mood", a.mood), ("clutter", a.clutter), ("seed", a.seed)) if v is not None}
    try:
        if a.cmd == "plan":
            res = make_plan(a.archetype, params)
            print(json.dumps(res, indent=1, sort_keys=True) if a.json else "\n".join(report_lines(res)))
            return 0
        res, room, pres, rep, st = plan_and_check(a.archetype, params)
        print("\n".join(report_lines(res, st)))
        return 0 if st["ok"] else 1
    except PlaceError as e:
        print("REFUSED: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
