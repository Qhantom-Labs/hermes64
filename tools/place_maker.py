"""PLACEMAKER CLI: make a type of place, render it in the real runtime, measure it, retry within bounds, record it.

  python3 -B -m tools.place_maker list
  python3 -B -m tools.place_maker plan  ARCH [--size S] [--mood M] [--clutter N] [--seed N]   # plan + static checks
  python3 -B -m tools.place_maker diagram ARCH ... --out plan.png                            # top-down plan picture
  python3 -B -m tools.place_maker make  ARCH [...] [--attempts 3] [--run NAME]               # render-and-measure loop
  python3 -B -m tools.place_maker approve --run DIR --room ID --by NAME [--note T] [--store DIR] [--synthetic]
  python3 -B -m tools.place_maker compare --run DIR --room ID [--store DIR]
  python3 -B -m tools.place_maker examples ARCH [--store DIR] [--with-synthetic]
  python3 -B -m tools.place_maker determinism ARCH [...]                                    # same seed -> same bytes

make clones this worktree into a scratch bundle (APFS clone; the shipped tree is never written), installs the mood
pack and any generator recipes the plan needs there, builds every attempt through the plugin's normal Service path
(scaffold -> compile -> check -> build_assets -> open with screenshots), runs the style gate, the n64 fidelity gate
and the reference-band measure on each room's game-camera frame, and keeps the best attempt. Every attempt is
recorded in <run>/report.json and <run>/report.txt. Bounded adjustments only: clutter, spacing, seed re-roll,
light energy 0.85-1.15, camera pull 0-0.3. Nothing here gives a look verdict.
"""
import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "kits"))
sys.path.insert(0, str(R))

from adventure_maker import place  # noqa: E402
from adventure_maker.place import PlaceError  # noqa: E402
from adventure_maker.runner import scratch_env  # noqa: E402
from tools import place_measure as PM  # noqa: E402

SCRATCH = Path(os.environ.get("PLACEMAKER_BUNDLE") or (Path.home() / ".hermes" / "cache" / "scratch" / "placemaker-bundle")).resolve()
EVID = R / "evidence" / "placemaker"
GAME = "place_maker"
MAX_PLANS = 6
LIGHT_STEP = 0.07


# ----------------------------------------------------------------------------------------------- bundle + packs
def clone_bundle(dest=SCRATCH, fresh=False):
    if dest.exists() and not fresh and (dest / "adventure_maker" / "place.py").is_file():
        # keep installed packs; refresh code + data from the worktree
        for sub in ("adventure_maker", "tools", "kits/places", "kits/core", "contracts", "catalog"):
            src, dst = R / sub, dest / sub
            if dst.exists():
                shutil.rmtree(dst)
            with scratch_env() as env:
                subprocess.run(["cp", "-cR", str(src), str(dst)], check=True, env=env)
        return dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with scratch_env() as env:
        subprocess.run(["cp", "-cR", str(R), str(dest)], check=True, env=env)
    for sub in ("evidence", ".git", "place_approvals"):
        p = dest / sub
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    return dest


def ensure_pack(bundle, res, log):
    """Make sure res['pack'] exists in the bundle with every key the plan uses (recipes built into it)."""
    from tools import mood_pack
    from tools.mood_pack import add_extras_to_base
    doc = (res.get("archetype_doc") or place.load_archetype(res["archetype"]))
    pack, how = res["pack"], res["mood"]["how"]
    keys = sorted(set(res["recipes"]))
    bpath = bundle / "packs" / pack / "bindings.json"
    t0 = time.monotonic()
    if how == "derive" and not bpath.is_file():
        inst = mood_pack.install(bundle, doc["base_pack"], res["params"]["mood"], keys, quiet=True)
        log.append({"install": pack, "seconds": round(time.monotonic() - t0, 1), "failed": inst.get("failed"),
                    "strength": inst.get("strength"), "clamped": inst.get("clamped")})
    if not bpath.is_file():
        return sorted(keys) or ["pack %s not installed" % pack]
    have = json.loads(bpath.read_text(encoding='utf-8'))["assets"]
    need = [k for k in keys if k not in have]
    if need:
        try:
            add_extras_to_base(bundle, pack, need)
            log.append({"recipes_built": need, "pack": pack, "seconds": round(time.monotonic() - t0, 1)})
        except (Exception, SystemExit) as e:          # recorded; the attempt reports the unbuilt pieces
            log.append({"recipes_failed": need, "pack": pack, "error": str(e)[:300]})
    have = json.loads(bpath.read_text(encoding='utf-8'))["assets"]
    used = {r["key"] for r in res["placements"]} | {p["key"] for p in res["plan"]["pieces"]}
    missing = sorted(k for k in used if k not in have)
    return missing


