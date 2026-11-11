# Six bounded mesh recipes

These six original recipes are complete, executable **JSON data**, authored for AGEN from the real signatures in `kits/core/meshkit.py`. The canonical files below ship with the generator skill; links point to the entire recipe, not pseudo-code. All declare CC0-1.0 as the author's licence declaration. This records a declaration, not legal verification. Colours and texture strokes come only from the chosen pack, including project mood packs.

| Need / canonical recipe | Construction | Bounded parameter | Floor-centred result |
|---|---|---|---|
| [Crystal spire](../../skills/hermes64-generators/recipes/crystal_spire.json) | Three six-sided lathes: stone footing, glass-role shaft ending in a pole, trim collar | height 1.8–3.0 m, default 2.4 | structure, crown socket |
| [Bookshelf with books](../../skills/hermes64-generators/recipes/bookshelf.json) | Back box; mirrored side box; four repeated shelves; three rows of five individual book boxes | width 1.3–1.6 m, default 1.4 | furniture, 15 visible separate book solids |
| [Potion bottle](../../skills/hermes64-generators/recipes/potion_bottle.json) | Five-ring lathe, separate cork lathe, paper label box | 5–8 radial segments, height .36–.64 m | prop; opaque pack glass, no translucent liquid simulation |
| [Wizard staff](../../skills/hermes64-generators/recipes/wizard_staff.json) | Three-point five-sided wood tube; five-sided collar and faceted crown | shaft 1.0–1.25 m | prop, grip socket; no character attachment |
| [Spellbook on lectern](../../skills/hermes64-generators/recipes/spellbook_lectern.json) | Stone base, wood post, tilted top, mirrored covers and page blocks | height .7–1.15 m | furniture; open two-leaf book, no text |
| [Rune circle](../../skills/hermes64-generators/recipes/rune_circle.json) | Twelve-sided, three-section torus and six radially repeated raised bars | radius .48–.70 m | prop; **abstract marks, not a glyph alphabet or readable runes** |

## Worked example: new bottle from primitives

Copy `potion_bottle.json`, keep its format and licence, change its id to a generic name. The `lathe.profile` pairs are `[radius, height]`, strictly increasing in height. Its first and last nonzero radii are capped by meshkit. Six sides and a handful of profile bands keep it below the prop budget; a paper-role box gives the pack's existing painted paper surface instead of a new texture path. `smooth:true` affects normals, not triangle count.

```json
{"primitive":"lathe","role":"glass","smooth":true,
 "args":{"profile":[[0.10,0],[0.16,0.08],[0.16,0.24],[0.065,0.34],[0.065,0.42]],"segs":6}}
```

For a short vial, reduce the bounded height and its profile ratios rather than replacing the pack's glass with an arbitrary purple. For a faceted bottle set `smooth:false`; segment count still stays bounded. Every parameter's minimum/default/maximum is screened independently; this is not an exhaustive Cartesian-product sweep.

## Archetype notes

- **Crystal:** a zero-radius last ring is a pole, not a flat cap. The collar intersects the shaft intentionally as separate nodes; this does not fuse them into one watertight object. Glass is the selected pack's material role, not guaranteed physical transparency.
- **Furniture:** repeated solid books are intentionally box geometry. Their separate nodes avoid one giant disconnected polygon soup. Bounds cover the shelf as a whole, not a wall-mount exception.
- **Tube:** the staff uses a small bend with distinct path points, closed caps, and a collar around the top. Its grip socket is metadata only; animation/hand attachment remains the character lane.
- **Tilted boxes:** transform local boxes first, then move to the lectern height. Mirroring is about world x=0; the two leaves remain symmetric.
- **Radial repeats:** apply the bar's translation before the repeat rotation. Six bars and one torus are 144 triangles; no emissive glow or glyph image is smuggled through a texture path.
- **Other primitives:** `loft` accepts equal-length closed rings; `blob` is the bounded faceted ellipsoid primitive; `prism` extrudes a finite 2D outline; `card` is an explicitly open `kit_card_` node; `grid_surface` uses a finite `(nv+1)*(nu+1)` height table, never a callback from JSON. See the schema for exact argument names.

## Run any recipe in a project's mood

```sh
python -B -m adventure_maker.gen_tools author --project PROJECT --recipe skills/hermes64-generators/recipes/potion_bottle.json --model SESSION_MODEL --brief-line "potion bottle"
python -B -m adventure_maker.gen_tools screen --project PROJECT --id gen:potion_bottle --pack castle_keep_purple_dusk
python -B -m adventure_maker.gen_tools build --project PROJECT --id gen:potion_bottle --pack castle_keep_purple_dusk --seed 7
```

The pack must already exist under `PROJECT/kits/packs/ID/pack.json` or in the shipped pack library. The CLI does not silently pick another mood. Native mesh/file checks, deterministic replay, bible checks and texture fidelity are machine measurements. Frame gates require the room capture. Appearance is for the owner to judge; no aesthetic grade is implied by passing.
