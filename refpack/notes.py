"""Reference notes: load (dict or JSON file), validate against schema/reference_notes.schema.json,
cross-check against the reference list, and normalise (defaults filled) for the drafter."""
import copy
import hashlib
import json
import os

from . import jsonschema_mini

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema", "reference_notes.schema.json")
MAX_NOTES_BYTES = 256 * 1024
FREE_TEXT_KEYS = ("title", "notes", "avoid_notes")

DEFAULT_USE = ["palette", "lighting", "fog", "materials", "shapes", "mood"]


class NotesError(ValueError):
    pass


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def canonical_bytes(obj):
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def load_notes(notes):
    """notes: dict, or a path to a JSON file. Returns (dict, raw_bytes_for_hash)."""
    if isinstance(notes, dict):
        try:
            raw = canonical_bytes(notes)
        except (TypeError, ValueError) as e:
            raise NotesError("notes object is not JSON-serialisable: %s" % e)
        if len(raw) > MAX_NOTES_BYTES:
            raise NotesError("notes are %d bytes (> %d)" % (len(raw), MAX_NOTES_BYTES))
        return copy.deepcopy(notes), raw
    if not isinstance(notes, str):
        raise NotesError("notes must be an object or a path to a JSON file, got %s" % type(notes).__name__)
    if not os.path.isfile(notes):
        raise NotesError("notes file not found: %s" % notes)
    size = os.path.getsize(notes)
    if size > MAX_NOTES_BYTES:
        raise NotesError("notes file is %d bytes (> %d)" % (size, MAX_NOTES_BYTES))
    with open(notes, "rb") as f:
        raw = f.read()
    try:
        d = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as e:
        raise NotesError("notes file is not UTF-8: %s" % e)
    except ValueError as e:
        raise NotesError("notes file is not valid JSON: %s" % e)
    if not isinstance(d, dict):
        raise NotesError("notes JSON must be an object")
    return d, canonical_bytes(d)


def validate_notes(d, n_refs, ref_sha256s=None):
    """Schema + cross checks. Returns normalised notes. Raises NotesError with all problems listed."""
    errs = jsonschema_mini.validate(d, load_schema())
    if not errs:
        idx = [r["index"] for r in d["references"]]
        if len(idx) != len(set(idx)):
            errs.append("$.references: duplicate index")
        for r in d["references"]:
            if r["index"] >= n_refs:
                errs.append("$.references[index=%d]: only %d reference image(s) were given" % (r["index"], n_refs))
            if ref_sha256s is not None and "sha256" in r and r["index"] < n_refs and r["sha256"] != ref_sha256s[r["index"]]:
                errs.append("$.references[index=%d]: sha256 does not match the image at that position "
                            "(notes describe a different file)" % r["index"])
            for key in ("crop",):
                if key in r:
                    x0, y0, x1, y1 = r[key]
                    if not (x0 < x1 and y0 < y1) or (x1 - x0) * (y1 - y0) < 0.02:
                        errs.append("$.references[index=%d].crop: needs x0<x1, y0<y1 and >= 2%% of the image" % r["index"])
            for j, b in enumerate(r.get("exclude", [])):
                if not (b[0] < b[2] and b[1] < b[3]):
                    errs.append("$.references[index=%d].exclude[%d]: needs x0<x1 and y0<y1" % (r["index"], j))
            for name, b in sorted(r.get("regions", {}).items()):
                if not (b[0] < b[2] and b[1] < b[3]) or (b[2] - b[0]) * (b[3] - b[1]) < 0.002:
                    errs.append("$.references[index=%d].regions.%s: needs x0<x1, y0<y1 and >= 0.2%% of the image" % (r["index"], name))
        if not any("palette" in r.get("use", DEFAULT_USE) and r.get("weight", 1.0) > 0 for r in d["references"]):
            errs.append("$.references: at least one reference must be used for 'palette' with weight > 0")
    if errs:
        raise NotesError("reference notes are invalid: " + "; ".join(errs[:20]))
    return normalise(d, n_refs)


def normalise(d, n_refs):
    n = copy.deepcopy(d)
    n.setdefault("themes", [])
    n.setdefault("surfaces", {})
    n.setdefault("finish", "satin")
    n.setdefault("metal_finish", "chrome" if n.get("finish") == "chrome" else "brushed")
    sl = n["shape_language"]
    sl.setdefault("openings", sl["architecture"])
    sl.setdefault("seating", sl["furniture"])
    sl.setdefault("props", sl["furniture"])
    sl.setdefault("vehicles", sl["furniture"])
    sl.setdefault("nature", ["organic"])
    n["fog"].setdefault("tint", "none")
    lt = n["lighting"]
    lt.setdefault("key", "mixed")
    lt.setdefault("light_sources", [])
    p = n.setdefault("palette", {})
    p.setdefault("temperature", lt["temperature"])
    p.setdefault("saturation", "moderate")
    p.setdefault("accent_hues", [])
    p.setdefault("avoid_hues", [])
    det = n.setdefault("detail", {})
    det.setdefault("texture_detail", "soft")
    det.setdefault("dither", "auto")
    n.setdefault("character_style", {})
    n.setdefault("avoid", [])
    n.setdefault("sound", {})
    by_index = {r["index"]: r for r in n["references"]}
    refs = []
    for i in range(n_refs):
        r = copy.deepcopy(by_index.get(i, {"index": i, "kind": "concept_art"}))
        r.setdefault("use", list(DEFAULT_USE))
        r.setdefault("weight", 1.0 if i in by_index else 0.5)
        r.setdefault("setting", n["setting"])
        r.setdefault("time_of_day", n["time_of_day"])
        r.setdefault("fog_density", n["fog"]["density"])
        r.setdefault("exclude", [])
        r.setdefault("materials", [])
        r.setdefault("regions", {})
        refs.append(r)
    n["references"] = refs
    return n


def controlled_view(n):
    """The notes with every free-text field removed (what the drafter may read)."""
    out = copy.deepcopy(n)
    for k in FREE_TEXT_KEYS:
        out.pop(k, None)
    out.get("character_style", {}).pop("notes", None)
    for r in out.get("references", []):
        r.pop("notes", None)
    return out


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()
