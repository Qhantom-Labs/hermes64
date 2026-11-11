"""Stable asset IDs and full resolved inputs. Original Thaw sound kit."""

import hashlib

from .synth import resolve


def catalog(seed=73021):
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an unsigned 32-bit integer")
    entries = []

    def add(identity, synth, **params):
        digest = hashlib.sha256((str(seed) + ":" + identity).encode("ascii")).digest()
        params["seed"] = int.from_bytes(digest[:4], "little")
        flags = []
        if synth in ("sphere", "save", "music"):
            flags.append("unheard: bell/glass partials may ring or fatigue")
        if synth in ("dialogue", "ui"):
            flags.append("unheard: rapid repetition may feel sharp; throttle in runtime")
        if synth == "cat":
            flags.append("unheard: synthetic cat identity/roughness unverified")
        if synth in ("gust", "ambience", "footstep"):
            flags.append("unheard: noise/hiss balance needs quiet-level review")
        if synth == "saucer":
            flags.append("unheard: resonant sweep may be too prominent")
        entries.append({"id": identity, "synth": synth,
                        "kind": synth if synth in ("ambience", "music") else "sfx",
                        "params": resolve(synth, params),
                        "loop": synth in ("ambience", "music"), "review_flags": flags})

    for surface in ("snow", "floor"):
        for i in range(1, 4):
            add("footstep.{}.{:02d}".format(surface, i), "footstep", surface=surface,
                duration=0.32 if surface == "snow" else 0.24, weight=0.85+i*0.08)
    add("hatch.open", "hatch")
    for action, duration, pitch in (("move", 0.09, 560.0), ("select", 0.16, 660.0), ("back", 0.13, 530.0)):
        add("ui."+action, "ui", action=action, duration=duration, pitch=pitch)
    for name, pitch, brightness, breath, formant in (
            ("low", 125.0, 0.18, 0.015, 550.0),
            ("mid", 165.0, 0.35, 0.025, 850.0),
            ("bright", 210.0, 0.60, 0.012, 1200.0),
            ("airy", 255.0, 0.22, 0.14, 1500.0)):
        add("dialogue."+name, "dialogue", pitch=pitch, brightness=brightness, breath=breath, formant=formant)
    for mode, duration, pitch in (("meow", 0.8, 360.0), ("purr", 1.8, 390.0), ("chirp", 0.35, 490.0)):
        for i in (1, 2):
            add("cat.{}.{:02d}".format(mode, i), "cat", mode=mode,
                duration=duration+(i-1)*0.08, pitch=pitch+(i-1)*37, roughness=0.10+i*0.035)
    for i in range(1, 9):
        add("sphere.pickup.{:02d}".format(i), "sphere", collected=i)
    for identity, synth in (("keycard.accept", "keycard"), ("storm.gust", "gust"),
                            ("pod.hum", "hum"), ("saucer.pass", "saucer"), ("save.tone", "save")):
        add(identity, synth)
    for scene in ("habitat", "outside", "storm"):
        add("ambience."+scene, "ambience", scene=scene)
    for mood in ("hub", "explore"):
        add("music."+mood, "music", mood=mood)
    return sorted(entries, key=lambda entry: entry["id"])


def main(argv=None):
    import argparse
    import json
    from .build import LANE, lane_path
    from .stock_catalog import CATEGORIES, query
    parser = argparse.ArgumentParser(description="Query the offline Hermes64 stock sound index")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("list", "search"):
        sub = commands.add_parser(command)
        if command == "search":
            sub.add_argument("terms", nargs="+")
        sub.add_argument("--category", choices=CATEGORIES)
        sub.add_argument("--tag", action="append", default=[])
        sub.add_argument("--limit", type=int)
        sub.add_argument("--catalog", default=str(LANE/"catalog.json"))
    args = parser.parse_args(argv)
    try:
        index = json.loads(lane_path(args.catalog).read_text(encoding='utf-8'))
        if index.get("schema_version") != "1.1":
            raise ValueError("expected catalog schema 1.1")
        report = query(index, getattr(args,"terms",()), args.category, args.tag, args.limit)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
