# COVER integration (`hermes64_cover`)

Exact registration for Main to merge. All of it is applied in the `cover-lane` worktree so it could be tested; these
are the only edits to pre-existing files.

## 1. Registration lines (pre-existing files)

| File | Change |
|---|---|
| `plugin.yaml` | append `"hermes64_cover"` to `provides_tools` (now 25 names) |
| `__init__.py` | `from .adventure_maker.cover_tools import register_cover_tools`, then `register_cover_tools(ctx)` at the end of `register()`, before the command |
| `tests/test_registration.py` | `self.assertEqual(len(ctx.tools), 24)` → `25` |
| `tests/test_plugin_isolation.py` | `self.assertEqual(report['tools'], 24)` → `25` |
| `tools/verify_all.py` | new stage `('cover',[sys.executable,'-B','-m','unittest','discover','-s','tests_cover','-v'],300)` after `plugin`; `'tests_cover'` added to the hashed source directories |

Schemas: the tool schema is `COVER_SCHEMA` in the new `adventure_maker/cover_schemas.py`. It reuses `obj`, `text` and
`ID` from `adventure_maker/schemas.py`, which is unchanged. `register_cover_tools` registers one tool,
`hermes64_cover`, in toolset `hermes64`, with `requires_env=[]` and `check_fn=lambda: True`, matching the other tools.
Config keys used, all existing: `projects_root`, `bundle_root`, `godot_path`.

Why a separate verify stage: the plugin stage (`tests/`) already takes about 131 s against its 180 s timeout on this
Mac. The heavier cover tests (finishing at full export sizes, the gate on real render passes, the two-render engine
determinism check) live in `tests_cover/`, about 70 s, under their own 300 s timeout. The fast cover tests (scene
contract, edits, proposals, the project field) stay in `tests/`.

## 2. New files

- `contracts/cover/1.0.0.json`: cover scene contract. `contracts/cover/project-cover-1.0.0.json`: the optional
  project field.
- `adventure_maker/cover_scene.py` (validator, typed edits, proposals), `cover_style.py` (style resolution, palette
  snapping, mood presets), `cover_render.py` (staged runtime + Runner job), `cover_gate.py`, `cover_finish.py`,
  `cover_font.py` (original 7x9 face), `cover_tools.py`, `cover_schemas.py`, `project_cover.py`.
- `runtime/godot/cover/` (`cover.tscn`, `cover.gd`, `sky.gdshader`, `particles.gdshader`).
- `skills/hermes64-cover/SKILL.md`, `tests/test_cover_scene.py`, `tests/test_project_cover.py`, `tests_cover/`,
  `tools/cover_demo.py`, `docs/COVER.md`, `docs/COVER-RESULT.md`, `docs/cover/`.

The renderer reuses the runtime as-is: `view/assets.gd` (hash-checked kit resolver), `actors/*` (bound cast), and
`look/rig.gd`, `look/n64_mat.gd` and `shaders/n64_world.gdshader` (the N64 look). No shared runtime file is
modified. `cover_render` copies `runtime/godot` (which now includes `cover/`) into `<project>/.maker/cover/runtime-<hash>/`
once per runtime digest and runs
`res://cover/cover.tscn` windowed through the existing sandboxed Runner (argv only, `--audio-driver Dummy`,
`--quit-after` bound).

## 3. Project model: optional `cover` field

`contracts/project/1.0.0.json` and `adventure_maker/project_model.py` are unchanged; the 1.0.0 manifest stays closed.
The new `adventure_maker/project_cover.py` owns one optional field:

- A manifest without `cover` passes through untouched: same bytes, same validation (tested).
- `project_cover.validate_manifest(manifest, root)` validates the base with `project_model.validate_manifest` and the
  `cover` block against `contracts/cover/project-cover-1.0.0.json`. Every named file is confined to the project,
  present and a PNG, and the scene hash is re-derived, so a scene edited after adoption is refused with
  `COVER_MISMATCH`.
- `project_model.validate_manifest` still rejects a manifest carrying `cover` (closed schema). Readers that may meet
  one call `project_cover.validate_manifest`, or strip it with `project_cover.without_cover`.
- `hermes64_cover export adopt=true` writes the field only when the project root has a `project.json` (a portable
  project). Scaffolded managed projects have none and get `.maker/cover/current.json`.

## 4. How the Studio picks it up (no change to `../wt-studio`)

The Studio scanner (`wt-studio/adventure_maker/studio_catalogue.py`, `_cover`) already prefers
`.maker/studio/cover.png` as a `kind: "file"` cover over run captures and the procedural fallback. It reads the file
through its own confined reader with the PNG size limit and records path, size and sha256. `adopt=true` writes the
title-free Studio art (440x308, 2x of the cartridge art window) to exactly that path. The cartridge keeps drawing its
own title band, so the shelf shows the staged art with no Studio change.

Optional, Studio-owned follow-up: to show the finished box art (logotype, band, corner mark) instead, read
`.maker/cover/current.json` (`exports["box-2x"].path`), or `project.json` → `cover.box` for portable projects, through
the same confined PNG reader, and skip the cartridge's own title for that card.

**Done in MERGE4** (the Studio is merged): `studio_catalogue._box_art` reads `project.json` `cover.box` first, then
`.maker/cover/current.json` `exports["box-2x"]`, through the same confined reader (a refused path is reported as a
`PATH` issue and the old order applies). The cover is `kind: "box"` (with the cover tool's `title_position`), and the
cartridge draws no title, corner mark, style band or grade of its own over it. Until the real image has arrived, the
procedural stand-in keeps the cartridge's own title. Verified on a real isolated Desktop with a real Godot render
(`docs/MERGE4-LOG.md` section 5); tests `tests/test_merge4_studio_covers.py`, `studio/harness/test_shared.mjs`.
