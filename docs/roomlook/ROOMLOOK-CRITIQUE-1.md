# ROOMLOOK critique 1 — light rig, chrome, fog, grade (same cameras)

Sheet: `evidence/roomlook/round-1/sheet-thaw.png`. Gate: `evidence/roomlook/round-1/thaw/style-gate.txt`.

## What changed (all data-driven)
- `n64_world.gdshader`: per-vertex room rig (hemisphere ambient, key, fill, view rim, 4 point lights, Blinn spec), per-vertex sphere-map texgen from the reflected view vector, env "chrome" path that keeps white glints white under coloured tints, gloss highlights on baked surfaces from the env map's white features only, colour grade (exposure/lift/gain/gamma/saturation/contrast), baked-light desaturation so the rig supplies hue. Legacy packs without a `look` block render as before (`n64_mode.w = 0`).
- `look/rig.gd` + `packs/polar_pod/view.json look`: interior / warm_interior / exterior profiles, per-role material response (gloss/spec/rim/tint/emission), emitters keyed by asset ref or kit id (lamps, screens, windows, warm pipes, heated path, dome glow) with optional floor pools, halos and per-instance role tints.
- Kit pack env maps redesigned in data (`kits/packs/polar_pod/pack.json env_maps`) via a backward-compatible split-studio painter (`texgen.paint_env` below/above/horizon/rim/panels): dark navy floor reflection, white horizon line, pale ceiling with light panels and hard glints. Regenerated through Blender (`tools/kits_refresh.py --packs polar_pod`); manifest/bindings verify clean (113 builds, 294 binding rows, 0 problems).

## Does it look like a finished hand-made N64-era game? No.
The light is better: chrome stools and the pit rim now read as glossy mirrored metal with white rim highlights; walls carry a real gradient from saturated cobalt in shadow to pale periwinkle; darks exist (luma p2 0.03–0.11 indoors vs 0.22–0.24 in round 0); highlights reach white (p99.5 0.94–1.0). But the frame is still a diorama: 45–63% void around a box seen from outside, so better light just makes a nicer product shot.

## Still wrong
- **Framing/void** unchanged (the next round's job).
- **Floors are flat**: one big slab with vertices only at its rim, so per-vertex lamp light never reaches the middle of the room; a warm pool on a saturated blue floor turns lilac, not warm. Measured warm accent fraction is 0.000 in all six rooms. Fix needs tessellated floors (vertex density for Gouraud pools), darker floor values near walls, and warm emissive surfaces (lamp shades/mug) large enough on screen.
- **Big reflection wedges**: on a 12 m floor triangle the per-vertex env coordinate sweeps across the light panel and paints a white wedge (authentic texgen artefact, ugly at this scale). Floor gloss lowered to 0.22; real fix = floor tessellation.
- **Snow Field** still lacks darks (p2 0.21): uniform snow slab, no sky dome, no silhouettes.
- **Flatness** 41–54% of 3x3 neighbourhoods: large untextured-looking wall/floor planes.

## Compared with the references
Closer on material (gloss + white glints on chrome, deep blue shadows) and palette (gate palette adherence 1.00). Far on everything spatial: references are enclosed, dense, eye-level; ours is distant, empty and open-topped.

## Gate (pack thresholds now in data)
All 6 rooms still FAIL (void, floating props, uncut doors, outside cameras, flatness, no accents). Darks/highlights/exposure checks now pass in most rooms.
