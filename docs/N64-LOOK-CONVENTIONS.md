# N64 look conventions

One shared, theme-agnostic convention for how Hermes64 frames look: the original-1998 N64 art direction
(soft, vertex-lit, low-res filtered textures, fog matched to a painted sky, organic low-poly shapes), written down here
and encoded as data in **`kits/core/n64_look.json`**. Every pack, kit build and future style profile inherits it; packs
supply colours and environment data only. Nothing in code names Thaw, Last Light, polar or forest.

Status: lane N64-FIDELITY. Gate: `adventure_maker/n64_gate.py` (section `n64_fidelity`). Evidence and numbers:
`docs/N64-FIDELITY-AUDIT.md`, `docs/N64-FIDELITY-RESULT.md`, `docs/n64fidelity/CRITIQUE-*.md`.

## Where the convention lives and how it flows

| layer | file | reads it |
|---|---|---|
| convention (source of truth) | `kits/core/n64_look.json` | kit texture generators (`kits/core/texgen.py`), the gate, the runtime |
| pack override (explicit, rare) | `packs/<pack>/view.json` `"n64": {...}` | merged over the convention (recursive, pack wins) |
| runtime copy | `theme.json "n64"` (`adventure_maker/assets_v3.runtime_snapshot` -> `n64_look`) | `runtime/godot/look/rig.gd` (`Rig.conv`), `view/assets.gd`, `view/presenter.gd`, `view/room.gd`, `actors/assets.gd` |
| environment data | `packs/<pack>/view.json look.profiles.<name>` with `"environment"` | `rig.gd apply()`; ranges checked by `tests/test_n64_conventions.py` |

The kit source fingerprint includes `kits/core/*.json`, so changing the convention invalidates cached kit builds.
A theme without `"n64"` (runtime-only test packs) keeps the legacy behaviour exactly.

## Output

- Fixed 320x240 internal frame (4:3) shown 3x in the 960x720 window with **bilinear** upscaling, no sharpening
  (`output.upscale_filter`). Integer 3x fit; the window is 4:3, so no letterbox is needed at the default size.
- Polygon edges antialiased with 4x MSAA (`output.edge_aa`), standing in for the RDP's coverage antialiasing. The
  capture harness switches MSAA off for its exact-colour passes (key, distance, region mask) so gate inputs stay exact.
- No output dither (`output.dither = "none"`): the VI's dither filter hid most of it on hardware, and textures are
  already low-colour.
- **PS1 tells are never used**: no vertex snapping/jitter, no affine texture warp (`output.vertex_snap = false`,
  `output.affine_uv = false`). `tests/test_n64_conventions.py` asserts the shaders contain neither.

## Texture filtering

- World surfaces: `filtering.world = "n64"`: three-point (triangle) filtering when a texel covers more than a pixel,
  the mip chain when minified, biased by `filtering.lod_bias` (-0.75) toward detail so distant ground keeps its painted
  blotches without the sparkle of unmipmapped sampling.
- Characters: `filtering.actors = "three_point"` on un-mipmapped textures (expression atlas cells never average). Face
  atlas materials clamp the filter footprint inside their cell, so a soft filter never bleeds the neighbouring
  expression into a face.
- Env (chrome/glass sphere maps): bilinear.

## Lighting model (same everywhere, different data)

Gouraud lighting like fixed-function T&L: baked vertex colour x (ambient + sky/ground hemisphere + key + fill + up to 4
point lights), interpolated across triangles.

- `lighting.per_pixel_point_lights = false`, `specular_glints = false`, `fresnel_rim = false`, `per_pixel_gloss = false`:
  the runtime gate global `n64_classic` is derived from these; pack data cannot switch them back on except through an
  explicit `"n64"` override (and the gate then fails it).
- Point lights on static surfaces are sampled on a **virtual vertex lattice** of `lighting.lattice_m` (1 m) and
  trilinearly interpolated: what vertex lighting on a tessellated N64 floor shows (soft polygonal pools), without per-pixel
  circles and without wedges smeared across large triangles. Characters keep true per-vertex lighting.
- Bounce light reaches ceilings through the ground hemisphere term (data), never through a fresnel rim.
- Lamp **pools** are painted floor decals (`lighting.lamp_pool.max_strength` 0.3; optional `pool_color` per emitter so a
  warm pool stays warm-white on a cool floor). Lamp **halos** are glow billboards hugging the lamp
  (`lighting.halo.max_size_m` 1.2, `max_strength` 0.85): N64 lantern/torch glow sprites, never screen-space bloom.
- Emissive surfaces stay near their painted colour (`lighting.emission_max` 0.15).
- **Painted light**: unlit surfaces (screens, light panels, window views) are drawn at `lighting.unlit_level` (0.88)
  of their texture. They keep their gradation and never clip to pure white, the way N64 light textures were painted
  rather than overexposed. On hardware the vertex shade only modulates the texture down; lamp-lit floors are kept
  below white by data (pool strength, floor lift), not by tone mapping.
