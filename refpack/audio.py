"""Sound palette selection from lane-audio catalog tags + a mirror of lane-audio's palette resolver.

The original `thaw_audio.stock_catalog.resolve_palette` only reads files inside lane-audio, so a draft
`audio.json` that lives in a project pack dir is checked by `check_palette` below, which mirrors its rules
(schema 1.1). tests/test_audio_mirror.py proves the mirror agrees with the original on the shipped palettes
and on known-bad controls."""
import json
import os
import re

from . import config

PALETTE_KEYS = ("schema_version", "id", "bindings", "presets")


def load_catalog(audio_dir=None):
    p = os.path.join(config.audio_dir(audio_dir), "catalog.json")
    with open(p, "rb") as f:
        raw = f.read()
    return json.loads(raw.decode("utf-8")), raw


def query(catalog, category=None, tags=(), prefer=(), max_n=None):
    rows = []
    for r in catalog["assets"]:
        if category is not None and r["category"] != category:
            continue
        if any(t not in r["tags"] for t in tags):
            continue
        score = sum(1 for t in prefer if t in r["tags"])
        rows.append((-score, r["id"]))
    rows.sort()
    ids = [i for _s, i in rows]
    return ids[:max_n] if max_n else ids


def run_queries(catalog, queries):
    out = []
    for q in queries:
        ids = query(catalog, q.get("category"), q.get("tags", ()), q.get("prefer", ()), q.get("max"))
        if ids:
            out.extend(i for i in ids if i not in out)
            if not q.get("accumulate"):
                break
    return out


def select_palette(pack_id, notes, surfaces, catalog, amap):
    """Returns (audio_dict, decisions). notes = normalised controlled notes; surfaces = {class: material}."""
    snd = notes.get("sound", {})
    mats = notes.get("materials", [])
    moods = notes.get("mood", [])
    themes = notes.get("themes", [])
    setting = notes.get("setting")
    dec = {}
    fm = amap["floor_from_material"]
    inside = snd.get("inside_floor") or fm.get(surfaces.get("floor"), "floor")
    outside = snd.get("outside_ground") or fm.get(surfaces.get("ground"), "grass")
    b = {}
    b["walk_inside"] = {"ids": run_queries(catalog, amap["footsteps"][inside]), "gain": 0.65}
    b["walk_outside"] = {"ids": run_queries(catalog, amap["footsteps"][outside]), "gain": 0.65}
    dec["footsteps"] = {"inside": inside, "outside": outside}
    metalish = any(m in mats for m in ("chrome", "brushed_metal", "iron", "rusted_iron", "brass")) or surfaces.get("trim") in ("chrome", "brushed_metal", "iron")
    rounded = "rounded" in notes["shape_language"].get("openings", []) or "molded" in notes["shape_language"].get("openings", [])
    if metalish and rounded:
        door = "hatch"
    elif metalish or "industrial" in notes["shape_language"].get("openings", []):
        door = "metal"
    elif any(m in mats for m in ("stone", "cobble", "brick", "marble")) and "ornate" in notes["shape_language"].get("openings", []):
        door = "gate"
    else:
        door = "wood"
    b["door"] = {"ids": run_queries(catalog, amap["door"][door]), "gain": 0.6}
    dec["door"] = door
    if any(m in mats for m in ("crystal", "glass")) or "screens" in mats:
        pick = "sphere"
    elif any(t in themes for t in ("forest", "jungle", "village", "plains", "swamp")):
        pick = "organic"
    elif any(t in themes for t in ("mine", "industrial", "cave")) or metalish:
        pick = "metal"
    elif any(t in themes for t in ("desert", "ruins", "temple", "castle", "harbor")):
        pick = "coin"
    else:
        pick = "generic"
    b["pickup"] = {"ids": run_queries(catalog, amap["pickup"][pick]), "gain": 0.55}
    dec["pickup"] = pick
    voices = list(snd.get("voices") or [])
    for m in moods:
        for v in amap["voices_from_mood"].get(m, []):
            if v not in voices:
                voices.append(v)
    voices = voices[:3] or ["calm", "bright"]
    vids = []
    for v in voices:
        q = dict(amap["voice_query"])
        vids.extend(i for i in run_queries(catalog, [dict(q, tags=q["tags"] + [v])]) if i not in vids)
    b["resident"] = {"ids": vids, "gain": 0.35}
    dec["voices"] = voices
    crit = list(snd.get("creatures") or [])
    cids = []
    for c in crit:
        cids.extend(i for i in run_queries(catalog, amap["creatures"][c]) if i not in cids)
    if cids:
        b["wildlife"] = {"ids": cids, "gain": 0.45}
    amb = list(snd.get("ambience") or [])
    if not amb:
        if "habitat" in themes or "lab" in themes or "space" in themes:
            amb.append("habitat")
        if "fire" in [x for x in notes["lighting"].get("light_sources", [])]:
            amb.append("fire")
        if any(t in themes for t in ("cave", "mine")):
            amb.append("cave_drip")
        if any(t in themes for t in ("forest", "jungle", "village", "plains")):
            amb.append("forest")
        if any(t in themes for t in ("ocean", "coast", "harbor", "underwater")):
            amb.append("waves")
        if any(t in themes for t in ("polar", "mountain", "desert")):
            amb.append("wind")
    inner = [a for a in amb if a in amap["interior_ambience"]]
    outer = [a for a in amb if a not in amap["interior_ambience"]]
    room = inner[0] if inner else ("silence" if setting == "interior" else (outer[0] if outer else "silence"))
    out_a = outer[0] if outer else "wind"
    b["room_ambience"] = {"ids": run_queries(catalog, amap["ambience"][room]), "gain": 0.28}
    b["outside_ambience"] = {"ids": run_queries(catalog, amap["ambience"][out_a]), "gain": 0.28}
    dec["ambience"] = {"room": room, "outside": out_a}
    music = snd.get("music")
    if not music:
        for m in moods:
            if m in amap["music_from_mood"]:
                music = amap["music_from_mood"][m]
                break
    music = music or "explore"
    b["room_music"] = {"ids": run_queries(catalog, amap["music"][music]), "gain": 0.35}
    explore = "explore" if music != "explore" else "night"
    b["explore_music"] = {"ids": run_queries(catalog, amap["music"][explore]), "gain": 0.35}
    dec["music"] = {"room": music, "explore": explore}
    craft = "industrial" if (metalish or any(t in themes for t in ("lab", "mine", "industrial", "habitat", "space"))) else "rustic"
    ids = []
    for q in amap["craft"][craft]:
        ids.extend(i for i in run_queries(catalog, [q]) if i not in ids)
    b["lab_build"] = {"ids": ids, "gain": 0.5}
    dec["craft"] = craft
    b = {k: v for k, v in b.items() if v["ids"]}
    audio = {"schema_version": "1.1", "id": pack_id,
             "description": "Draft sound palette chosen by catalog tags (hermes64_pack_from_refs); not reviewed by ear.",
             "bindings": b, "presets": {}}
    return audio, dec


