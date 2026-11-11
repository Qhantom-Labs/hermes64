"""Mood packs CLI (plan 07 section 2.5, lane A3). Derives a data pack from a shipped base pack + a mood, checks it,
measures look continuity, and (for proofs) installs it into a bundle root with a hash-pinned library + bindings.

  python3 -B -m tools.mood_pack list
  python3 -B -m tools.mood_pack derive --base castle_keep --mood "purple dusk" --out DIR [--id ID] [--no-textures]
        writes DIR/kits/packs/<id>/pack.json, DIR/packs/<id>/{pack.json,view.json}, DIR/mood-report.json
  python3 -B -m tools.mood_pack check --base castle_keep --pack DIR/kits/packs/<id>/pack.json
  python3 -B -m tools.mood_pack look --pack PACK.json --tex-dir DIR [--base PACK.json --base-tex-dir DIR]
  python3 -B -m tools.mood_pack install --bundle ROOT --base castle_keep --mood purple_dusk [--extra K1,K2] [--id ID]
        derive + write into ROOT (a bundle copy), build every base binding key + extras in the derived pack
        (python builder), write ROOT/packs/<id>/bindings.json, env maps and palette table
  python3 -B -m tools.mood_pack matrix                 every shipped pack x every mood (markdown)
  python3 -B -m tools.mood_pack oracle                 hand-written medieval moods vs generic remaps (numbers)
  python3 -B -m tools.mood_pack pins [--check]        docs/amood/pins.json: sha256 of every derived pack for the
                                                       proof bases x the mood list (determinism + drift guard)

Nothing here edits shipped packs. A derived pack is data: id, palette and fog colour names move; roles, materials,
ramps, presets, budgets and thresholds stay byte-identical (kits/core/mood.py check_derived).
"""
import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "kits"))
sys.path.insert(0, str(R))

from core import mood as M  # noqa: E402
from core import look as K  # noqa: E402

PIN_BASES = ("castle_keep", "medieval_village", "stone_dungeon")
PINS = R / "docs" / "amood" / "pins.json"


def jdump(obj):
    return json.dumps(obj, indent=1, sort_keys=True) + "\n"


def add_extras_to_base(bundle, base, keys):
    """Build the wizard pieces in the BASE pack too (scratch bundle only) so base and mood captures match.

    Moved here from tools/mood_demo.py (FINALINT4): place_maker needs only this, and the demo driver stays out of the
    package."""
    from core import pipeline
    from adventure_maker.glb import srgb8, inspect
    bpath = bundle / "packs" / base / "bindings.json"
    doc = json.loads(bpath.read_text(encoding='utf-8'))
    pack_file = bundle / "kits" / "packs" / base / "pack.json"
    for key in keys:
        if key in doc["assets"]:
            continue
        gid, _, pre = key.partition("__")
        out = bundle / "kits" / "library" / base / "amood_extras" / (key + ".glb")
        out.parent.mkdir(parents=True, exist_ok=True)
        st, rep = pipeline.build_one(gid, base, pre or None, {}, 0, str(out), tex_dir=str(out.parent / "textures"),
                                     builder="python", pack_path=str(pack_file))
        if st != "passed":
            raise SystemExit("extra %s in %s: %s" % (key, base, rep.get("error")))
        conv = srgb8(out.read_bytes())
        out.write_bytes(conv)
        doc["assets"][key] = {"glb": str(out.relative_to(bundle)), "kit_id": gid, "preset": pre or None,
                              "sha256": inspect(conv)["sha256"]}
    bpath.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding='utf-8')


def base_kit(base, root=R):
    return json.loads((Path(root) / "kits" / "packs" / base / "pack.json").read_text(encoding='utf-8'))


def base_style(base, root=R):
    d = Path(root) / "packs" / base
    sp = json.loads((d / "pack.json").read_text(encoding='utf-8')) if (d / "pack.json").is_file() else None
    view = json.loads((d / "view.json").read_text(encoding='utf-8')) if (d / "view.json").is_file() else None
    return sp, view


def derive_all(base, mood, new_id=None, textures=True, root=R):
    """-> (kit_pack, style_pack, view, report). Raises SystemExit with the refusal when every strength fails."""
    bible = M.load_bible()
    kit = base_kit(base, root)
    derived, rep = M.derive_checked(kit, mood, bible, new_id, textures=textures)
    if derived is None:
        raise SystemExit("REFUSED: %s + %s: %s" % (base, mood, "; ".join(rep["errors"][:4])))
    sp, view = base_style(base, root)
    out_view = out_sp = None
    if view is not None:
        out_view, cmap = M.derive_view(kit, derived, view, bible)
        hexes = set()
        M._collect_hex(sp or {}, hexes)
        cmap.update(M.colour_map(kit, derived, hexes - set(cmap), bible, M._fog_hexes(sp or {})))
        if sp is not None:
            out_sp = M.derive_style_pack(sp, cmap, derived["id"])
            out_sp["name"] = "%s (%s)" % (sp.get("name", base), derived["mood"]["id"].replace("_", " "))
        vr = M.check_derived(kit, derived, bible, view, out_view)
        if not vr["ok"]:
            raise SystemExit("REFUSED view: " + "; ".join(vr["errors"]))
    rep = dict(rep, id=derived["id"], base=base, mood=derived["mood"]["id"], pack_sha256=M.pack_sha(derived),
               view_sha256=M.pack_sha(out_view) if out_view else None)
    return derived, out_sp, out_view, rep


