# CHARCREATOR plan (Phase A)

## Answer

- The plugin cannot make characters in the reference shape and art style today. Its people come from the vendored
  house generator: 3 to 5 materials, 128 px cloth and hair textures, a separate face atlas and 8 to 16 flat colours.
  They fit 16 to 23 of the card's 40 body metrics. The references use one 64x64 atlas with baked light.
- Measured style card: `docs/charstyle/meshy_n64_card.json`. It holds generic ranges over the 2 reference models
  (min/max/mean) and no per-model rows, names, paths, hashes, texels or vertices. Tool:
  `tools/charcreator_measure.py` (repository only). The private receipt with per-model rows and source hashes is in
  the git-ignored `evidence/charcreator/`.
- Design: a new numpy builder, `adventure_maker/charcreator/`, with its data in `characters/creator/creator.json`.
  - The agent reaches it through the existing `hermes64_character` tool by passing `style=creator64`.
  - Edits use the existing typed edits. The validation and advertised schemas do not change (0 tokens; headroom
    is 2 tokens, 5,998/6,000).
  - The body is one welded, parametric low-poly mesh of about 560 triangles. Accessory modules are inset pieces.
    It is painted into one 64x64 atlas with baked light.
  - Clips come from the human16_v1 rig pack through `rigkit.clips.attach_clips`: 7 base clips plus 6 combat clips.
  - It is gated by the existing `character_gate.run`: rig kit, GLB audit, palette, cuboid, silhouette and
    determinism.
  - Contact sheets come from a pure-Python software renderer, so Blender is optional.

## 1. What exists (file:line at base 58404673)

| Piece | Where | Can do | Limits |
|---|---|---|---|
| Tool `hermes64_character` | `adventure_maker/character_tools.py:32-41` (actions), `:269` propose, `:298` edit, `:321` build, `:370` locomotion, `:492` bind | propose 3 variants from a sentence, typed edits, build + gates, bind, bake walk/run | contact sheets need Blender (`:216-224`, `character_pipeline.py:31`) |
| Schemas | `character_schemas.py:4-14` (8 edit kinds), `:22` (actions); compact copy `wire.py:57-59`, `:108-110` | | schema budget 5,998/6,000 tokens (`tools/schema_budget.py`) |
| Recipe compiler | `character_recipe.py:212` `compile_build`; `:58` `FACE_HEAD_MAX`; `:60` `RIG_HEIGHT`; `:486-558` edits | 9 bodies, 120 parts (`characters/library/parts.json`) | the person body is the vendored generator (`characters/gen`), not a 64 px atlas body |
| Proposer | `character_propose.py:18-82` word tables, `:394` `propose` | person / masked / robot / cat / dog from words | no wizard hat, no elf/goblin/dwarf/animal-person, no star hat |
| Style locks | `character_style.py:25-43` roles, `:265` `load_lock`; 5 locks in `profiles/character-styles/` | palette roles, proportion clamps | every test iterates every lock over house recipes (`tests/test_characters_recipe.py:63,179`) |
| Pipeline | `character_pipeline.py:160` `build`, `:41` python exporter child, `:120` Blender review renders | compile -> job -> child export -> gates, determinism by rebuild | review renders Blender-only |
| Gates | `character_gate.py:360` ORDER; `:63` rig (rig kit `validate_character`); `:151` palette; `:212` cuboid; `:315` hair (generator params only); `:328` silhouette (`EDGE_SHARE` `:39`) | | silhouette needs renders |
| Rig | `rigs/human16_v1/rig.json` | 16 bones, body < 700 tris, prop <= 200, height 0.948-2.314 m, segment-length ranges, 7 required + 6 combat clips, STEP 15 fps x 16 keys | `human16_v2` and the `n64_stocky` preset named in the commission do not exist in this tree (`git grep`: 0 hits). Both references and the generated people use human16_v1; human16_v3 has the same bones with adult rest heights 1.392-2.324 m |
| Clip pack | `rigkit/clips.py:178` `attach_clips` | writes the pack's clips onto any human16 body, grounding per key, deformation guard | |
| Exporter | `nbchars/scene.py` (Scene model), `nbchars/writer.py` (Scene -> GLB), `nbchars/__init__.py:20` `_BUILDERS` | a registered item kind builds in the export child | the parity fingerprint (`nbchars/select.py:13-16`) covers `api.py`, not `__init__.py`. The verdict is already STALE at base, so `auto` picks Blender wherever Blender exists |

