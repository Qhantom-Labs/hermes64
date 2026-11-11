"""Theme pack loading + validation. A pack is DATA: packs/<id>/pack.json. Core code never
hard-codes theme colours; it only knows the role vocabulary and the material kinds."""
import json
import os

from .palette import Palette

CORE_ROLES = (
    "wall wall_alt floor ceiling trim frame door glass view roof step rail post stone metal chrome "
    "body body_alt cushion fabric knit fur quilt screen light orb wood paper book leather rope fire "
    "grass snow sand rock dirt water ice bark foliage cap flower hull hull_alt band sky particle "
    "skin face headwear opening costume coat").split()

# Exterior roles (additive 3.2). Optional: a pack that does not bind them falls back to an existing role, so
# older packs keep validating and building.
OPTIONAL_ROLES = {"cliff": "rock", "path": "dirt", "vista": "view", "vista_far": "view", "field": "grass"}

KINDS = ("baked_unlit", "chrome_env", "glass_env", "emissive", "view_plane", "card_alpha", "water", "face_atlas")
TEXTURED_KINDS = ("baked_unlit", "emissive", "view_plane", "card_alpha", "water", "face_atlas")
CORE_CLASSES = {
    "shell": 1500, "building": 900, "structure": 500, "arch": 300, "terrain": 512, "flora": 300,
    "furniture": 300, "furniture_large": 400, "vehicle": 500, "prop": 150, "soft": 150, "sky": 128,
    "fx": 16, "character": 700, "animal": 300,
}
REQUIRED_KEYS = ("id", "version", "palette", "palette_names", "light_ramp", "materials", "light_rig", "fog",
                 "kit_presets", "fixtures", "cast", "validator_thresholds", "env_maps")


class PackError(ValueError):
    pass


class Pack:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        with open(self.path, "rb") as f:
            self.raw_bytes = f.read()
        try:
            d = json.loads(self.raw_bytes.decode("utf-8"))
        except Exception as e:
            raise PackError("pack.json is not valid UTF-8 JSON: %s" % e)
        self.d = d
        errors = validate_pack_dict(d)
        if errors:
            raise PackError("; ".join(errors[:12]))
        self.id = d["id"]
        self.version = d["version"]
        self.pal = Palette(d["palette"], d["palette_names"])
        self.light_ramp = [self.pal.idx(n) for n in d["light_ramp"]]
        self.materials = d["materials"]
        self.light_rig = d["light_rig"]
        self.fog = d["fog"]
        self.presets = d["kit_presets"]
        self.fixtures = d["fixtures"]
        self.cast = d["cast"]
        self.thresholds = d["validator_thresholds"]
        self.env_maps = d["env_maps"]
        self.face_atlas = d.get("face_atlas")
        # texture painting seed: a mood pack (kits/core/mood.py) keeps its base pack's seed, so every texture is painted
        # with the same strokes and mottle as the base and only the ramp colours differ
        self.seed_id = d.get("texture_seed", self.id)

    @property
    def palette_names(self):
        return set(self.pal.names)

    def mat(self, role):
        if role not in self.materials and role in OPTIONAL_ROLES:
            return self.materials[OPTIONAL_ROLES[role]]
        return self.materials[role]

    def tri_limit(self, cls, core_limit):
        over = self.thresholds.get("tri_limits", {}).get(cls)
        return min(core_limit, over) if over else core_limit


def _is_name(pal_names, v):
    return isinstance(v, str) and v in pal_names