# ----------------------------------------------------------------------------------------------- spec
def spec_for(rows, pack, game=GAME):
    """A STORY 1.2.0 game: every place room plus a plain 'lobby' that holds the other end of each door (region links
    cannot be self links). Rooms with only virtual openings are entered from the lobby list (no door)."""
    binds = {r["character_id"]: r for r in json.loads((R / "bindings.json").read_text(encoding='utf-8'))["characters"]}
    src = binds["fv_scribe"]
    chars = [{"id": place.PROTAGONIST, "name": "[Visitor]", "role": "visitor", "body_id": src["body_id"],
              "base_rig_id": src["base_rig_id"], "params": src["params"], "role_profiles": {"visitor": src["params"]}}]
    rooms, pres, links, regions, checkpoints = [], {}, [], [], []
    lobby_doors = []
    for i, (res, room, pr, rep) in enumerate(rows):
        rooms.append(room)
        pres[room["id"]] = pr
        z = res["zones"]
        doc = (res.get("archetype_doc") or place.load_archetype(res["archetype"]))
        fp = next(f for f in doc["footprints"] if f["size"] == res["footprint"])
        e = next(d for d in z["doors"] if d["id"] == fp["entrance"]["id"])
        nx, nz = place.WALL_NORMAL[e["side"]]
        cp = [round(e["point_m"][0] + nx * 1.6, 2), 0, round(e["point_m"][1] + nz * 1.6, 2)]
        checkpoints.append({"id": room["id"] + "_safe", "room": room["id"], "position_m": cp})
        regions.append({"id": room["id"], "room": room["id"], "checkpoint": room["id"] + "_safe",
                        "landmarks": [{"id": "focal", "name": "Focal point", "position_m": [z["focal_m"][0], 0, z["focal_m"][1]]}]})
        for d in room["doors"]:
            ld = "to_%s_%s" % (room["id"], d["id"])
            lobby_doors.append({"id": ld, "wall": "north", "position": 1 + 2 * len(lobby_doors), "to_room": room["id"],
                                "to_door": d["id"], "label": "Enter " + room["name"], "conditions": []})
            links.append({"id": "%s__%s" % (room["id"], d["id"]), "a": {"region": room["id"], "door": d["id"]},
                          "b": {"region": "lobby", "door": ld}})
    width = max(6, 2 * len(lobby_doors) + 2)
    lobby = {"id": "lobby", "name": "Lobby", "description": "A plain room that holds the other end of every door.",
             "grid_size": [width, 6], "kit_refs": [], "doors": lobby_doors,
             "cameras": [{"id": "game", "position": [width / 2.0, 4.0, 6.5], "look_at": [width / 2.0, 0.0, 2.0]}],
             "props": [], "character_ids": [place.PROTAGONIST]}
    rooms.append(lobby)
    checkpoints.append({"id": "lobby_safe", "room": "lobby", "position_m": [width / 2.0, 0, 4.0]})
    regions.append({"id": "lobby", "room": "lobby", "checkpoint": "lobby_safe",
                    "landmarks": [{"id": "lobby_mark", "name": "Lobby", "position_m": [width / 2.0, 0, 3.0]}]})
    first = rows[0][1]["id"]
    return {"contract_version": "1.2.0", "id": game, "title": "Place maker", "description": "PLACEMAKER render run.",
            "characters": chars, "collectible_groups": [], "collectibles": [], "dialogues": [], "items": [], "quests": [],
            "flags": [{"id": "seen", "description": "Looked around", "initial": False}],
            "endings": [{"id": "done", "text": "Done.", "conditions": [{"flag": "seen", "equals": True}]}],
            "interactions": [{"id": "look", "room": first, "kind": "examine", "target": "focal", "label": "Look around",
                              "text": "You look around.", "conditions": [], "effects": [{"flag": "seen", "value": True}]}],
            "gameplay": {"api_version": "1.0.0", "seed": 7, "verification_policy": "conditional", "modules": [
                {"id": "abilities", "version": "1.0.0", "config": {"max_health": 6}, "entities": {"abilities": []}},
                {"id": "challenge", "version": "1.0.0", "config": {"entry_cost": "none", "failure_progress": "unchanged", "max_active": 1},
                 "entities": {"challenges": [], "checkpoints": checkpoints}},
                {"id": "regions", "version": "1.0.0", "config": {"fast_travel": False, "load_policy": "one_region"},
                 "entities": {"links": links, "regions": regions}}]},
            "rooms": rooms,
            "start": {"collected": [], "dialogue": {}, "flags": {"seen": False}, "inventory": [], "location": first,
                      "modules": {"abilities": [], "active": "", "checkpoint": first + "_safe", "completed": [],
                                  "discovered": [first], "failed": ""}, "tide": {"state": "now", "tick": 0}},
            "tide": {"id": "time", "states": [{"id": "now", "duration": 1, "label": "Now"}], "wait_label": "Wait",
                     "wait_text": "A moment passes."},
            "metadata": {"protagonist": place.PROTAGONIST, "style_pack": pack,
                         "presentation": {"convention": "hermes64-presentation/1", "rotation_order": "YXZ",
                                          "rotation_units": "degrees", "rooms": pres}}}


def compile_for_game(res, room_id):
    """Compile one attempt with a unique room id and every real door pointed at the lobby."""
    r2 = copy.deepcopy(res)
    r2["plan"]["id"] = room_id
    targets = {d["id"]: ("lobby", "to_%s_%s" % (room_id, d["id"]), "Back to the lobby") for d in r2["plan"]["doors"]}
    room, pres, rep = place.compile(r2, targets)
    return r2, room, pres, rep