## 2. Measured style card (both references; full numbers in the card)

| Metric (fraction of height unless stated) | Range | Stock cast for contrast (pp_engineer, fv_scribe, fv_smith, new_arrival) |
|---|---|---|
| height | 1.700-1.713 m | 1.60-1.79 m |
| heads tall (neck joint to top) | 4.84-4.87 | 3.98-4.17 (bigger heads) |
| head width incl. hair | 0.223-0.320 | 0.168-0.220 |
| shoulder joint span / hip joint span | 0.178-0.232 / 0.121-0.156 | narrower shoulders, wider hips |
| upper arm / forearm (joint to joint) | 0.127-0.129 / 0.150-0.152 | |
| thigh / shin | 0.176-0.196 / 0.226-0.241 | shorter shins |
| ankle joint height | 0.097-0.099 | lower |
| hand length / width | 0.105-0.122 / 0.068-0.085 | 0.068-0.073 (small hands) |
| boot length / width / height | 0.214-0.224 / 0.144-0.150 / 0.093-0.100 | 0.10-0.15 wide |
| limb radius median: upper arm, forearm, thigh, shin | 0.033-0.049, 0.043-0.055, 0.052-0.055, 0.060 | |
| triangles | 698 (< 700 rig budget): head 25-27 %, torso 13-14 %, arms 14-16 %, hands 7-8 %, legs 28-29 %, feet 9 % | 684-696 body + props |
| vertices | 921-948 (95 % share a position: UV and normal splits); normals smooth (median 35 deg from face normals) | |
| texture | one 64x64 atlas, 1 material, KHR unlit, n64 kind `baked_unlit`, sampler linear / linear-mipmap, vertex colours all white | 3-4 materials, 128 px + face atlas |
| atlas use | 20-23 % of texels covered; head 44-58 % of the UV area, legs 17-23 %, arms 7-12 %, torso 6-9 %, feet 8-9 %, hands 3 % | |
| colours | 28-29 unique (90 % of texels in 20-22) | 8-16 |
| luminance p05 / p50 / p95 | 0.06-0.11 / 0.20-0.35 / 0.78-0.79 | |
| neighbour step mean / flat-neighbour share | 0.076-0.086 / 0.36-0.41 (soft gradients, not flat fills) | |
| 2x2 checker (ordered dither) share | 0.014-0.023 (no ordered dither) | |
| UV-border / interior luminance | 1.07-1.14 (no edge darkening at island borders) | |
| baked light: up-facing minus down-facing luminance | +0.04 to +0.17 | |
| saturation mean | 0.31-0.55 | |
| rig and clips | human16_v1, identity rest rotations, STEP clips of 16 keys over 1 s | |
| front/side mask IoU between the two references | 0.585 / 0.675 (the card ranges are an envelope of two different bodies) | |

The commission asked for "dither/edge-darkening rules from the card". Measured: no ordered dither and no border
darkening. The rules the card does support are soft baked gradients (step mean about 0.08), top light (+0.04 to
+0.17), a narrow luminance range per material and 28-29 colours after median cut. The commission's "8-16 colour
indexed palette" is read as 8-16 base colours per character. Each base colour gets a baked shading ramp, and the
atlas is then reduced to at most 29 colours, the card maximum. That decision is reported, not hidden.

## 3. Design (smallest that meets the request)

