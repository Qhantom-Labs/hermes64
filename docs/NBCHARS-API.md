# NBCHARS API — Blender-free character export (pure Python + numpy)

Owner: lane NBCHARS (`wt-nbchars`, branch `noblender-chars-lane`). Stable surface for CHARSYS (recipes / parts /
propose) and the merge lane. The skinned + animated GLB is written in pure Python (numpy only); Blender is kept
only as an optional test oracle and as the `blender` exporter choice. Rig contract and validator: `docs/RIGKIT-API.md`.

## 1. Package layout

| path | role |
|---|---|
| `adventure_maker/nbchars/` | exporter package (this API) |
| `adventure_maker/rigkit/` | rig contract runtime: GLB read/write, numpy LBS reference, validator, clip attach |
| `characters/gen/core/`, `characters/gen/packs/` | the generator, vendored **byte-identical to CHARSYS's vendoring** from `lane-combat-art` (same files, same pack transform, so the two branches add identical bytes). Provenance: `adventure_maker/nbchars/VENDORED-GEN.json` (not `characters/gen/VENDORED.json`, which CHARSYS owns) |
| `rigs/<rig_id>/` | rig kits (RIGKIT-API) |

The generator's Blender modules (`core/blender.py`, `core/combat_blender.py`) are never imported by the python
exporter; `adventure_maker/nbchars/assemble.py` is their pure-Python port (same calls into the generator, same
order, same seeds).

## 2. Entry points

```python
from adventure_maker import nbchars

# One compiled build item (CHARSYS job item schema, see section 3) -> GLB on disk + info row
info = nbchars.build_item(item, out_dir, *, packs=None, exporter='auto', settings=None)

# A whole CHARSYS job (schema 'hermes64-charsys-job/1') -> build report ('hermes64-charsys-build-report/1'),
# the same report characters/gen/build.py writes under Blender
report = nbchars.build_job(job, out_dir, *, exporter='auto', settings=None)

# export_cast / export_combat equivalents (the published cast, enemies, weapon, projectile)
manifest = nbchars.export_cast(out_dir, *, only=None, exporter='auto', settings=None, layout='published')
record = nbchars.export_combat(out_dir, *, only=None, exporter='auto', settings=None)

# Low-level: a fully described scene -> GLB bytes in the Blender-exporter layout (section 4)
raw = nbchars.write_scene(scene)

# Exporter choice and one-line doctor truth (numpy / blender: facts already probed for the build interpreter)
choice = nbchars.select_exporter(settings, numpy=None, blender=None)  # {'exporter': 'python'|'blender'|None, 'reason', 'numpy', 'parity'}
line = nbchars.doctor_line(settings)   # 'characters: python exporter (numpy 2.0.2, parity PASS, max skinned error 9.9e-07 m over 37 files) - Blender not required'
```

`layout='published'` reproduces the published byte layout of the combat cast (the r21 base export plus
`core/graft.py` appending the 6 combat clips); `layout='single'` writes one export with all 13 clips, which is what
a fresh Blender export of the same body gives.

CLI (`python3 -m adventure_maker.nbchars ...`):

```
export --cast all|id,id --out DIR [--exporter python|blender|auto] [--layout published|single]
export --combat --out DIR                                              # enemies, weapon, projectile
export --job JOB.json --out DIR                                        # CHARSYS job file
export --recipe ITEM_OR_RECIPE.json --out DIR                          # one build item; a CHARSYS recipe is
                                                                       #   compiled with adventure_maker.character_recipe
                                                                       #   when that module is present
doctor                                                                 # one line
parity --oracle PUBLISHED_DIR --out DIR [--visor-root DIR] [--reexport-blender ids] [--write-verdict]
preview --glb FILE.glb [...] --out DIR [--play-only]                   # Godot import check + contact sheets, no Blender
```

## 3. Build item (identical to CHARSYS `characters/gen/build.py` items)

```json
{"id": "tavi", "kind": "person|masked|animal|enemy|robot", "pack_id": "polar_pod", "params": {...},
 "seed": 19, "stance": "hold_mug", "props": ["mug"], "clips": ["idle", "...", "block"], "weapon": false,
 "enemy": "cairn_dasher", "robot": {...}, "out": "polar_pod/tavi.glb"}
```

