# KITS contract 3.1.0: Hermes64 core kit library + theme packs

Status: PUBLISHED EARLY (2026-11-07 ~15:50 EST) so the runtime, plugin and story lanes can code against it. The interface is fixed now; assets land as they are built. **A file exists only when `kits/manifest.json` lists it with a sha256.** `../CHECKPOINT.md` says what exists and what is verified. Contract 2.0.0 (polar-only ids such as `char.expedition_figure`) is retired and kept in `../old/v2/`. Changes after this date are additive and logged in §14. **3.1.0 (2026-11-07 evening): people and animals moved to lane-characters**; this lane is environment-only (architecture, terrain, flora/rocks, furniture/containers incl. molded seating, vehicles/boats, props/signage/books/keys/tools, soft goods, sky, fx).

Owner: lane-kits. Integration owner: Hermes Main. Executing model (runtime header): `claude-opus-5-5`. Local, offline, code-generated assets only (Blender 5.2.1 headless + Python). Godot import is NOT claimed here.

## 1. Model: CORE generators + THEME PACKS

- **Core generator** = theme-agnostic Python code: `id`, `version`, typed `params_schema`, defaults, `build(params, seed) -> geometry with semantic material ROLES`. Core code contains no palette, colour, texture or theme word.
- **Theme pack** = data only: `packs/<pack_id>/pack.json` (+ `NOTES.md`). It holds the palette (<=32 colours) + LUT, the material binding for every core role, the vertex-light and fog rig, kit presets, layout fixture bindings, cast presets and validator thresholds.
- **Build** = (generator id, pack id, preset, params, seed) -> one `.glb` + sidecar `.json`. The same id/params/seed in two packs gives the same shape (same `shape_sha256`, 3.1.0) with different materials, unless the pack preset sets different params (then it says so in the resolved params). Correction (3.1.0): 3.0.0 claimed equal `geometry_sha256`; that hash covers the exported vertex arrays, whose split pattern follows pack-specific vertex colours and UV tiling, so it differs across packs for many generators (measured: equal in 761 of 1290 same-param pairs; `shape_sha256` equal in 1290 of 1290, `reports/determinism.json`).
- Packs shipped: `polar_pod` (retro-futurist polar habitat; the Thaw showcase) and `forest_village` (warm N64-style woodland village). Rationale in `packs/forest_village/NOTES.md`. The second pack needed zero core code.
- Pack data shape (validated fail-closed by `core/packs.py`, resolved against the registry by `tools/packcheck.py`): `kit_presets: {generator_id: {preset_name: {params}}}`; `fixtures: {slot: {generator, preset[, params]}}`; `cast: {name: {character_id, kind: person|animal, supplied_by: "lane-characters"[, source, study_only]}}` (references only since 3.1.0); `validator_thresholds.tri_limits` may only tighten §6.

## 2. Paths (relative to `lane-kits/`)