# ----------------------------------------------------------------------------------------------- capture + measure
def capture(bundle, rows, pack, out, seconds=40):
    """Build rows (list of (res, room, pres, rep)) as one game in the bundle, open it with screenshots, gate it."""
    from adventure_maker.service import Service
    from adventure_maker import style_gate, n64_gate
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    projects = out / "projects"
    projects.mkdir()
    for res, room, pres, rep in rows:
        if res["params"]["light"] != 1.0 or res["params"].get("contrast"):
            pres["look"] = place.light_override(pack, res["plan"]["look_profile"], res["params"]["light"], root=bundle,
                                                contrast=res["params"].get("contrast", 0.0))
    svc = Service({"bundle_root": str(bundle), "projects_root": str(projects)})
    log = []

    def call(name, **args):
        t0 = time.monotonic()
        r = json.loads(svc.handle("hermes64_" + name, dict(project=GAME, **args)))
        if r.get("truncated"):
            r = json.loads((projects / GAME / r["report_path"]).read_text(encoding='utf-8'))
        log.append({"tool": name, "seconds": round(time.monotonic() - t0, 1), "status": r.get("status", r.get("error"))})
        (out / "calls.json").write_text(json.dumps(log, indent=1, default=str), encoding='utf-8')
        if not r.get("ok") and name != "open":
            (out / (name + ".json")).write_text(json.dumps(r, indent=1, default=str)[:200000], encoding='utf-8')
            raise RuntimeError("%s failed: %s" % (name, json.dumps(r.get("error", r))[:600]))
        return r
    spec = spec_for(rows, pack)
    (out / "spec.json").write_text(json.dumps(spec, indent=1, sort_keys=True), encoding='utf-8')
    call("scaffold", pack=pack, spec_json=json.dumps(spec))
    call("compile", spec_path="source/spec.json")
    call("check")
    call("build_assets", seed=7)
    opened = call("open", seconds=seconds, screenshots=True)
    cap = opened.get("capture")
    if not isinstance(cap, dict):
        raise RuntimeError("capture failed: %s" % json.dumps(opened)[:600])
    run = projects / GAME / Path(opened["report_path"]).parent
    dest = out / "screens"
    shutil.copytree(run / "screens", dest)
    theme = json.loads((run / "runtime" / "theme.json").read_text(encoding='utf-8'))
    sg = style_gate.gate_directory(dest, theme)
    ng = n64_gate.gate_folder(dest, theme)
    (out / "style-gate.json").write_text(json.dumps(sg, indent=1, default=str), encoding='utf-8')
    (out / "n64-fidelity.json").write_text(json.dumps(ng, indent=1, default=str), encoding='utf-8')
    shutil.rmtree(projects, ignore_errors=True)
    rooms = {}
    fid = {r["id"]: r for r in ng.get("rooms", [])}
    tri = {r["id"]: r for r in cap.get("rooms", [])}
    for r in sg.get("rooms", []):
        rid = r["id"]
        frame = dest / (rid + "-clean.png")
        st = PM.frame_stats(frame) if frame.is_file() else {}
        rooms[rid] = {"style_gate": r["status"], "style_reasons": r.get("reasons", []),
                      "style_metrics": {k: r.get("metrics", {}).get(k) for k in (
                          "palette_adherence", "contrast_range", "mean_luma", "flat_fraction", "accent_fraction",
                          "fog_swallowed_fraction", "edge_density")},
                      "n64": fid.get(rid, {}).get("status"), "n64_reasons": fid.get(rid, {}).get("reasons", []),
                      "triangles": tri.get(rid, {}).get("triangles"),
                      "triangles_split": tri.get(rid, {}).get("triangles_split"),
                      "floating": (tri.get(rid, {}).get("audit") or {}).get("floating"),
                      "uncut_doors": (tri.get(rid, {}).get("audit") or {}).get("uncut_doors"),
                      "frame": str(frame), "closeup": str(dest / (rid + "-closeup.png")),
                      "stats": {k: v for k, v in st.items() if k != "hue_hist"},
                      "band": PM.band_score(st) if st else None,
                      "palette": PM.palette_vector(frame) if frame.is_file() else None}
    return {"rooms": rooms, "missing_assets": cap.get("missing_assets"), "capture_status": cap.get("status"),
            "calls": log, "gate": sg.get("status"), "n64": ng.get("status")}


def render_ok(m):
    reasons = []
    if m["style_gate"] != "passed":
        reasons.append("style gate: " + "; ".join(m["style_reasons"][:2]))
    if m["n64"] != "passed":
        reasons.append("n64: " + "; ".join(str(x) for x in m["n64_reasons"][:2]))
    if not (m.get("band") or {}).get("ok"):
        reasons.append("reference band %.2f < %.2f (out: %s)" % ((m.get("band") or {}).get("score", 0), PM.BAND_MIN,
                                                                 ", ".join((m.get("band") or {}).get("out_of_band", []))))
    if m.get("floating"):
        reasons.append("floating pieces: %s" % m["floating"])
    return not reasons, reasons


def score(att):
    """Ranking only (best attempt): static ok, render ok, then reference-band score."""
    r = att.get("render") or {}
    return (1 if att["static"]["ok"] else 0, 1 if r.get("ok") else 0, (r.get("band") or {}).get("score", 0),
            -len(att["static"]["failures"]))


# ----------------------------------------------------------------------------------------------- adjustment policy
def adjust_static(p, failures, k):
    q = dict(p)
    text = " ".join(failures)
    if "over budget" in text or "clear floor" in text:
        if q["clutter"] > 0:
            q["clutter"] -= 1
            return q, "clutter -1 (%s)" % failures[0]
        if q["spacing"] < 1.6:
            q["spacing"] = round(min(1.6, q["spacing"] + 0.2), 3)
            return q, "spacing +0.2 (%s)" % failures[0]
    q["seed"] = (p["seed"] + 7919 * (k + 1)) % (2 ** 31)
    return q, "seed re-roll (%s)" % (failures[0] if failures else "?")


def adjust_render(p, reasons, k):
    """Gate reason -> one bounded knob. Rules are explicit phrases from the style / n64 gates, checked in order."""
    q = dict(p)
    text = " ".join(reasons).lower()
    if "low contrast" in text or "washed out" in text or "no real darks" in text:
        if q.get("contrast", 0.0) + 0.1 <= 0.2 + 1e-9:
            q["contrast"] = round(q.get("contrast", 0.0) + 0.1, 3)
            return q, "contrast +0.1 (ambient down, key up)"
        if "low contrast" in text and q["light"] + LIGHT_STEP <= 1.15 + 1e-9:
            q["light"] = round(q["light"] + LIGHT_STEP, 3)
            return q, "light +%.2f" % LIGHT_STEP
    if "too dark" in text or "too dim" in text or "mean luma" in text and "low" in text:
        if q["light"] + LIGHT_STEP <= 1.15 + 1e-9:
            q["light"] = round(q["light"] + LIGHT_STEP, 3)
            return q, "light +%.2f" % LIGHT_STEP
    if "neon" in text or "too bright" in text or "blown" in text:
        if q["light"] - LIGHT_STEP >= 0.85 - 1e-9:
            q["light"] = round(q["light"] - LIGHT_STEP, 3)
            return q, "light -%.2f" % LIGHT_STEP
    if "fog" in text and q["camera_pull"] + 0.15 <= 0.3 + 1e-9:
        q["camera_pull"] = round(q["camera_pull"] + 0.15, 3)
        return q, "camera pull +0.15"
    if "reference band" in text and "flat" in text and q["clutter"] < 3:
        q["clutter"] += 1
        return q, "clutter +1"
    if "reference band" in text and "edges" in text and q["clutter"] > 0:
        q["clutter"] -= 1
        return q, "clutter -1"
    q["seed"] = (p["seed"] + 104729 * (k + 1)) % (2 ** 31)
    return q, "seed re-roll"


