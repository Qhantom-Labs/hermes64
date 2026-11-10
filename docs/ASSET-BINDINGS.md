# Asset binding seam

`kits/bindings.json` is the only character selector table. `packs/<pack>/bindings.json` maps semantic environment/prop keys to explicit built variants. `adventure_maker/assets_v3.py` validates hashes and emits a project-local runtime snapshot; `view/assets.gd` loads it without rewriting any story IDs.

## Character identity

Each row has exact `body_id`, `base_rig_id`, and **complete `params` equality**, plus `glb`, `sha256`, `bone_names`, `animations`, `placeholder` and a reason. All authored role profiles from both source stories are covered (22 unique selectors). `expedition_base_v1`/`human_16` and `cat_base_v1`/`cat_8` remain story identities, never aliases for an incompatible built rig.

Current rows point to static generated markers: `placeholder:true`, `bone_names:[]`, `animations:[]`. Suit/coat fields remain in selectors and instance metadata; the markers do **not** depict every costume, pattern or coat distinction. Their visual simplicity is disclosed in captures and the critique.

For the real character lane: place the reviewed GLB inside the bundle, use its exact hash, measured bone names and actual animation names, and edit the matching manifest row. Keep all story identity/params selectors unchanged. Change `placeholder` only when warranted. The loader needs no source change to load the new rigged model. Animation playback/retargeting and deformation testing are separate unfinished work; manifest loading alone is not animation compatibility certification.

## Environment identities

Binding rows retain semantic key, kit ID/preset, relative GLB path and SHA-256. `kit/blob_desk` explicitly selects `furn.console` / `desk_triple_crt`; `kit/sunken_lounge` selects `furn.pod` / `conversation_pit`. Several hero props are approximate kit interpretations, labeled `fidelity`; there is no silent ID substitution. The pickup sphere is an isolated **real KITS orb mesh**, not a table proxy; `ORB-DERIVATION.json` records its source/output hashes and translation.

`n64_v0` is an explicit compatibility pack mapping Last Light to `forest_village` kit geometry/materials and the LOOK harbor UI palette. It is not a nonexistent original LOOK pack. The resulting warm kit treatment is functional, not a bespoke finished lighthouse art direction.

## Colour and provenance

`PROVENANCE.json` records every copied file's original lane-relative source, destination, SHA-256, byte count and lane CHECKPOINT/RESULT receipt hashes. It describes **original copied bytes**, even when an assembly fix subsequently changes a destination. `docs/GLB-TRANSFORMS.json` records original and transformed GLB hashes. The derived `kits/manifest.json` preserves each original source hash alongside relocated paths and measured transformed hashes/counts; the copied original is `kits/library/manifest.json`.

All library `COLOR_0` arrays are normalized unsigned bytes (component type **5121**), with `asset.extras.vertex_color_encoding == "srgb8"`. This deliberately stores display-space values, **not glTF-standard linear colour semantics**. The N64 shader uses `vcolor_is_linear:false`; a generic viewer may show wrong lighting. Embedded source textures remain intact, and chrome/glass env maps are loaded from each pack's env library.

## Build/cache

The real builder uses KITS 3.1 parameter recipes via Blender headless. Cache keys include requested ID/params, seed, pack recipe, source generator/validator bytes and conversion version. A cached GLB must match its retained hash; modified cache bytes fail, not silently pass. Default floor/wall recipes and selected presets build; immutable prebuilt semantic library entries are hash-verified, not unnecessarily rebuilt.

Fresh builder sidecars must say passed and hash-match. The adapter independently counts GLB index triangles, enforces each kit's own budget, normalizes colour encoding and records original/final hashes. Per-asset source validation covers bounded recipe palette/texture/topology checks; screenshot reports conservatively count whole instantiated room meshes, including hidden collision floor, against 6,000 triangles. This is **not** self-intersection proof for arbitrary assembled rooms, exact final-pixel palette quantization or human style approval.