| Path | What |
|---|---|
| `kits/manifest.json` | authoritative list: generators, schemas, every built file with sha256, tri counts, budgets, validation |
| `kits/<pack>/assets/<id>.glb` | default build of each generator in that pack (pack default preset applied) |
| `kits/<pack>/presets/<id>__<preset>.glb` | named pack presets (e.g. `furn.pod__chaise`) |
| ~~`kits/<pack>/cast/<name>.glb`~~ | retired in 3.1.0: people/animals are published by lane-characters (see its contract); `pack.json -> cast` holds id references only |
| `kits/<pack>/rooms/<layout>/<slot>.glb` | the pieces of a resolved layout (built from the pack's fixture bindings; openings filled to their exact size) |
| `kits/<pack>/textures/tex_*.png`, `kits/<pack>/env/*.png` | source textures (also embedded in GLBs); env maps live only here |
| `kits/<pack>/palette.json`, `kits/<pack>/lut16.png`, `kits/<pack>/materials.json` | palette, LUT, material table + runtime recipes |
| `kits/layouts/<layout>.json` | theme-agnostic room layouts (semantic fixture slots) |
| `kits/<pack>/rooms/<layout>.json` | the layout resolved for a pack (asset files + transforms) |
| `kits/style-packs/<pack>.json` | byte copy of `packs/<pack>/pack.json` for the plugin's discovery path |
| `packs/<pack>/pack.json`, `packs/<pack>/NOTES.md` | the pack itself (data) |
| `reports/`, `sheets/` | sweeps, gates, controls, determinism; contact sheets (small PNGs) |

## 3. Referencing and building an asset

Reference (compiler/runtime): `{"asset_id": "furn.table", "version": "3.0.0", "pack": "polar_pod", "preset": "flower_table", "params": {}, "seed": 0}`.

Param resolution order: generator defaults <- pack preset `default` for that id (if any) <- named `preset` <- explicit `params`. The resolved params are written to the sidecar/manifest. **Fail closed** (exit 2, no output file): unknown id, unsupported major version, unknown pack/preset, unknown param, wrong type, out of range, bad enum, unknown palette colour name, violated cross-param rule. No silent clamping.

`params: {}`, `preset: null`, `seed: 0` = the prebuilt `kits/<pack>/assets/<id>.glb`. Anything else needs an offline build:

```
/opt/homebrew/bin/blender -b --factory-startup --python build.py -- \
  --id furn.table --pack polar_pod [--preset flower_table] [--params '{"height":0.7}'] [--seed 7] --out OUT.glb
```

Exit 0 = built AND passed the per-asset validators; writes `OUT.glb` + `OUT.glb.json` (resolved params, tri count, sha256, geometry/topology hashes, validator results). Exit 2 = rejected input. Exit 3 = built but failed validation (the GLB is deleted; the JSON explains why). Batch: `--batch JOBS.json --out-dir DIR`. Seeds drive only declared stochastic detail (noise, scatter, patterns).

## 4. Space, units, origin

Metres. glTF space: **+Y up, model front faces +Z**, +X is the model's left (standard glTF; Blender authors +Z up / front -Y and the exporter converts). Every node has scale 1, no negative scale. Origins:
- furniture, props, flora, rocks, vehicles, characters, buildings: footprint centre, min Y = 0 (within 1 cm). `wall_mounted: true` in the manifest marks exceptions.
- wall/door/window modules: floor-level centre of the opening's interior face; interior side faces +Z.
- `arch.room_shell`, `arch.corridor`: room floor centre; spans x in [-w/2, w/2], z in [-d/2, d/2]. Lane-story room-local coordinates (origin NW corner, X east, Z south, 1 tile = 1 m) = shell coordinates + (w/2, 0, d/2). Shell north wall = -Z side.
- terrain/water: patch centre at Y=0 rest height. sky/fx: documented per asset.
No collision meshes. The runtime authors collision from the layout/room plan.

## 5. Node naming and topology rules (validated)

Lowercase ASCII snake_case. Nodes start `kit_`, materials `mat_`, images `tex_`, armatures `rig_<skeleton>`, attachments `attach_<slot>`. Prefix = topology rule:
- `kit_<name>`: closed solids. Every island watertight (each welded edge has exactly 2 faces), consistently wound, no zero-area faces, no self-intersection inside an island. Islands may interpenetrate; they never share coincident vertices.
- `kit_shell_<name>`: one-sided interior surfaces (room/corridor walls, floor, ceiling seen from inside). Boundary allowed; each edge <= 2 faces; consistent winding toward the inside; no self-intersection.
- `kit_card_<name>`: planar single-sided cards (window view planes, sky, particles). Facing documented.
- Movable sub-parts are separate nodes with their own pivot: `kit_door_leaf` (hinge), `kit_lid` (container hinge).

## 6. Classes and budgets (triangles per GLB; textures px)

| class | generators | tri limit | tex |
|---|---|---|---|
| shell | `arch.room_shell` | 1500 | <=64, view 128 |
| building | `arch.house` | 900 | <=64 |
| structure | `arch.stairs`, `arch.bridge`, `arch.pier`, `arch.corridor` | 500 | <=64 |
| arch | `arch.wall_module`, `arch.floor_module`, `arch.ceiling_module`, `arch.door`, `arch.window`, `arch.roof`, `arch.railing`, `arch.column` | 300 | <=64, view 128 |
| terrain | `terrain.patch`, `terrain.water` | 512 | <=64 |
| flora | `nature.tree`, `nature.bush`, `nature.rock`, `nature.grass_tuft` | 300 | <=64 |
| furniture | `furn.table`, `furn.chair`, `furn.shelf`, `furn.container`, `furn.lamp`, `furn.rug`, `furn.hearth` | 300 | <=64 |
| furniture_large | `furn.bed`, `furn.pod`, `furn.bench`, `furn.console` | 400 | <=64 |
| vehicle | `vehicle.boat`, `vehicle.craft` | 500 | <=64 |
| prop | `prop.sign`, `prop.book`, `prop.key`, `prop.tool`, `prop.vessel`, `prop.device` | 150 | <=64 |
| soft | `soft.pillow`, `soft.blanket` | 150 | <=64 |
| sky | `sky.backdrop` | 128 | 128 |
| fx | `fx.particles` (card + JSON spec) | 16 | <=32 |
| character | owned by lane-characters since 3.1.0 (not built, validated or listed by this lane) | (700) | (128) |
| animal | owned by lane-characters since 3.1.0 | (300) | (<=64) |

A pack may tighten (never loosen) these. Visible room review target <= 6000 tris (each resolved layout reports its total). Textures are tiny and soft: sampled LINEAR (bilinear) with REPEAT, 8-128 px.

## 7. Material roles (core vocabulary) and kinds (runtime recipes)

Generators tag faces with ROLES; the pack binds every role to a material. Roles: `wall wall_alt floor ceiling trim frame door glass view roof step rail post stone metal chrome body body_alt cushion fabric knit fur quilt screen light orb wood paper book leather rope fire grass snow sand rock dirt water ice bark foliage cap flower hull hull_alt band sky particle skin face headwear opening costume coat`.

Material name = `mat_<pack>_<role>` (characters: `mat_<pack>_char_<slot>_<hash8>`). Each material carries `extras.n64 = {kind, role, pack, ...}` and the same table is in `kits/<pack>/materials.json` keyed by material name, so the runtime can rely on the name if extras are dropped. Kinds:
- `baked_unlit` (default): colour = baseColorTexture x COLOR_0 (baseColorFactor is white). Exported with `KHR_materials_unlit`. COLOR_0 carries baked light from the pack light rig (soft key, darker undersides/creases) quantised to the pack's light ramp.
- `chrome_env`: fake environment map. Exported as metallic 1 / roughness 0.2 with `baseColorFactor` = tint, no texture. **Runtime recipe**: `n = normalize(view-space normal); uv = n.xy*0.5+0.5; colour = texture(env, uv).rgb * tint * COLOR_0`, unlit (sphere-map/matcap lookup, no real reflection). `extras.n64.env` names the env PNG under `kits/<pack>/env/`. Godot sketch (NOT verified): `shader_type spatial; render_mode unshaded; uniform sampler2D env; uniform vec3 tint; void fragment(){ ALBEDO = texture(env, NORMAL.xy*0.5+0.5).rgb * tint * COLOR.rgb; }`.
- `glass_env`: same recipe with a darker env (glass spheres, portholes, screens off).
- `emissive`: unlit full-bright texture; ignores COLOR_0 darkening; fog still applies (lamps, screens, lit windows, fire).
- `view_plane`: unlit opaque scene card behind windows (never fogged by interior fog).
- `card_alpha`: unlit alpha-tested (`alphaMode MASK`, cutoff 0.5), double-sided allowed (particles, grass cards, steam).
- `water`: like `baked_unlit` plus `extras.n64.scroll = [u, v]` metres/second UV scroll (runtime option).
- `face_atlas`: like `baked_unlit`; the texture is the pack face atlas; `KHR_texture_transform` offset/scale selects a cell; `extras.n64.atlas = {cols, rows, cell}`. Expression swap (blink/talk) = change the offset; mesh UVs never change.

## 8. Palette, LUT, light, fog

`kits/<pack>/palette.json` = `{"pack_id", "version", "colors": ["#RRGGBB" x <=32], "names": [...], "ramps": {name: [indices]}, "light_ramp": [indices dark->bright]}`. **Every texel of every texture is exactly a palette colour** (textures are built from palette ramps with 4x4 ordered/Bayer dithering). Every COLOR_0 value is a light-ramp colour (glTF stores linear; compare in sRGB8 with +-2 tolerance). baseColorFactor is white or a palette colour.
LUT `lut16.png`: 256x16 RGB, 16 slices of 16x16; pixel (x = b*16 + r, y = g) for 4-bit sRGB r,g,b holds the nearest palette colour (same layout as 2.0.0; lane-look already implements it). Post-process with NEAREST to force the frame through the palette (optional runtime look).
Fog/light rig: `pack.json -> fog {color, start, end, interior{...}}` and `light_rig`; the runtime reads them from the pack (kits does not render fog into GLBs).

## 9. People: `char.humanoid` (skeleton `human16_v1`): MOVED to lane-characters in 3.1.0

> Historical 3.0.0 interface, kept for reference only. lane-characters owns people and their contract; this lane's segmented generators (`core/gen_char.py`, `charrig.py`, `chartex.py`) are frozen in place, not loaded, not iterated and not part of any acceptance here.

ONE generic humanoid, ONE fixed-topology skinned mesh `kit_body` (<= ~620 tris) for every person in every pack, plus optional rigid accessory nodes `kit_acc_<slot>_<kind>` under attachment nodes (total <= 700). Head options: face-atlas head OR faceless hood/helmet (black void opening); headwear shell (hair styles / hood / helmet / cap); costume parts (top, vest, mantle, skirt/coat, trousers volume, gloves, boots) are vertex positions + material colours/patterns; height/build/head-size change vertex and bone REST POSITIONS only.

**Invariants (validated on every build):** `kit_body` has identical vertex count, triangle indices, UVs, material-slot layout (`costume`, `face`, `headwear`, `opening`), joints and weights for ALL params and BOTH packs (`topology_sha256`, `uv_sha256`, `skin_sha256` equal). Bone names, parents and rest ORIENTATIONS are identical; only rest positions scale. Role/costume/colour edits never change topology or rig.

Bones (exact names, parent in brackets): `root`; `pelvis`[root]; `spine`[pelvis]; `head`[spine]; `upper_arm_l`[spine]; `forearm_l`[upper_arm_l]; `hand_l`[forearm_l]; `upper_arm_r`[spine]; `forearm_r`[upper_arm_r]; `hand_r`[forearm_r]; `thigh_l`[pelvis]; `shin_l`[thigh_l]; `foot_l`[shin_l]; `thigh_r`[pelvis]; `shin_r`[thigh_r]; `foot_r`[shin_r]. (Same 16 names as 2.0.0.)
Attachments (glTF child nodes of joints): `attach_hand_l`, `attach_hand_r`, `attach_head`, `attach_back`[spine], `attach_belt`[pelvis]. Held props attach with their origin at the grip.
Clips (every person, same rotation keys): `idle`, `walk`, `run`, `interact`, `talk`, `carry`, `sit`. 12 fps held: keys on integer frames, glTF `STEP`. Non-root bones carry rotation only; `root` carries translation (bob, sit drop) + rotation, so clips retarget by bone name; only root translation is per-figure. Walk/run are in place.
Params (exact ranges/enums in the manifest; colours are pack palette NAMES): `height, build, head_size, head_mode (face|faceless), face (atlas cell), skin, headwear (bald|crop|bob|long|ponytail|bun|hood|helmet|cap), headwear_color, headwear_finish (matte|sheen), top_pattern, top_color, vest (none|quilted_wave|quilted_diamond|leather|apron), vest_color, vest_trim_color, mantle (0..1), mantle_color, skirt (0..1 length; 0 = belt), skirt_color, trouser_volume, bottom_color, wear, hands (bare|gloves), glove_color, boots (heavy|boots|shoes), boot_color, belt_color, armband, armband_color, patch, acc_head, acc_back, acc_belt`. Packs supply named cast presets (`cast` in pack.json).
Lane-story 1.1.0 `Suit` mapping: `hood:"silver_faceless"` -> `head_mode=faceless, headwear=hood, headwear_finish=sheen`; `vest_pattern` -> `vest`; `vest_colour`/`sweater_colour`/`trouser_colour` -> `vest_color`/`top_color`/`bottom_color` (palette names); `sweater_wear`/`trouser_wear` -> `wear`; `trouser_volume` -> `trouser_volume`; `gloves` -> `hands`/`glove_color`; `boots` -> `boots`; `accessories` -> `acc_*`. `body_id = "char.humanoid"`, `base_rig_id = "human16_v1"`.

## 10. Animals: `char.quadruped` (skeleton `quad16_v1`): MOVED to lane-characters in 3.1.0

> Historical 3.0.0 interface, kept for reference only (see §9 note).

One fixed-topology quadruped mesh for every species (cat, dog, deer-like, ...): `species` presets proportions; `size, leg_length, snout_length, ear_shape, tail_length, chubby, antlers, coat_pattern (solid|tuxedo|tabby|calico|spotted|socks|saddle), coat_color_1..3, eye_color` vary it. Topology/UV/skin invariant across species and coats. Bones: `root`; `hips`[root]; `chest`[hips]; `neck`[chest]; `head`[neck]; `tail_1`[hips]; `tail_2`[tail_1]; `tail_3`[tail_2]; `leg_fl`[chest]; `paw_fl`[leg_fl]; `leg_fr`[chest]; `paw_fr`[leg_fr]; `leg_bl`[hips]; `paw_bl`[leg_bl]; `leg_br`[hips]; `paw_br`[leg_br]. Clips (12 fps STEP): `idle`, `walk`, `run`, `sit`, `loaf`, `sleep_curled`, `stretch`. `loaf`/`sleep_curled` lowest point at Y=0 (drop onto cushions). `body_id = "char.quadruped"`, `base_rig_id = "quad16_v1"`.

## 11. Layouts (same room, any pack)

`kits/layouts/<id>.json`: `{"layout_id", "version", "shell": {"generator", "params"}, "openings": {slot: opening_index}, "fixtures": [{"slot", "pos": [x,y,z], "rot_y_deg", "params": {}}]}` in shell coordinates (`rot_y_deg` turns the fixture's front, +Z, about +Y). `openings` (3.1.0) fills the shell's openings: the bound door/window module takes the opening's shape and size and is placed at the shell's `meta.openings[i].pos_gltf` / `yaw_deg`. Slots are semantic (`seat_lounge`, `table_main`, `bed`, `lamp_floor`, `shelf`, `rug`, `console`, `container`, `window_main`, `door_main`, `cat_bed`, ...). Each pack binds slots in `pack.json -> fixtures: {slot: {generator, preset, params}}`. The resolved `kits/<pack>/rooms/<id>.json` lists asset files (`kits/<pack>/rooms/<id>/<slot>.glb`), their sha256, resolved params, transforms and the room tri total; `tools/room.py` builds and renders it with the same cameras for every pack. Shipped layout: `lounge` (7 x 6 m, door + two windows, 10 fixture slots).

## 12. Manifest

`kits/manifest.json` = `{"contract_version": "3.1.0", "blender": "...", "packs": [{id, version, pack_json, sha256, palette, palette_sha256, lut, lut_sha256, materials, materials_sha256, style_pack_copy, style_pack_copy_sha256, notes}], "classes": {class: tri_limit}, "classes_owned_elsewhere": {"character": "lane-characters", "animal": "lane-characters"}, "skeletons": {}, "kits": [entry...], "layouts": [{id, file, sha256}], "rooms": [{layout, pack, file, sha256, room_tris, pieces}]}`. Entry: `id, version, class, tri_limit, description, params_schema` (JSON-Schema subset: object, `properties` with `type` number/integer/string/boolean/array, `minimum`/`maximum`/`enum`/`default`, `x-palette-color: true` for colour names, `x-lod`/`x-runtime` annotations (3.1.0), `additionalProperties: false`), `defaults`, `seed_default`, `wall_mounted`, `origin_rule`, `builds: [{pack, preset, params (resolved), seed, glb, sha256, geometry_sha256, topology_sha256, uv_sha256, shape_sha256, tri_count, tri_limit, textures [{name, file, sha256}], validation, meta}]` (character-only fields are no longer emitted by this lane). The list key is `kits` (the plugin's `kits list/inspect` reads `manifest["kits"]`). A hash is evidence only for the exact file named. Sweep/gate/control evidence lives in `reports/`, never as a synthetic PASS in the manifest.

## 13. Honesty boundary

Verified here = built in Blender 5.2.1, exported, re-read by our own GLB reader (and re-imported into Blender for skin/animation checks and preview renders). NOT verified by this lane: Godot import, runtime shading (recipes above are specs), animation playback in Godot, the plugin's `--request` adapter seam (ADAPTERS.md v0.1; Main reconciles).

## 14. Changelog
- 3.0.0 (2026-11-07): core + packs split; generic ids; humanoid/quadruped universal meshes; layouts with fixture slots; manifest `kits` key.
- 3.1.0 (2026-11-07, additive): people/animals moved to lane-characters (§6, §9, §10; `cast` = references; `kits/<pack>/cast/` retired). New generator `furn.bench` (molded curled blob bench, furniture_large). `furn.pod` rebuilt as molded seating (`bowl`, `egg`, `chaise`, `lounge_pit` conversation pit with throws and disc table + dark glass orb) and `furn.console` as molded consoles (`mushroom`, `desk` with 1-3 rounded CRTs on a wavy kidney top, `terminal`, `lectern`), both now in `core/gen_molded.py`; `vehicle.craft` kind `saucer` (lens hull, two black window bands, light ring, optional dome, three legs); `arch.window` molded oval / rounded-rect frames. New fail-closed cross-param rules (each returns a reason, exit 2): sign assembly height <= 1.58 m, vessel width/height proportion, saucer canopy/size limits, desk width >= 0.5 + 0.6 x screens and top height <= 0.95 m, corridor inner bend radius >= 0.30 m, railing arc span limit, table lamp height <= 0.9 m, lantern height <= 0.6 m, lamp shade <= 0.8 x height, lounge_pit rim height <= 0.9 m (these replace former silent clamps). `furn.lamp` `hanging`: `height` is now the cord drop. `fx.particles` card outline follows `shape`. `terrain.patch`/`terrain.water` resolution max 13 (keeps 512). Layout `openings`; `kits/<pack>/rooms/<layout>/`; manifest fields above. Pack data shape documented in §1. Param schemas may carry `x-lod: true` (tessellation-only: `sky.backdrop.rings/segments`, `terrain.*.resolution`, `arch.room_shell.wall_segments`) and `x-runtime: true` (acts only in the runtime: `fx.particles` emitter params, `sky.backdrop.radius`); the visible-difference validator does not require those to change a static render. Manifest pack entries list `env_maps` [{name, file, sha256}] and build textures carry sha256. New hash `shape_sha256` = sha256 of the canonical welded triangle soup per node (positions quantised to 0.1 mm, each triangle rotated to its smallest vertex, list sorted): the cross-pack identity hash (§1 correction).
