"""Mood words in a premise or brief -> a mood pack plan (plan 07 lane A3 hand-off for A8 / newgame.pick_style).

Pure lookups; nothing is written. The derivation itself is kits/core/mood.py (loaded from the bundle by path, as the
kit code is not a package of adventure_maker); installing a derived pack with rebuilt, hash-pinned bindings is
tools/mood_pack.py install. Until A8 wires a project-local pack resolver, a mood is APPLIED only when the derived
pack is installed in the bundle (packs/<id>/bindings.json exists); otherwise it is reported as named-not-applied,
never silently dropped.
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_MOOD = {}


def mood_module(root=None):
    root = Path(root or ROOT)
    key = str(root)
    if key not in _MOOD:
        path = root / "kits" / "core" / "mood.py"
        spec = importlib.util.spec_from_file_location("hermes64_kits_core_mood", str(path),
                                                      submodule_search_locations=None)
        mod = importlib.util.module_from_spec(spec)
        # mood.py imports .packs lazily inside check_derived only; derive/resolve need no package context
        spec.loader.exec_module(mod)
        _MOOD[key] = mod
    return _MOOD[key]


def pick_mood(premise, brief=None, root=None):
    """(mood id or None, reason). A brief's palette_mood wins over premise words; unknown words never map."""
    M = mood_module(root)
    if isinstance(brief, dict) and isinstance(brief.get("palette_mood"), dict) and brief["palette_mood"].get("dominant"):
        try:
            spec = M.mood_from_brief(brief["palette_mood"], brief.get("mood"))
        except M.MoodError as e:
            return None, "brief palette_mood not usable: %s" % e
        named = M.resolve_mood("%s %s" % (brief["palette_mood"]["dominant"], spec["time"]))
        return (named or "brief"), "brief palette_mood %s/%s, accent %s, %s" % (
            spec["dominant"], spec["support"], spec["accent"], spec["time"])
    mid = M.resolve_mood(premise or "")
    if not mid:
        return None, "no mood words"
    said = [w for w in M.MOODS[mid]["words"] if w in (premise or "").lower()]
    return mid, "mood words: %s" % (", ".join(said) or mid)


def plan(premise, pack, brief=None, root=None):
    """-> {base, mood, derived_id, installed, apply, reason, command} for newgame / the gap report."""
    root = Path(root or ROOT)
    mid, why = pick_mood(premise, brief, root)
    out = {"base": pack, "mood": mid, "reason": why, "derived_id": None, "installed": False, "apply": False,
           "command": None}
    if not mid or mid == "brief":
        return out
    did = "%s_%s" % (pack, mid)
    installed = (root / "packs" / did / "bindings.json").is_file() and (root / "kits" / "packs" / did / "pack.json").is_file()
    out.update(derived_id=did, installed=installed, apply=installed,
               command="python3 -B -m tools.mood_pack install --bundle %s --base %s --mood %s" % (root, pack, mid))
    return out