1. **Data** `characters/creator/creator.json`:
   - card targets, copied from the card; a test keeps them equal
   - builds: stocky, lean, tall, child, bulky, average
   - species presets: human, elf, dwarf, goblin, robot, animal-person (cat/fox/bear/rabbit ears + muzzle + tail)
   - face styles: dot, round, anime, sleepy, visor, goggles
   - module library: hair masses (crop, spiky, long, bob, ponytail, bun, mohawk, bald), beards (stubble, short,
     long, wizard), hats (wizard, star-wizard, cap, beanie, helmet, hood, crown, top hat), cape, backpack, belt,
     boots (heavy, plain, shoes), gloves, glasses, goggles, ears, horns, tail, apron, scarf
   - a 16-name base palette with skin and tone ranges
2. **Builder** `adventure_maker/charcreator/` (numpy and PIL only):
   - `mesh.py`: a welded body. The torso is lofted from 8-vertex rings. The legs are 6-vertex lofts that share the
     pelvis ring and a crotch vertex. The arms are 6-vertex lofts from side openings. Hands and boots are lofted.
     The head and neck use 8-vertex rings. Modules are separate pieces inset into the body, so the rig kit's
     connectivity check sees them joined. Skin weights blend 50/50 on joint rings; modules are rigid on one bone.
     Everything derives from (recipe, seed); there is no randomness without the seed.
   - `paint.py`: per-part UV rectangles in one 64x64 atlas. Head area about 45-55 %. Shading per base colour: top
     light, a gloss band, soft gradient and low noise, then median-cut reduction to at most 29 colours. The face
     style is painted on the head front.
   - `scene.py`: builds an `nbchars.scene.Scene`, writes it with `nbchars.writer`, then calls
     `rigkit.clips.attach_clips(rig='human16_v1', ground='match', guard=True)` for all 13 pack clips. Material:
     KHR unlit, `baked_unlit`.
   - `render.py`: software renderer for contact sheets. Views are front, back, side and three-quarter, with a
     key/fill/ambient approximation of the card lighting. It also writes transparent renders, so the silhouette
     gate runs.
   - `__main__.py`: the export child (`python -B -m adventure_maker.charcreator build --job J --out D`). It goes
     through `Runner` like the existing exporter child, so the child-environment rule holds.
3. **Tool routing** (`character_tools.py`, no schema change):
   - `style=creator64` on propose returns 3 creator variants. A project `characters/style.json` with
     `lock: creator64` makes it the default.
   - `edit` and `build` dispatch on `recipe.body == 'body.creator'`. `list what=styles|bodies` and `info id=creator64`
     show the creator.
   - Edits map onto the existing kinds:
     - `height value`
     - `build head/shoulders/waist/legs/age`
     - `hair style/color`
     - `color slot role`: "cloak to green" is `slot=cape role=green`
     - `swap part [value]`: `value` scales the module, so "hat taller" is `swap part=hat.wizard value=1.4`
     - `face preset/expression/eyes/beard`
     - `prop part`
     - `name`
4. **Gates**: the existing `character_gate.run` with the creator palette as `palette_hex`, the software renders and a
   rebuild for determinism. Card fit is measured with the same functions as the card (`tools/charcreator_measure.py`
   logic shipped as `charcreator/measure.py`) and reported, not used as a new blocking gate. No existing threshold
   changes.
5. **Phase C**: create_flow cast members whose brief words describe a person (role, species, outfit) are built by the
   creator when the gates pass. A brief that names no characters gives byte-identical outputs.
6. **Privacy**: no reference bytes, names or likeness enter the package. A new test hashes and name-scans the
   package against the private folders when they are present.

## 4. Risks and stop rules

- The rig-pack clips were authored on a 1.63 m body. Large boots or a big head may trip the deformation guard or the
  floor check in roll/death. Stop rule: 3 small generator iterations per blocker, then report the numbers. No gate
  edits.
- The budget is < 700 body triangles. Module combinations are budgeted in the compiler: a refusal or a named drop,
  never a silent one.
- How the characters look is the owner's call. Renders go out with factual notes only.