- `clips` omitted = the legacy 7 clips (human `HCLIPS` / animal `ACLIPS`), exactly like `B.assemble(actions=True)`.
- `kind: robot` needs a scene builder: CHARSYS registers one with
  `nbchars.register_builder('robot', fn)` where `fn(item, pack) -> nbchars.Scene` (section 4). Until it is
  registered, robot items fail with a clear message (they are built by CHARSYS's own parts code).
- Packs: `packs={'<pack_id>': {'pack': {...}, 'combat_roles': {...}}}` overrides the vendored packs (the
  inline-pack mechanism of the CHARSYS job).

## 4. Scene model (for builders other than the vendored generator)

The writer is layout-faithful to Blender's exporter, so the scene carries exactly what Blender's export would see.
Coordinates follow the generator: **Blender-style Z up, metres, the character faces -Y**; the writer converts to glTF
(+Y up, faces +Z) like the exporter's `export_yup`. Containers are ordered because order is part of the byte layout.

```python
nbchars.Scene(kind='human'|'animal'|'enemy'|'prop', rig=SceneRig | None, body=SceneMesh,
              body_object='kit_body', body_extras=None, sockets=[SceneSocket], clips=[SceneClip], info={})
nbchars.SceneRig(object_name='rig_human16_v1', skeleton='human16_v1',
                 bones={'root': (x, y, z), ...},       # bone heads (Z up), creation order
                 parents={'root': None, ...}, extras={...})        # -> rig node extras (skeleton, topology, ...)
nbchars.SceneMesh(name, vertices (N,3) float32, faces (M,3), face_material (M,), corner_uv (3M,2) float32,
                  corner_color (3M,4) uint8 sRGB | None, materials=[SceneMaterial],
                  groups=[bone names], weights=[[(group, float32 weight)]], vertex_normals (N,3) float32)
nbchars.SceneMaterial(name, image_name, png_bytes, n64_extras, atlas_cell=None | (cell, cols, rows))
nbchars.SceneSocket(name, bone, translation=None, rotation=None (glTF xyzw), mesh=None, extras=None)
nbchars.SceneClip(name, times (16,) float32, rotations={bone: (16,4) glTF xyzw},
                  translations={bone: (16,3) offset from rest, glTF axes}, channel_order=[(bone, path)], extras=None)
```

Rules the writer enforces or applies: at most 4 influences per vertex (largest kept, renormalised like Blender),
weights <= 1e-4 dropped, a vertex with no influence is a `WriteError`; quaternions are written with w >= 0; STEP
samplers at the given times; translation channels are rest + offset in float32. `nbchars.assemble` builds these
scenes from the vendored generator (`character`, `enemy`, `weapon`, `projectile`, `weapon_socket`); the float32
paths Blender uses (face and vertex normals, the sRGB byte-colour table, the bone matrix chain) come from
`nbchars.blendmath`, and the generator runs with CPython 3.13 `sum` / `math.hypot` semantics (`nbchars.pycompat`)
because the oracle ran inside Blender's Python 3.13.

## 5. Byte conventions (what is identical to Blender and what is only equivalent)

Measured on all 37 published files (`docs/NBCHARS-RESULT.md`): accessor/bufferView layout, JSON structure, POSITION,
TEXCOORD_0, COLOR_0, JOINTS_0, WEIGHTS_0, indices, inverse bind matrices and embedded PNGs are byte-identical.
NORMAL differs by at most 1.3e-4 on a minority of vertices (Blender's `fast_acosf` corner weighting reproduced to
1-4 ulp before the exporter's 4-decimal rounding), animation quaternions by <= 2.4e-7 and root translations by
<= 4.7e-7 (Blender's float32 `mathutils` path versus float64 then float32). Skinned vertex positions agree to
<= 9.9e-7 m on every key of every clip. Two exports of the same input are byte-identical, and Python 3.9.6 / numpy
2.0.2 and Python 3.14.3 / numpy 2.4.3 write the same bytes.

## 6. Exporter switch

`settings['character_exporter']` (or `--exporter`, or env `HERMES64_CHARACTER_EXPORTER`): `python` | `blender` |
`auto` (default `auto`).

- `auto`: python when numpy is importable **and** the committed parity verdict
  (`adventure_maker/nbchars/PARITY.json`) is PASS for the current code (its fingerprint covers every vendored
  generator file and the exporter modules; any change makes it STALE). Otherwise Blender when `blender_path` (or a
  standard install) resolves. With a STALE verdict and no Blender the python exporter is still used and the doctor
  line says WARNING. Otherwise a one-line failure that names the missing piece.
- `python`: never touches Blender. Needs numpy (the doctor says so if it is missing; no stdlib skinning fallback is
  claimed for production export).
- `blender`: the original pipeline under Blender (`tools/nbchars_blender_export.py`), kept as the oracle.

`adventure_maker.doctor` reports `character_exporter` (the line above) and marks `new_character_bodies` available
with numpy alone. The plugin's tool schemas are not edited by this lane (CHARSYS owns them); `character_exporter`
is read from the settings dict, Main may surface it in `plugin.yaml` at merge.

## 7. Status (both APIs)

| item | status |
|---|---|
| API docs, rig.json x4, contract schema | committed a030bf5 |
| GLB writer (Blender layout), assemble port, float32 emulation, CPython-3.13 shims, parity harness | committed 15f3c98 |
| clip packs x4, mannequins x2, attach_clips (copy + grounding + guard) | committed efb48ac |
| parity verdict PASS (37/37), STALE fingerprint, doctor line, Godot import check + contact sheets, validate_prop | committed 7f35263 |
| oracle validate reports, tests, docs/RIGKIT.md, docs/NBCHARS-RESULT.md, blender exporter tool | committed 50cdb85 |
| hover positive control + validator fixes (unreferenced vertices, hover proportions, optional sit), 34 tests, verify_all 8/8 | closeout commit after 50cdb85 |