def check_palette(palette, catalog, resolve_preset=None):
    """Mirror of lane-audio stock_catalog.resolve_palette (schema 1.1) on an in-memory palette.
    Returns a list of errors (empty = valid). resolve_preset(generator, params) may be supplied to run the
    real lane-audio parameter resolver for presets; presets that would need it fail if it is absent."""
    errs = []
    if not isinstance(palette, dict) or any(k not in palette for k in PALETTE_KEYS):
        return ["palette requires schema_version/id/bindings/presets"]
    if any(k not in PALETTE_KEYS + ("description",) for k in palette):
        return ["unknown palette field"]
    if palette["schema_version"] != "1.1" or not isinstance(palette["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", palette["id"]):
        return ["invalid palette version or ID"]
    if not isinstance(palette["bindings"], dict) or not palette["bindings"] or not isinstance(palette["presets"], dict):
        return ["invalid binding/preset objects"]
    lookup = {r["id"]: r for r in catalog["assets"]}
    for name, binding in palette["bindings"].items():
        if not isinstance(binding, dict) or sorted(binding) != ["gain", "ids"]:
            errs.append("binding %s requires only gain and ids" % name)
            continue
        ids = binding["ids"]
        if not isinstance(ids, list) or not ids or any(type(i) is not str or i not in lookup for i in ids):
            errs.append("binding %s: unknown or empty binding IDs" % name)
        g = binding["gain"]
        if isinstance(g, bool) or not isinstance(g, (int, float)) or not (0 <= g <= 1):
            errs.append("binding %s: mix gain must be a number in [0, 1]" % name)
    for name, preset in palette["presets"].items():
        if not isinstance(preset, dict) or sorted(preset) != ["asset", "params"] or not isinstance(preset["params"], dict):
            errs.append("preset %s requires asset and params" % name)
            continue
        ident = preset["asset"]
        if type(ident) is not str or ident not in lookup:
            errs.append("preset %s: unknown preset asset" % name)
            continue
        if lookup[ident]["provenance"] != "core_generated":
            errs.append("preset %s: frozen audio cannot be regenerated or overridden by a pack" % name)
            continue
        if resolve_preset is None:
            errs.append("preset %s: cannot be checked without the lane-audio parameter resolver" % name)
        else:
            try:
                inputs = dict(lookup[ident]["params"])
                inputs.update(preset["params"])
                resolve_preset(lookup[ident]["generator"], inputs)
            except ValueError as e:
                errs.append("preset %s: %s" % (name, e))
    return errs
