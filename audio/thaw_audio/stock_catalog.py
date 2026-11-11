"""Data-driven core catalog, filtering and pack-palette resolution."""
import copy
import hashlib
import json
import re

from .build import LANE, lane_path
from .stock_synth import resolve, number

CATEGORIES = ("footsteps", "mechanisms", "ui", "rewards", "craft", "dialogue", "creatures",
              "weather", "machines", "combat", "magic", "stingers", "music")


def definitions(seed=90517):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be uint32")
    source = json.loads((LANE / "core/sound_definitions.json").read_text(encoding='utf-8'))
    records = []
    seen = {}
    for entry in source["assets"]:
        identity = entry["id"]
        if not re.fullmatch(r"core\.[a-z0-9_.]+", identity) or identity in seen:
            raise ValueError("invalid/duplicate stock ID")
        seen[identity] = True
        if entry["category"] not in CATEGORIES:
            raise ValueError("unknown category")
        tags = entry["tags"]
        if not isinstance(tags, list) or not tags or any(not isinstance(t, str) or not re.fullmatch(r"[a-z0-9_-]+", t) for t in tags):
            raise ValueError("invalid tags")
        p = dict(entry["params"])
        p["seed"] = int.from_bytes(hashlib.sha256((str(seed)+":"+identity).encode()).digest()[:4], "little")
        p = resolve(entry["generator"], p)
        flags = ["unheard: new sound; perceptual identity and comfort unverified"]
        if entry["category"] in ("combat", "craft"):
            flags.append("review-priority: transient/noise texture may be sharp; audition quietly")
        if p.get("pitch", 0) >= 500 or entry["category"] in ("magic", "music"):
            flags.append("review-priority: bright partials/tones may ring or fatigue")
        if entry["category"] in ("dialogue", "ui"):
            flags.append("review-priority: rapid repetition needs runtime throttling")
        if entry["category"] == "creatures":
            flags.append("review-priority: animal likeness is a synthetic approximation")
        record = dict(entry, tags=sorted(dict.fromkeys(tags)), params=p, loop=p["loop"],
                      provenance="core_generated", review_flags=flags)
        if entry["category"] == "music":
            record["composition_note"] = source["composition_note"]
        records.append(record)
    return sorted(records, key=lambda record: record["id"])


def frozen_records():
    source = json.loads((LANE / "manifest.json").read_text(encoding='utf-8'))
    category_by_synth = {"footstep": "footsteps", "hatch": "mechanisms", "ui": "ui",
                         "dialogue": "dialogue", "cat": "creatures", "sphere": "rewards",
                         "keycard": "mechanisms", "gust": "weather", "hum": "machines",
                         "saucer": "machines", "save": "ui", "ambience": "weather", "music": "music"}
    result = []
    for original in source["assets"]:
        row = copy.deepcopy(original)
        row.update(category=category_by_synth[original["synth"]], generator="frozen_v1",
                   tags=sorted(dict.fromkeys(original["id"].split(".")+["soft", "low-fi", "dylan-approved-wave1"])),
                   provenance="wave1_frozen", owner_feedback="the owner listened to and loved the original 38; unchanged")
        if original["kind"] == "music":
            row["composition_note"] = "Original wave-1 code-composed score, preserved byte-for-byte."
        result.append(row)
    return result


def query(index, terms=(), category=None, tags=(), limit=None):
    if limit is not None and (type(limit) is not int or not 0 <= limit <= 10000):
        raise ValueError("limit must be an integer 0..10000")
    rows = index["assets"]
    terms = [term.casefold() for term in terms]
    matches = []
    for row in sorted(rows, key=lambda r: r["id"]):
        haystack = " ".join([row["id"], row["category"]]+row["tags"]).casefold()
        if category is not None and row["category"] != category:
            continue
        if any(tag not in row["tags"] for tag in tags) or any(term not in haystack for term in terms):
            continue
        matches.append(row)
    returned = matches if limit is None else matches[:limit]
    return {"total": len(rows), "matched": len(matches), "returned": len(returned),
            "has_more": len(returned) < len(matches), "assets": returned}


def resolve_palette(path, index):
    palette = json.loads(lane_path(path).read_text(encoding='utf-8'))
    required = ("schema_version", "id", "bindings", "presets")
    if not isinstance(palette, dict) or any(key not in palette for key in required):
        raise ValueError("palette requires schema_version/id/bindings/presets")
    if any(key not in required+("description",) for key in palette):
        raise ValueError("unknown palette field")
    if palette["schema_version"] != "1.1" or not isinstance(palette["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", palette["id"]):
        raise ValueError("invalid palette version or ID")
    if not isinstance(palette["bindings"], dict) or not palette["bindings"] or not isinstance(palette["presets"], dict):
        raise ValueError("invalid binding/preset objects")
    lookup = {record["id"]:record for record in index["assets"]}
    bindings, presets = {}, {}
    for name, binding in palette["bindings"].items():
        if not isinstance(binding, dict) or sorted(binding) != ["gain", "ids"]:
            raise ValueError("binding requires only gain and ids")
        identities = binding["ids"]
        if not isinstance(identities, list) or not identities or any(type(identity) is not str or identity not in lookup for identity in identities):
            raise ValueError("unknown or empty binding IDs")
        number(binding["gain"], 0, 1, "mix gain")
        bindings[name] = copy.deepcopy(binding)
    for name, preset in palette["presets"].items():
        if not isinstance(preset, dict) or sorted(preset) != ["asset", "params"] or not isinstance(preset["params"], dict):
            raise ValueError("preset requires asset and params")
        identity = preset["asset"]
        if type(identity) is not str or identity not in lookup:
            raise ValueError("unknown preset asset")
        base = lookup[identity]
        if base["provenance"] != "core_generated":
            raise ValueError("frozen audio cannot be regenerated or overridden by a pack")
        inputs = copy.deepcopy(base["params"])
        inputs.update(preset["params"])
        presets[name] = {"asset": identity, "generator": base["generator"], "params": resolve(base["generator"], inputs)}
    return {"schema_version": "1.1", "id": palette["id"], "bindings": bindings, "presets": presets}