def write_derived(out, derived, sp, view, rep):
    out = Path(out)
    kd = out / "kits" / "packs" / derived["id"]
    kd.mkdir(parents=True, exist_ok=True)
    (kd / "pack.json").write_text(jdump(derived), encoding='utf-8')
    if view is not None:
        sd = out / "packs" / derived["id"]
        sd.mkdir(parents=True, exist_ok=True)
        (sd / "view.json").write_text(jdump(view), encoding='utf-8')
        if sp is not None:
            (sd / "pack.json").write_text(jdump(sp), encoding='utf-8')
    (out / ("mood-report-%s.json" % derived["id"])).write_text(jdump(rep), encoding='utf-8')
    return kd / "pack.json"


# ------------------------------------------------------------------------------------------------ install (proofs)
def _lib_path(root, pid, gid, preset):
    sub = "presets" if preset else "assets"
    return Path(root) / "kits" / "library" / pid / sub / ("%s%s.glb" % (gid, "__" + preset if preset else ""))


def install(bundle, base, mood, extra=(), new_id=None, quiet=False):
    """Derive into a bundle root and build its library + bindings. Returns the summary dict."""
    from core import pipeline, png
    from core.texgen import make_texture
    from adventure_maker.glb import srgb8, inspect
    bundle = Path(bundle)
    derived, sp, view, rep = derive_all(base, mood, new_id, root=bundle)
    pack_file = write_derived(bundle, derived, sp, view, rep)
    pid = derived["id"]
    bind_base = json.loads((bundle / "packs" / base / "bindings.json").read_text(encoding='utf-8'))
    jobs = {}
    for key, row in bind_base["assets"].items():
        if "alias_of" in row:
            continue
        jobs[key] = (row["kit_id"], row.get("preset"))
    for key in extra:
        gid, _, pre = key.partition("__")
        jobs.setdefault(key, (gid, pre or None))
    tex = bundle / "kits" / "library" / pid / "textures"
    tex.mkdir(parents=True, exist_ok=True)
    assets, failed = {}, {}
    for key, (gid, preset) in sorted(jobs.items()):
        out = _lib_path(bundle, pid, gid, preset)
        out.parent.mkdir(parents=True, exist_ok=True)
        st, r = pipeline.build_one(gid, pid, preset, {}, 0, str(out), tex_dir=str(tex), builder="python",
                                   pack_path=str(pack_file))
        if st != "passed":
            failed[key] = (r.get("error") or str([k for k, v in (r.get("validation") or {}).items() if not v["ok"]]))[:200]
            continue
        conv = srgb8(out.read_bytes())
        out.write_bytes(conv)
        assets[key] = {"glb": str(out.relative_to(bundle)), "kit_id": gid, "preset": preset,
                       "sha256": inspect(conv)["sha256"]}
    for key, row in bind_base["assets"].items():
        if "alias_of" in row and row["alias_of"] in assets:
            assets[key] = dict(assets[row["alias_of"]], alias_of=row["alias_of"])
    doc = {"format": 1, "pack": pid, "kit_pack": pid,
           "note": "Mood pack bindings (tools/mood_pack.py install): every %s binding key rebuilt in %s; hash-pinned." % (base, pid),
           "assets": dict(sorted(assets.items()))}
    (bundle / "packs" / pid / "bindings.json").write_text(jdump(doc), encoding='utf-8')
    pk = pipeline.get_pack(pid, str(pack_file))
    env = bundle / "kits" / "library" / pid / "env"
    env.mkdir(parents=True, exist_ok=True)
    for name, spec in sorted(pk.env_maps.items()):
        (env / (name + ".png")).write_bytes(png.encode(make_texture(spec, pk.pal, pk.seed_id, name)))
    (bundle / "kits" / "library" / pid / "palette.json").write_text(jdump(
        {"pack_id": pid, "colors": list(pk.d["palette"]), "names": list(pk.pal.names),
         "roles": pk.d.get("palette_roles", {}), "light_ramp": list(pk.light_ramp)}), encoding='utf-8')
    summary = {"id": pid, "built": len(assets), "failed": failed, "pack_sha256": rep["pack_sha256"],
               "strength": rep.get("strength"), "clamped": rep.get("clamped")}
    if not quiet:
        print(json.dumps({k: (v if k != "failed" else len(v)) for k, v in summary.items()}))
    return summary