def static_attempt(arch, params, attempts):
    """Plan + compile + static checks, adjusting within bounds until static passes or MAX_PLANS is used."""
    p = dict(params)
    for k in range(MAX_PLANS):
        try:
            res = place.make_plan(arch, p)
            room, pres, rep = place.compile(res)
            st = place.static_checks(res, room, pres, rep)
        except PlaceError as e:
            attempts.append({"n": len(attempts) + 1, "params": p, "refused": str(e), "static": {"ok": False, "failures": [str(e)]}})
            if "required group" in str(e) or "kit compiler" in str(e):
                q, why = adjust_static(p, [str(e)], k)
                attempts[-1]["next"] = why
                p = q
                continue
            raise
        att = {"n": len(attempts) + 1, "params": res["params"], "plan_sha256": res["plan_sha256"], "static": st,
               "layout": res["layout"], "pieces": res["layout"]["pieces"], "tri_estimate": rep.get("tri_estimate")}
        attempts.append(att)
        if st["ok"]:
            return res, att
        q, why = adjust_static(res["params"], st["failures"], k)
        att["next"] = why
        p = q
    return None, None


def make_many(requests, run, seconds=40, render_rounds=3, bundle=None, fresh=False):
    """requests: [{"name", "archetype", "params"}]. Rounds: each unfinished request proposes a static-clean attempt;
    all proposals sharing a pack are captured in ONE game; failures adjust and go again (<= render_rounds)."""
    out = EVID / run
    out.mkdir(parents=True, exist_ok=True)
    bundle = clone_bundle(bundle or SCRATCH, fresh=fresh)
    state = {r["name"]: {"req": r, "attempts": [], "params": place.resolve_params(place.validate(place.load_archetype(r["archetype"])), r["params"]),
                         "done": False, "best": None} for r in requests}
    installs = []
    for rnd in range(1, render_rounds + 1):
        batch = {}
        for name, s in state.items():
            if s["done"]:
                continue
            res, att = static_attempt(s["req"]["archetype"], s["params"], s["attempts"])
            if res is None:
                s["done"] = True
                s["note"] = "no static-clean plan within %d plans" % MAX_PLANS
                continue
            rid = "%s_r%d" % (name, rnd)
            att["room_id"] = rid
            att["round"] = rnd
            missing = ensure_pack(bundle, res, installs)
            if missing:
                att["render"] = {"ok": False, "reasons": ["not built in pack: %s" % ", ".join(missing)]}
                s["done"] = True
                continue
            r2, room, pres, rep = compile_for_game(res, rid)
            batch.setdefault(res["pack"], []).append((name, att, (r2, room, pres, rep)))
        if not batch:
            break
        for pack, items in sorted(batch.items()):
            cdir = out / ("round%d-%s" % (rnd, pack))
            try:
                cap = capture(bundle, [x[2] for x in items], pack, cdir, seconds)
            except Exception as e:      # a whole-game failure is recorded for every attempt in it
                for name, att, _ in items:
                    att["render"] = {"ok": False, "reasons": ["capture: %s" % str(e)[:300]]}
                continue
            for name, att, row in items:
                m = cap["rooms"].get(att["room_id"])
                if m is None:
                    att["render"] = {"ok": False, "reasons": ["no frame for room"]}
                    continue
                ok, reasons = render_ok(m)
                att["render"] = dict(m, ok=ok, reasons=reasons, capture_dir=str(cdir.relative_to(R)),
                                     missing_assets=cap["missing_assets"])
                att["plan"] = row[0]["plan"]
                att["result"] = {k: row[0][k] for k in ("archetype", "pack", "mood", "footprint", "zones", "gaps",
                                                        "wants", "trims", "short", "recipes", "groups", "tris")}
        for name, s in state.items():
            if s["done"]:
                continue
            last = s["attempts"][-1]
            if (last.get("render") or {}).get("ok"):
                s["done"] = True
                continue
            if rnd < render_rounds:
                q, why = adjust_render(last["params"], (last.get("render") or {}).get("reasons", []), rnd)
                last["next"] = why
                s["params"] = q
    report = {"run": run, "bundle": str(bundle), "installs": installs, "requests": {}}
    for name, s in state.items():
        rendered = [a for a in s["attempts"] if "render" in a]
        best = max(rendered, key=score) if rendered else (max(s["attempts"], key=score) if s["attempts"] else None)
        report["requests"][name] = {"archetype": s["req"]["archetype"], "asked": s["req"]["params"],
                                    "attempts_used": len(s["attempts"]), "renders_used": len(rendered),
                                    "best": best and best["n"], "passed": bool(best and best["static"]["ok"] and (best.get("render") or {}).get("ok")),
                                    "note": s.get("note"), "attempts": s["attempts"]}
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str, sort_keys=True), encoding='utf-8')
    (out / "report.txt").write_text("\n".join(report_text(report)) + "\n", encoding='utf-8')
    return report


def report_text(report):
    lines = ["PLACEMAKER run %s (numbers only; looks are for the owner to judge)" % report["run"]]
    for i in report["installs"]:
        lines.append("install: %s" % json.dumps(i, sort_keys=True))
    for name, r in sorted(report["requests"].items()):
        lines.append("")
        lines.append("%s  [%s]  asked %s  attempts %d (renders %d)  best #%s  %s" % (
            name, r["archetype"], json.dumps(r["asked"], sort_keys=True), r["attempts_used"], r["renders_used"],
            r["best"], "all checks passed" if r["passed"] else "NOT all checks passed"))
        for a in r["attempts"]:
            st = a["static"]
            ren = a.get("render")
            p = a["params"]
            s = "  #%d size %s mood %s clutter %d seed %d light %.2f contrast %.2f pull %.2f: static %s" % (
                a["n"], p["size"], p["mood"], p["clutter"], p["seed"], p["light"], p.get("contrast", 0.0), p["camera_pull"],
                "ok" if st["ok"] else "FAIL (%s)" % "; ".join(st["failures"][:2]))
            if st.get("clear_square_m") is not None:
                s += " clear %.2f m reach %d/%d cov %.3f" % (st["clear_square_m"], sum(1 for v in st["reachable"].values() if v),
                                                            len(st["reachable"]), st["coverage"])
            if ren:
                b = ren.get("band") or {}
                s += " | render %s: style %s n64 %s band %.2f tris %s" % (
                    "ok" if ren.get("ok") else "FAIL", ren.get("style_gate"), ren.get("n64"), b.get("score", 0),
                    ren.get("triangles"))
                if ren.get("reasons"):
                    s += " (%s)" % "; ".join(ren["reasons"][:2])
            if a.get("next"):
                s += " -> next: " + a["next"]
            lines.append(s)
    return lines