- **Chrome/glass** = painted sphere-map texture tinted by the room rig, evaluated per vertex like hardware texgen; the
  convention bounds the metal response (`gamma_max` 1.25, `hot_max` 0.2, `hot_from_min` 0.94, `rim_max` 0).
- **Characters** use the world rig; the only extra is a modest kicker from behind the subject for readability
  (`lighting.actor.kicker_max` 0.22, `rim` 0).

## Fog and sky

- Linear distance fog evaluated per vertex (`fog.model`).
- Exteriors: the painted sky gradient melts into the fog colour across `fog.sky_horizon` = [-0.03, 0.12] (sine of the
  view elevation, relative to the top of the far terrain as seen from the room camera; `presenter.fit_sky_horizon`), so
  the visible horizon and the fogged distance share one colour.
- Interiors: fog colour = the room's darkest ambient tone; ceilings are kept off it by bounce light.

## Environment types (data in each pack's look profiles)

Each look profile declares `"environment"`; `kits/core/n64_look.json environments.<type>.ranges` bounds its grade, fog
and rig strengths (checked by `tests/test_n64_conventions.py`).

| type | intent |
|---|---|
| `interior_cool` | blue futuristic: pearl/cobalt values, cool but restrained (greyer blue ambient/bounce, saturation 0.9), no neon, sparing warm practicals |
| `interior_warm` | cottage: soft warm key from the window side, cool-ish fill in the shadows, dark warm interior fog, rafters falling into shadow, warm hearth/lamp/window practicals |
| `exterior_day` | village daylight/dusk: painted sky gradient, fog tinted to the horizon |
| `exterior_night` | night snow field: painted aurora sky, pale snow, fog tinted to the horizon |

## Texel density and texture sizes

Texels per metre by material class (texture size / `tile_m`), the same in every pack (`texel_density.classes`), within
`texel_density.tolerance`. Sizes are powers of two from `texel_density.sizes`. Flat, emissive, view-plane, env and
character roles are outside the table.

| class | texels/m | roles |
|---|---|---|
| ground | 10.67 | field, grass, snow, dirt, sand, path, cap, ice, water |
| rockface | 16 | cliff, rock |
| architecture | 16 | wall, wall_alt, floor, ceiling, stone, roof, door, step, frame, trim |
| furniture | 21.33 | body, body_alt, hull, hull_alt, wood, bark, foliage, flower, post, rail, band |
| textile | 53.33 | cushion, fabric, knit, fur, quilt, leather, rope |
| detail | 80 | paper, book |

`python3 -m adventure_maker.n64_gate library` reports the per-pack spread by class and each texture's high-frequency
energy.

## Texture painting (`textures`, read by `kits/core/texgen.py`)

- Every texel stays a pack palette colour; ramps stay short (3-5 steps).
- Field generators keep their mid-frequency painted structure. They are quantized with an irregular **mottle**
  threshold (`dither_pattern: mottle`: seeded white noise, rank-equalised so the mean colour is unbiased) instead of
  the regular 4x4 Bayer grid. Band transitions become painted mottling, which three-point filtering turns into the soft
  blotchy look of N64 textures. Fully clean bands were tried in round 2 and rejected: the frames went posterised-flat.
- Readable textures (`crisp_gens`: screen, paper, spines) are quantized clean.
- Sky and window cards paint aurora, cloud and haze layers into the gradient as soft masks toward sky-ramp steps
  (`painted_sky`). The runtime blurs the sky card vertically by `filtering.sky_vblur_texels` (3) so the palette bands
  read as one painted gradient.
- A recipe may override `dither` (amount or false), `dither_pattern`, `soften` (wrapped blur passes) or `painted`.

## Baked vertex colour (`bake`, read by `kits/core/bake.py`)

- Per-corner light from the pack light rig, quantized to the pack light ramp. Smooth faces share normals within 55
  degrees.
- `bake.vertex_variation`: painted low-frequency light/dark patches (deterministic value noise of the vertex position,
  +-0.16 of the ramp, 3 m cells) on large terrain roles (cliff, rock, field, grass, snow, dirt, sand, cap). This is
  how N64 artists broke up big faces: with vertex colour, not texture detail.

## Organic terrain (`kits/core/gen_terrain.py terrain.yard`)

No boxed terraces, and no new params (the capabilities contract is frozen):
- each riser is a steep slope with a ragged top, then a rounded lip ring where the tread wraps over the edge;
- a ragged talus band sits at the cliff foot;
- landscape rings use Gouraud shading;
- the organic detail draws from its own seeded stream, so ridge heights, ring jag, exits and paths (the layout) are
  unchanged.

## Gate (`n64_fidelity`)

`python3 -m adventure_maker.n64_gate frames <capture folder>` and `... library`. Thresholds live in
`kits/core/n64_look.json gate` (pack `view.json "n64".gate` may tighten them). They are additions beside the defect gate
in `style_gate.py`, whose thresholds are unchanged. Known-bad controls: the round-0 before frames
(`tests/fixtures/n64fidelity/`), which must fail; unit tests: `tests/test_n64_gate.py`.