def validate_pack_dict(d):
    """Returns a list of human-readable errors (empty = valid)."""
    err = []
    if not isinstance(d, dict):
        return ["pack is not an object"]
    for k in REQUIRED_KEYS:
        if k not in d:
            err.append("missing key %r" % k)
    if err:
        return err
    pal, names = d["palette"], d["palette_names"]
    if not isinstance(pal, list) or not pal:
        err.append("palette must be a non-empty list")
        return err
    if len(pal) > 32:
        err.append("palette has %d colours (> 32)" % len(pal))
    if len(pal) != len(names):
        err.append("palette (%d) and palette_names (%d) differ in length" % (len(pal), len(names)))
    if len(set(names)) != len(names):
        err.append("duplicate palette names")
    for c in pal:
        if not (isinstance(c, str) and len(c) == 7 and c[0] == "#" and all(ch in "0123456789abcdefABCDEF" for ch in c[1:])):
            err.append("bad colour %r" % (c,))
    if len(set(x.lower() for x in pal if isinstance(x, str))) != len(pal):
        err.append("duplicate palette colours")
    pn = set(names)
    if "texture_seed" in d and not (isinstance(d["texture_seed"], str) and d["texture_seed"]):
        err.append("texture_seed must be a non-empty string")
    lr = d["light_ramp"]
    if not isinstance(lr, list) or len(lr) < 3 or not all(_is_name(pn, n) for n in lr):
        err.append("light_ramp must list >= 3 palette names")
    mats = d["materials"]
    if not isinstance(mats, dict):
        err.append("materials must be an object")
        return err
    for role in CORE_ROLES:
        if role not in mats:
            err.append("material role %r is not bound" % role)
    for role, m in mats.items():
        if role not in CORE_ROLES and role not in OPTIONAL_ROLES:
            err.append("unknown material role %r" % role)
            continue
        if not isinstance(m, dict) or m.get("kind") not in KINDS:
            err.append("role %r: bad kind %r" % (role, m.get("kind") if isinstance(m, dict) else m))
            continue
        k = m["kind"]
        if k in TEXTURED_KINDS and role not in ("face", "costume", "coat", "headwear"):
            t = m.get("texture")
            if not isinstance(t, dict) or "gen" not in t:
                err.append("role %r: textured kind needs texture.gen" % role)
            else:
                if t["gen"] not in ("env", "scene"):
                    ramp = t.get("ramp")
                    if not isinstance(ramp, list) or not ramp or not all(_is_name(pn, n) for n in ramp):
                        err.append("role %r: texture.ramp must list palette names" % role)
                size = t.get("size", 32)
                if not isinstance(size, int) or size < 4 or size > 128:
                    err.append("role %r: texture size %r outside 4..128" % (role, size))
            tm = m.get("tile_m", 1.0)
            if not isinstance(tm, (int, float)) or tm <= 0:
                err.append("role %r: tile_m must be > 0" % role)
        if k in ("chrome_env", "glass_env"):
            if not _is_name(pn, m.get("tint")):
                err.append("role %r: tint must be a palette name" % role)
            if m.get("env") not in d.get("env_maps", {}):
                err.append("role %r: env %r not in env_maps" % (role, m.get("env")))
    rig = d["light_rig"]
    for key in ("key_dir", "ambient", "key", "sky", "ground"):
        if key not in rig:
            err.append("light_rig missing %r" % key)
    fog = d["fog"]
    for key in ("color", "start", "end"):
        if key not in fog:
            err.append("fog missing %r" % key)
    if all(k in fog for k in ("start", "end")) and not (0 <= fog["start"] < fog["end"]):
        err.append("fog start/end invalid")
    if "color" in fog and not _is_name(pn, fog["color"]):
        err.append("fog colour must be a palette name")
    th = d["validator_thresholds"]
    for cls, lim in th.get("tri_limits", {}).items():
        if cls not in CORE_CLASSES:
            err.append("validator_thresholds.tri_limits: unknown class %r" % cls)
        elif lim > CORE_CLASSES[cls]:
            err.append("pack may not loosen %s budget (%d > %d)" % (cls, lim, CORE_CLASSES[cls]))
    for name, em in d["env_maps"].items():
        names = list(em.get("stops", [])) + list(em.get("below", [])) + list(em.get("above", []))
        names += [em[k] for k in ("edge", "glint", "rim", "horizon_color") if em.get(k)]
        names += [pnl[4] for pnl in em.get("panels", []) if isinstance(pnl, list) and len(pnl) == 5]
        split = "below" in em or "above" in em
        if em.get("gen") != "env" or not all(_is_name(pn, n) for n in names) or \
                (split and not (em.get("below") and em.get("above"))) or (not split and not em.get("stops")):
            err.append("env map %r invalid" % name)
    # Structure of the data tables (generator ids / params are checked against the registry by
    # tools/packcheck.py, which resolves every preset and fixture fail-closed).
    kp = d["kit_presets"]
    if not isinstance(kp, dict) or not all(isinstance(v, dict) and all(isinstance(p, dict) for p in v.values()) for v in kp.values()):
        err.append("kit_presets must be {generator_id: {preset_name: {params}}}")
    fxs = d["fixtures"]
    if not isinstance(fxs, dict):
        err.append("fixtures must be {slot: {generator, preset[, params]}}")
    else:
        for slot, b in fxs.items():
            if not (isinstance(b, dict) and isinstance(b.get("generator"), str) and isinstance(b.get("preset", "default"), str)
                    and isinstance(b.get("params", {}), dict) and set(b) <= {"generator", "preset", "params"}):
                err.append("fixture %r must be {generator, preset[, params]}" % slot)
    cast = d["cast"]
    if not isinstance(cast, dict):
        err.append("cast must be an object")
    else:
        for name, c in cast.items():
            if name.startswith("_"):
                continue
            if not (isinstance(c, dict) and isinstance(c.get("character_id"), str) and c.get("kind") in ("person", "animal")
                    and c.get("supplied_by") == "lane-characters"
                    and set(c) <= {"character_id", "kind", "supplied_by", "source", "study_only", "preset"}):
                err.append("cast %r must be a reference {character_id, kind: person|animal, supplied_by: lane-characters"
                           "[, source, study_only, preset]} (characters are built by lane-characters)" % name)
    return err