# ----------------------------------------------------------------------------------------------- diagram
def diagram(res, out, scale=24):
    """Top-down picture of a plan: floor, zones, footprints by group (mechanical view for checking placement)."""
    from PIL import Image, ImageDraw
    doc = (res.get("archetype_doc") or place.load_archetype(res["archetype"]))
    fp = next(f for f in doc["footprints"] if f["size"] == res["footprint"])
    w, d = fp["plot_cells"][0] * 4 + 1, fp["plot_cells"][1] * 4 + 1
    pad = 30
    im = Image.new("RGB", (int(w * scale) + 2 * pad, int(d * scale) + 2 * pad + 40), (24, 24, 28))
    dr = ImageDraw.Draw(im)

    def P(x, z):
        return (pad + x * scale, pad + z * scale)
    z = res["zones"]
    dr.rectangle([P(0, 0), P(w, d)], outline=(90, 90, 90))
    dr.rectangle([P(*z["floor_rect_m"][:2]), P(*z["floor_rect_m"][2:])], outline=(200, 200, 200), fill=(44, 44, 50))
    if z.get("fight_rect_m"):
        dr.rectangle([P(*z["fight_rect_m"][:2]), P(*z["fight_rect_m"][2:])], outline=(220, 80, 80))
    dr.rectangle([P(*z["entrance_rect_m"][:2]), P(*z["entrance_rect_m"][2:])], outline=(80, 200, 120))
    pts = [P(*p) for p in z["path_m"]]
    dr.line(pts, fill=(80, 160, 220), width=max(2, int(z["path_width_m"] * scale)))
    palette = [(230, 180, 60), (120, 200, 230), (200, 120, 220), (120, 220, 120), (240, 120, 100), (180, 180, 120),
               (100, 140, 240), (240, 200, 160), (160, 240, 200), (220, 100, 160), (140, 120, 90), (200, 200, 255)]
    groups = [g["group"] for g in res["groups"]]
    for r in res["placements"]:
        col = palette[groups.index(r["group"]) % len(palette)] if r["group"] in groups else (255, 255, 255)
        if "lot" in r:
            continue
        try:
            rc = place.rect_of(r["key"], r["at_m"][0], r["at_m"][1], r["yaw"], doc["base_pack"])
        except PlaceError:
            continue
        dr.rectangle([P(rc[0], rc[1]), P(rc[2], rc[3])], outline=col, fill=None if r.get("mounted") else tuple(c // 3 for c in col))
        dr.text(P(r["at_m"][0] - 0.3, r["at_m"][1] - 0.2), r["group"][:6], fill=col)
    fx, fz = z["focal_m"]
    dr.ellipse([P(fx - 0.3, fz - 0.3), P(fx + 0.3, fz + 0.3)], outline=(255, 255, 255))
    p = res["params"]
    dr.text((pad, int(d * scale) + pad + 8), "%s %s mood %s clutter %d seed %d  plan %s" % (
        res["archetype"], p["size"], p["mood"], p["clutter"], p["seed"], res["plan_sha256"][:12]), fill=(230, 230, 230))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


# ----------------------------------------------------------------------------------------------- determinism
def determinism(arch, params, runs=2, fn=None):
    """Same archetype + params -> same plan bytes; returns {"same": bool, "sha256": [...]}."""
    fn = fn or (lambda: place.plan_bytes(place.make_plan(arch, params)))
    import hashlib
    shas = [hashlib.sha256(fn()).hexdigest() for _ in range(runs)]
    return {"same": len(set(shas)) == 1, "sha256": shas}


# ----------------------------------------------------------------------------------------------- proof sheets
def best_attempt(r):
    rendered = [a for a in r["attempts"] if a.get("render") and a["render"].get("frame")]
    return max(rendered, key=score) if rendered else None


def recapture_view(report, view, seconds=40):
    """Capture every request's best attempt again from standard camera <view> (b/c/d), one game per pack."""
    run = report["run"]
    bundle = Path(report["bundle"])
    batch = {}
    for name, r in sorted(report["requests"].items()):
        att = best_attempt(r)
        if not att:
            continue
        res = place.make_plan(att["result"]["archetype"], att["params"])
        if res["plan_sha256"] != att["plan_sha256"]:
            raise RuntimeError("replan of %s gave a different plan (determinism broken)" % name)
        res["plan"]["camera"] = res["plan"]["cameras"][view]
        rid = "%s_%s" % (name, view)
        r2, room, pres, rep = compile_for_game(res, rid)
        batch.setdefault(res["pack"], []).append((name, rid, (r2, room, pres, rep)))
    for pack, items in sorted(batch.items()):
        cap = capture(bundle, [x[2] for x in items], pack, EVID / run / ("view-%s-%s" % (view, pack)), seconds)
        for name, rid, _ in items:
            m = cap["rooms"].get(rid) or {}
            report["requests"][name].setdefault("views", {})[view] = {
                k: m.get(k) for k in ("frame", "closeup", "style_gate", "n64", "triangles", "band", "style_metrics")}
    (EVID / run / "report.json").write_text(json.dumps(report, indent=1, default=str, sort_keys=True), encoding='utf-8')
    return report


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _numbers(name, r, att):
    st, ren = att["static"], att["render"]
    p = att["params"]
    b = ren.get("band") or {}
    return ["%s  %s  size %s  mood %s (%s)  clutter %d  seed %d  light %.2f" % (
                name, r["archetype"], p["size"], p["mood"], att["result"]["pack"], p["clutter"], p["seed"], p["light"]),
            "runtime triangles %s  tri estimate %s  pieces %d  clear square %.2f m (rule %.2f)  reachable %d/%d  coverage %.3f" % (
                ren.get("triangles"), att.get("tri_estimate"), att["pieces"], st["clear_square_m"], st["min_clear_m"],
                sum(1 for v in st["reachable"].values() if v), len(st["reachable"]), st["coverage"]),
            "style gate %s  n64 %s  reference band %.2f (%d/%d in p10-p90)  attempts %d (renders %d)  plan %s" % (
                ren.get("style_gate"), ren.get("n64"), b.get("score", 0), len(b.get("in_band", [])),
                len(b.get("in_band", [])) + len(b.get("out_of_band", [])), r["attempts_used"], r["renders_used"],
                att["plan_sha256"][:12])]


def sheets(report, out_dir):
    """Contact sheet per archetype (game camera a, camera b, plan diagram per room) + numbers; no verdict words."""
    from PIL import Image, ImageDraw
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    by_arch = {}
    for name, r in sorted(report["requests"].items()):
        att = best_attempt(r)
        if att:
            by_arch.setdefault(r["archetype"], []).append((name, r, att))
    made = []
    cw, ch, pad, head = 640, 360, 10, 70
    f1, f2 = _font(20), _font(15)
    for arch, rows in sorted(by_arch.items()):
        W = pad + 3 * (cw + pad)
        H = 50 + len(rows) * (ch + head + pad)
        sheet = Image.new("RGB", (W, H), (18, 18, 22))
        dr = ImageDraw.Draw(sheet)
        dr.text((pad, 12), "PLACEMAKER  %s  (shown: game camera a, camera b, plan diagram; numbers only)" % arch,
                fill=(235, 235, 235), font=f1)
        y = 50
        for name, r, att in rows:
            for k, line in enumerate(_numbers(name, r, att)):
                dr.text((pad, y + 4 + 21 * k), line, fill=(215, 215, 225), font=f2)
            imgs = [att["render"]["frame"], (r.get("views", {}).get("b") or {}).get("frame")]
            diag = EVID / report["run"] / ("diagram-%s.png" % name)
            diagram(place.make_plan(r["archetype"], att["params"]), diag)
            imgs.append(str(diag))
            caps = ["camera a (entrance)", "camera b (corner)", "plan: zones + footprints"]
            for j, img in enumerate(imgs):
                x0 = pad + j * (cw + pad)
                if img and Path(img).is_file():
                    pic = Image.open(img).convert("RGB")
                    f = min(cw / float(pic.size[0]), ch / float(pic.size[1]))      # fit the cell, keep aspect
                    pic = pic.resize((max(1, int(pic.size[0] * f)), max(1, int(pic.size[1] * f))),
                                     Image.NEAREST if j < 2 else Image.BILINEAR)
                    sheet.paste(pic, (x0, y + head))
                else:
                    dr.rectangle([x0, y + head, x0 + cw, y + head + ch], outline=(90, 90, 90))
                    dr.text((x0 + 10, y + head + 10), "not captured", fill=(200, 200, 200), font=f2)
                dr.text((x0 + 6, y + head + 6), caps[j], fill=(255, 255, 255), font=f2)
            y += ch + head + pad
        p = out_dir / ("%s-sheet.png" % arch)
        sheet.save(p)
        made.append(str(p))
    return made, by_arch


def hero(att, name, r, out, view="a"):
    from PIL import Image, ImageDraw
    src = att["render"]["frame"] if view == "a" else r["views"][view]["frame"]
    pic = Image.open(src).convert("RGB")
    sc = max(1, 1280 // pic.size[0])
    pic = pic.resize((pic.size[0] * sc, pic.size[1] * sc), Image.NEAREST)
    canvas = Image.new("RGB", (pic.size[0], pic.size[1] + 76), (18, 18, 22))
    canvas.paste(pic, (0, 0))
    dr = ImageDraw.Draw(canvas)
    for k, line in enumerate(_numbers(name, r, att)):
        dr.text((10, pic.size[1] + 6 + 22 * k), line, fill=(220, 220, 228), font=_font(15))
    canvas.save(out)
    return out


def proof(requests_file, run, out_dir, seconds=40, render_rounds=3, fresh=False, views=("b",)):
    reqs = json.loads(Path(requests_file).read_text(encoding='utf-8'))["requests"]
    rep = make_many(reqs, run, seconds, render_rounds=render_rounds, fresh=fresh)
    for v in views:
        rep = recapture_view(rep, v, seconds)
    made, by_arch = sheets(rep, out_dir)
    return rep, made, by_arch


def approval_demo(report, store):
    """Prove the style-lock mechanism on real frames with a SYNTHETIC approval in a scratch store: approve one room,
    compare the others of the same archetype, and a known-bad control (the approved frame with its colours inverted,
    paired with a clutter-3 layout). Never writes the repo store."""
    from PIL import Image, ImageOps
    store = Path(store)
    if store.resolve() == PM.STORE.resolve():
        raise RuntimeError("approval_demo must not write the repo approval store")
    if store.exists():
        shutil.rmtree(store)
    out = {"store": str(store), "synthetic": True, "rows": []}
    by_arch = {}
    for name, r in sorted(report["requests"].items()):
        att = best_attempt(r)
        if att:
            by_arch.setdefault(r["archetype"], []).append((name, r, att))
    for arch, rows in sorted(by_arch.items()):
        name0, r0, a0 = rows[0]
        rec, d = PM.approve(store, arch, a0["params"], a0["plan_sha256"], a0["result"]["pack"], a0["params"]["mood"],
                            [a0["render"]["frame"]], a0["layout"], "synthetic-proof", synthetic=True,
                            note="mechanism proof only; not a human approval")
        row = {"archetype": arch, "approved_synthetic": name0, "compare": []}
        for name, r, att in rows:
            c = PM.compare(store, arch, [att["render"]["frame"]], att["layout"], att["result"]["pack"], att["params"]["mood"])
            n = c["nearest"][0]
            row["compare"].append({"room": name, "mood": att["params"]["mood"], "clutter": att["params"]["clutter"],
                                   "palette_distance": n["palette_distance"], "layout_distance": n["layout_distance"],
                                   "same_style": n["same_style"]})
        vb = ((r0.get("views") or {}).get("b") or {}).get("frame")
        if vb and Path(vb).is_file():          # same room, same style, other standard camera
            c = PM.compare(store, arch, [vb], a0["layout"], a0["result"]["pack"], a0["params"]["mood"])
            n = c["nearest"][0]
            row["same_style_camera_b"] = {"palette_distance": n["palette_distance"], "layout_distance": n["layout_distance"]}
        bad = EVID / report["run"] / ("control-offpalette-%s.png" % arch)
        im = Image.open(a0["render"]["frame"]).convert("RGB")
        ImageOps.invert(im).save(bad)
        worst = place.make_plan(arch, dict(a0["params"], clutter=3, seed=a0["params"]["seed"] + 1))
        c = PM.compare(store, arch, [bad], worst["layout"], a0["result"]["pack"], a0["params"]["mood"])
        n = c["nearest"][0]
        row["control"] = {"frame": str(bad), "palette_distance": n["palette_distance"], "layout_distance": n["layout_distance"],
                          "palette_far": n["palette_far"]}
        row["examples_offered_without_synthetic"] = len(PM.examples(store, arch))
        out["rows"].append(row)
    (EVID / report["run"] / "approval-demo.json").write_text(json.dumps(out, indent=1, sort_keys=True), encoding='utf-8')
    return out


def finish(report, out_dir, store=None):
    """Hero shots (selection rule: highest reference-band score among rooms that passed every check, two different
    archetypes, ties by name; a numbers rule, not a look ranking), SHOWN.md and the approval demo."""
    out_dir = Path(out_dir)
    rows = []
    for name, r in sorted(report["requests"].items()):
        att = best_attempt(r)
        if att:
            rows.append((name, r, att))
    passed = [x for x in rows if x[1]["passed"]]
    ranked = sorted(passed or rows, key=lambda x: (-((x[2]["render"].get("band") or {}).get("score", 0)), x[0]))
    heroes, seen = [], set()
    for x in ranked:
        if x[1]["archetype"] not in seen:
            heroes.append(x)
            seen.add(x[1]["archetype"])
        if len(heroes) == 2:
            break
    hero_files = []
    for k, (name, r, att) in enumerate(heroes, 1):
        hero_files.append(hero(att, name, r, out_dir / ("hero-%d-%s.png" % (k, name))))
    demo = approval_demo(report, store or (SCRATCH.parent / "placemaker-approvals-demo"))
    L = ["# PLACEMAKER proof: what is shown", "",
         "Real runtime frames from the plugin's normal Service path (scaffold, compile, check, build_assets, open with "
         "screenshots) in a scratch bundle clone. Numbers only; how it looks is for the owner to judge.", "",
         "Run: `python3 -B -m tools.place_maker proof --requests docs/placemaker/proof-requests.json --run %s` "
         "(report: `evidence/placemaker/%s/report.txt`, git-ignored)." % (report["run"], report["run"]), "",
         "## Files", ""]
    for p in sorted(out_dir.glob("*-sheet.png")):
        L.append("- `%s`: contact sheet, one row per room: game camera a (entrance view), standard camera b (corner), "
                 "top-down plan diagram (floor box, entrance zone green, path blue, fight floor red, footprints by group)." % p.name)
    for (name, r, att), f in zip(heroes, hero_files):
        L.append("- `%s`: hero shot, %s (%s), camera a, nearest-neighbour upscale, numbers strip." % (Path(f).name, name, r["archetype"]))
    L += ["", "Hero selection rule: highest reference-band score among rooms that passed every check, two different "
          "archetypes, ties by name. A numbers rule, not a look ranking.", "",
          "## Rooms", "",
          "| room | archetype | size | mood (pack) | clutter | seed | runtime tris | clear sq. m (rule) | reachable | "
          "coverage | style gate | n64 | band | attempts (renders) | all checks |", "|" + "---|" * 15]
    for name, r, att in rows:
        st, ren = att["static"], att["render"]
        p = att["params"]
        b = ren.get("band") or {}
        L.append("| %s | %s | %s | %s (%s) | %d | %d | %s | %.2f (%.2f) | %d/%d | %.3f | %s | %s | %.2f | %d (%d) | %s |" % (
            name, r["archetype"], p["size"], p["mood"], att["result"]["pack"], p["clutter"], p["seed"], ren.get("triangles"),
            st["clear_square_m"], st["min_clear_m"], sum(1 for v in st["reachable"].values() if v), len(st["reachable"]),
            st["coverage"], ren.get("style_gate"), ren.get("n64"), b.get("score", 0), r["attempts_used"], r["renders_used"],
            "yes" if r["passed"] else "no"))
    L += ["", "Camera b frames (second standard camera), gates on that frame:", "",
          "| room | style gate | n64 | band | runtime tris |", "|---|---|---|---|---|"]
    for name, r, att in rows:
        v = (r.get("views") or {}).get("b") or {}
        L.append("| %s | %s | %s | %.2f | %s |" % (name, v.get("style_gate"), v.get("n64"), (v.get("band") or {}).get("score", 0),
                                                  v.get("triangles")))
    L += ["", "## Attempts that changed something", ""]
    for name, r, att in rows:
        for a in r["attempts"]:
            if a.get("next"):
                why = "; ".join((a.get("render") or {}).get("reasons", [])[:1] or a["static"]["failures"][:1])
                L.append("- %s #%d: %s -> %s" % (name, a["n"], why, a["next"]))
    L += ["", "## Gaps and recipes per room", ""]
    for name, r, att in rows:
        res = att["result"]
        miss = [w["want"] for w in res["wants"] if w["status"] != "exists"]
        L.append("- %s: recipes %s; not in library %s; trimmed %d; short %s" % (
            name, ", ".join(res["recipes"]) or "none", ", ".join(miss) or "none", len(res["trims"]),
            ", ".join("%s %s/%s" % (s.get("group"), s.get("placed"), s.get("wanted")) for s in res["short"]) or "none"))
    L += ["", "## Approval mechanism (synthetic, scratch store; nothing approved by a human)", ""]
    for row in demo["rows"]:
        sb = row.get("same_style_camera_b") or {}
        L.append("- %s: synthetic approval of %s (%s). Same room from camera b (same style): palette %s. Other rooms "
                 "(other moods) palette / layout: %s. Known-bad control (inverted frame + clutter-3 layout): palette %.3f, "
                 "layout %.3f. Approved examples offered (synthetic excluded): %d." % (
                     row["archetype"], row["approved_synthetic"], row["compare"][0]["mood"],
                     "%.3f" % sb["palette_distance"] if sb else "n/a",
                     "; ".join("%s %s %.3f / %.3f" % (c["room"], c["mood"], c["palette_distance"], c["layout_distance"])
                               for c in row["compare"][1:]),
                     row["control"]["palette_distance"], row["control"]["layout_distance"], row["examples_offered_without_synthetic"]))
    (out_dir / "SHOWN.md").write_text("\n".join(L) + "\n", encoding='utf-8')
    return out_dir / "SHOWN.md", hero_files, demo


# ----------------------------------------------------------------------------------------------- CLI
def _params(a):
    return {k: v for k, v in (("size", a.size), ("mood", a.mood), ("clutter", a.clutter), ("seed", a.seed)) if v is not None}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools.place_maker")
    ap.add_argument("cmd", choices=["list", "plan", "diagram", "make", "approve", "compare", "examples", "determinism",
                                    "proof", "finish"])
    ap.add_argument("--requests", help="proof: JSON file {\"requests\": [{name, archetype, params}]}")
    ap.add_argument("--fresh", action="store_true", help="re-clone the scratch bundle")
    ap.add_argument("archetype", nargs="?")
    ap.add_argument("--size")
    ap.add_argument("--mood")
    ap.add_argument("--clutter", type=int)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--attempts", type=int, default=3, help="render rounds (each round may use several static plans)")
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--run")
    ap.add_argument("--room")
    ap.add_argument("--by")
    ap.add_argument("--note", default="")
    ap.add_argument("--store", default=str(PM.STORE))
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--with-synthetic", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "list":
            return place.main(["list"])
        if a.cmd == "plan":
            res, room, pres, rep, st = place.plan_and_check(a.archetype, _params(a))
            print("\n".join(place.report_lines(res, st)))
            return 0 if st["ok"] else 1
        if a.cmd == "diagram":
            res = place.make_plan(a.archetype, _params(a))
            print(diagram(res, a.out or str(EVID / ("diagram-%s.png" % a.archetype))))
            return 0
        if a.cmd == "determinism":
            r = determinism(a.archetype, _params(a))
            print("same bytes" if r["same"] else "DIFFERENT bytes", " ".join(s[:12] for s in r["sha256"]))
            return 0 if r["same"] else 1
        if a.cmd == "proof":
            run = a.run or time.strftime("proof-%Y%m%d-%H%M%S")
            rep, made, _ = proof(a.requests, run, a.out or str(EVID / run / "sheets"), a.seconds, a.attempts, a.fresh)
            print("\n".join(report_text(rep)))
            print("sheets:", " ".join(made))
            return 0
        if a.cmd == "finish":
            rep = json.loads((EVID / a.run / "report.json").read_text(encoding='utf-8'))
            made, _ = sheets(rep, a.out or str(EVID / a.run / "sheets"))
            shown, heroes, demo = finish(rep, a.out or str(EVID / a.run / "sheets"))
            print("\n".join(made + [str(h) for h in heroes] + [str(shown)]))
            return 0
        if a.cmd == "make":
            run = a.run or time.strftime("make-%Y%m%d-%H%M%S")
            rep = make_many([{"name": a.archetype, "archetype": a.archetype, "params": _params(a)}], run, a.seconds,
                            render_rounds=a.attempts)
            print("\n".join(report_text(rep)))
            print("report:", EVID / run / "report.txt")
            return 0 if all(r["passed"] for r in rep["requests"].values()) else 1
        if a.cmd in ("approve", "compare"):
            run = Path(a.run)
            rep = json.loads((run / "report.json").read_text(encoding='utf-8'))
            att = None
            for r in rep["requests"].values():
                for x in r["attempts"]:
                    if x.get("room_id") == a.room:
                        att = x
            if att is None or "render" not in att:
                print("REFUSED: no rendered attempt with room id %r in %s" % (a.room, run))
                return 2
            frames = [att["render"]["frame"]]
            res = att["result"]
            if a.cmd == "approve":
                rec, d = PM.approve(a.store, res["archetype"], att["params"], att["plan_sha256"], res["pack"],
                                    att["params"]["mood"], frames, att["layout"], a.by, note=a.note, synthetic=a.synthetic,
                                    extra={"plan": att["plan"]})
                print("recorded approval %s by %s%s -> %s" % (rec["id"], rec["approved_by"],
                                                            " (synthetic)" if rec["synthetic"] else "", d))
                return 0
            c = PM.compare(a.store, res["archetype"], frames, att["layout"], res["pack"], att["params"]["mood"])
            print(json.dumps(c, indent=1, sort_keys=True))
            return 0
        if a.cmd == "examples":
            ex = PM.examples(a.store, a.archetype, include_synthetic=a.with_synthetic)
            if not ex:
                print("no approved examples for %s yet (store %s)" % (a.archetype, a.store))
            for e in ex:
                print(json.dumps(e, sort_keys=True))
            return 0
    except PlaceError as e:
        print("REFUSED: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
