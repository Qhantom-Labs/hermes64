"""Load the refpack library (kit presets, material vocabulary, audio tag map) as one dict + its hashes."""
import hashlib
import json

from . import config

FILES = ("kits.json", "materials.json", "audio_map.json", "kit_tags.json", "kit_variants.json", "gen_calibration.json")


def _load(name):
    with open(config.library_path(name), "r", encoding="utf-8") as f:
        return json.load(f)


def load():
    lib = _load("kits.json")
    lib["materials"] = _load("materials.json")
    lib["audio_map"] = _load("audio_map.json")
    cal = _load("gen_calibration.json")
    lib["gen_calibration"] = cal["gens"]
    lib["use_gen_calibration"] = bool(cal.get("enabled", True))
    return lib


def hashes():
    out = {}
    for name in FILES:
        with open(config.library_path(name), "rb") as f:
            out[name] = hashlib.sha256(f.read()).hexdigest()
    return out