# ------------------------------------------------------------------------------------------------ oracle
def oracle():
    """Plan 2.5 oracle: mean OKLab distance per palette name between each hand-written medieval mood and (a) the
    base, (b) every generic mood derived from the base. Numbers only; tells how far generic is from hand-tuned."""
    bible = M.load_bible()
    base = base_kit("medieval_village")

    def de(p, q):
        pb, qb = dict(zip(p["palette_names"], p["palette"])), dict(zip(q["palette_names"], q["palette"]))
        return round(sum(M.oklab_de(pb[n], qb[n]) for n in pb) / len(pb), 4)
    out = {}
    for hand in ("medieval_village_dusk", "medieval_village_night", "medieval_village_snow"):
        h = base_kit(hand)
        row = {"base": de(base, h)}
        for m in M.mood_names():
            d, _ = M.derive_checked(base, m, bible, textures=False)
            row[m] = de(d, h) if d else None
        out[hand] = row
    return out


def matrix():
    """Markdown table: every shipped kit pack x every mood -> ok / ok @strength / refused: reason."""
    bible = M.load_bible()
    names = M.mood_names()
    lines = ["| base | " + " | ".join(names) + " |", "|" + "---|" * (len(names) + 1)]
    for p in sorted(x.name for x in (R / "kits" / "packs").iterdir() if (x / "pack.json").is_file()):
        base = base_kit(p)
        cells = []
        for m in names:
            d, r = M.derive_checked(base, m, bible)
            cells.append("refused: " + r["errors"][0].replace("look: ", "")[:70] if d is None else
                         ("ok" if not r["clamped"] else "ok @%.2f" % r["strength"]))
        lines.append("| %s | %s |" % (p, " | ".join(cells)))
    return "\n".join(lines)


# ------------------------------------------------------------------------------------------------ pins
def pins_doc():
    rows = {}
    for b in PIN_BASES:
        for m in M.mood_names():
            try:
                d, _, v, rep = derive_all(b, m)
                rows["%s+%s" % (b, m)] = {"pack_sha256": rep["pack_sha256"], "view_sha256": rep["view_sha256"],
                                          "strength": rep.get("strength")}
            except SystemExit as e:
                rows["%s+%s" % (b, m)] = {"refused": str(e)[:200]}
    return {"mood_version": M.MOOD_VERSION, "bible_sha256": hashlib.sha256((R / "kits/core/style_bible.json").read_bytes()).hexdigest(),
            "moods_sha256": M.mood_sha(M.MOODS), "packs": rows}


def main(argv):
    ap = argparse.ArgumentParser(prog="mood_pack")
    ap.add_argument("cmd", choices=["list", "derive", "check", "look", "install", "pins", "oracle", "matrix"])
    ap.add_argument("--base")
    ap.add_argument("--mood")
    ap.add_argument("--id")
    ap.add_argument("--out")
    ap.add_argument("--pack")
    ap.add_argument("--tex-dir")
    ap.add_argument("--base-tex-dir")
    ap.add_argument("--bundle")
    ap.add_argument("--extra", default="")
    ap.add_argument("--no-textures", action="store_true")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for mid in M.mood_names():
            m = M.MOODS[mid]
            print("%-13s %-8s %-7s accent %-8s %-11s value %-4s words: %s" % (
                mid, m["dominant"], m["support"], m["accent"], m["time"], m["value_key"], ", ".join(m["words"])))
        return 0
    if a.cmd == "derive":
        d, sp, v, rep = derive_all(a.base, a.mood, a.id, textures=not a.no_textures)
        p = write_derived(a.out, d, sp, v, rep)
        print(json.dumps({"pack": str(p), "id": d["id"], "sha256": rep["pack_sha256"], "strength": rep.get("strength"),
                          "clamped": rep.get("clamped"), "numbers": rep.get("numbers")}))
        return 0
    if a.cmd == "check":
        base = base_kit(a.base)
        d = json.loads(Path(a.pack).read_text(encoding='utf-8'))
        r = M.check_derived(base, d)
        print(json.dumps(r, indent=1))
        return 0 if r["ok"] else 3
    if a.cmd == "look":
        d = json.loads(Path(a.pack).read_text(encoding='utf-8'))
        tex = K.read_textures(a.tex_dir, d["id"])
        bt = bp = None
        if a.base and a.base_tex_dir:
            bp = json.loads(Path(a.base).read_text(encoding='utf-8'))
            bt = K.read_textures(a.base_tex_dir, bp["id"])
        r = K.continuity(tex, d, bt, bp)
        print(json.dumps({"ok": r["ok"], "errors": r["errors"], "set": r["set"]}, indent=1))
        return 0 if r["ok"] else 3
    if a.cmd == "install":
        s = install(a.bundle, a.base, a.mood, [x for x in a.extra.split(",") if x], a.id)
        return 0 if not s["failed"] else 3
    if a.cmd == "matrix":
        print(matrix())
        return 0
    if a.cmd == "oracle":
        print(json.dumps(oracle(), indent=1))
        return 0
    if a.cmd == "pins":
        doc = pins_doc()
        text = jdump(doc)
        if a.check:
            ok = PINS.is_file() and PINS.read_text(encoding='utf-8') == text
            print("pins", "ok" if ok else "STALE")
            return 0 if ok else 3
        PINS.parent.mkdir(parents=True, exist_ok=True)
        PINS.write_text(text, encoding='utf-8')
        print("wrote", PINS.relative_to(R), len(doc["packs"]), "rows")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
