# ROOMLOOK critique 0 — baseline (control)

Sheet: `evidence/roomlook/round-0/sheet-thaw.png` (clean 320x240 captures, nearest x2, beside private reference crops), `sheet-last_light.png`. Gate: `evidence/roomlook/round-0/{thaw,last_light}/style-gate.txt`. Code = assembly HEAD `12388b2` plus capture passes only (clean/no-UI frame, magenta-clear key frame, geometry audit). Nothing about the look was changed.

**Does this look like a finished hand-made N64-era game? No.** Every Thaw room is the same product shot: a rectangular floor slab with two full walls and two 10%-height walls, photographed from outside and above the room. 45–63% of each frame is the flat navy clear colour (measured `void_fraction` 0.45–0.63 interior). It reads as a level-editor preview, not a place.

## Where it looks like a diorama / test scene
- **Framing:** every camera sits 9–11 m outside the room (`camera outside the room shell` in all five interiors). With fog starting at 6 m, the whole room sits inside the fog ramp, which is the real reason everything is washed out.
- **Light:** one generic baked key; no darks (luma p2 0.17–0.24 in every room, refs 0.00–0.14), no white-hot glints (p99.5 0.70–0.78). Walls, floor and furniture share one periwinkle value band. No warm accent anywhere (`accent_fraction` 0 in all six rooms).
- **Fog:** Snow Field has 38% of drawn pixels within 0.07 of the fog colour; Pod Bay 19%. Props dissolve into the floor.
- **Shells:** identical boxes; the curved corridor is straight, the dome has no dome, the pit bowl sits on a flat floor, door frames stand free in front of continuous walls (12 uncut doors across 6 rooms).
- **Windows:** a ring on the wall with wall colour inside; the window kit's view card exists but is hidden behind the wall plane. The pit's tree pokes out above the cutaway.
- **Props:** crt screens, headphones, cards, spheres and mugs hover at 0.8–1.5 m with nothing under them (workstation: 6 floating props). The bell/gear/headphones are re-used radio/flashlight meshes.
- **Dressing:** 4–8 objects on 100+ m² of empty floor. Nothing on walls, no rugs/cables/lamps/cushions; nothing suggests people live here.

## Against the references
The references are dense, enclosed, glossy and contrasty: the camera is *inside* the furniture, chrome reads as near-black mirrored lobes with hard white highlights, windows are saturated navy rectangles with white snow, and the frame is full edge to edge. Round 0 is the opposite on each axis: distant, matte, low-contrast, mostly empty.

## Measured (gate v0, pack-agnostic defaults)
| Room | contrast p95-p5 | luma p2 | p99.5 | fog-swallowed | flat | edges | void | floating | uncut doors | camera |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| conversation_pit | 0.39 | 0.22 | 0.78 | 0.06 | 0.59 | 0.14 | 0.447 | 1 | 1 | outside |
| curved_corridor | 0.45 | 0.22 | 0.78 | 0.06 | 0.46 | 0.19 | 0.629 | 4 | 2 | outside |
| dome_shelter | 0.41 | 0.24 | 0.75 | 0.05 | 0.50 | 0.15 | 0.600 | 2 | 1 | outside |
| pod_bay | 0.35 | 0.23 | 0.72 | 0.19 | 0.67 | 0.13 | 0.628 | 3 | 3 | outside |
| snow_field (ext) | 0.46 | 0.24 | 0.74 | 0.38 | 0.72 | 0.03 | 0.187 | 0 | 2 | (exterior) |
| workstation | 0.43 | 0.22 | 0.79 | 0.04 | 0.49 | 0.15 | 0.569 | 6 | 1 | outside |

All 6 Thaw rooms and all 4 Last Light rooms FAIL the gate (exit 1). This round is the gate's known-bad control.

## Calibration note
Private reference crops measured with the same code: contrast 0.30–0.64 (median ≈0.48), luma p2 0.00–0.14 (one foggy photo 0.32), flat 0.21–0.54, edges 0.10–0.28. The strongest separators between round 0 and the references are darks (p2), void, flatness and the geometry audit, not the contrast range alone. Thresholds will be set per pack in data (view.json `style_gate`), never loosened to pass a round.

## Next (round 1)
Lighting/fog/grade/chrome as pack data + shader (vertex light rig with key/fill/rim/point lights, per-vertex env-map chrome with a designed high-contrast env texture, per-room fog presets, post grade), measured on the same cameras so the effect of light alone is visible before geometry changes.
