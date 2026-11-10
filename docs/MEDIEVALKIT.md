# MEDIEVALKIT

Original medieval village and castle environment kits for the existing Hermes64 N64-style renderer. The target is painted, softly filtered, vertex-lit late-1990s fantasy, not voxels, Minecraft, PBR or flat-colour modern low-poly art.

## Contents and entry points

- `kits/core/gen_medievalkit_*.py`: seven new geometry/painting/support modules. Only shared-source change: the added generator-import line in `kits/core/pipeline.py`.
- `tools/medievalkit_packs.py`, `medievalkit_style.py`, `medievalkit_presets.py`: authored pack data and geometry presets.
- `kits/packs/{medieval_village,medieval_village_dusk,medieval_village_night,medieval_village_snow,castle_keep}/pack.json`: 32-colour kit palettes, material-role recipes and bake rigs.
- `packs/<same IDs>/{pack,view,bindings}.json`: normal plugin style packs, room looks and hashed asset bindings.
- `kits/library/medievalkit-manifest.json`: **1,140 builds**, **228 per variant**. This is 227 lane pieces plus the existing `sky.backdrop` generator per variant. Every default and named pack preset is built.
- `kits/library/medievalkit-sockets.json`: **227 lane pieces**, grid/anchor definitions and 10 connector rules.
- `examples/medievalkit-demo/spec.json`: four-region demo, The Wayfarer's Audience.
- [Piece inventory](medievalkit/INVENTORY.md): every generator, preset count and triangle range, generated from the manifest.
- [Results and limits](MEDIEVALKIT-RESULT.md), [merge/hub notes](MEDIEVALKIT-HUB-ENTRIES.md), [best-six sheet](medievalkit/best6.png).

| family | new generators | pieces including presets, per variant | coverage |
|---|---:|---:|---|
| `vlg.` | 16 | 53 | Four cottage styles; tavern, smithy, wind/water mill, chapel, stalls, wells, bridges, town walls, fences, gatehouse, stairs, room shell, ceiling, hearth, doorway |
| `cst.` | 20 | 49 | Round/square towers, curtain walls, battlements, gatehouse, portcullis and drawbridge state pairs, keep, hall/dungeon shells, ceiling, throne/dais/carpet, pillars, original banners, lights, cells, spiral stair |
| `mprop.` | 23 | 62 | Barrels, crates, sacks, buckets, baskets, hay, woodpile, carts, anvil, cauldron, trough, tables/benches, chests, beds/shelves, weapon racks, shields, tableware, blank sign frames, lanterns |
| `mnat.` | 10 | 34 | Oaks, pines, orchard trees, bushes, hedgerows, rocks, stumps/logs, flowers/reeds/mushrooms, dead trees, cultivated fields |
| `mter.` | 5 | 29 | Ground/path pieces, hills, banks, river/moat/pond, distant hill/mountain/castle silhouettes |
| existing `sky.` | 0 | 1 | Painted sky dome, rebuilt with each medieval palette |
| **lane total** | **74** | **227** | **1,135 lane builds across five variants**, plus five core sky builds |

Counts correct the early checkpoint's provisional family counts. No character generator or new tool was added. People use the existing forest actor-library looks; medieval-specific costumes are not supplied.

## Palette roles and lighting

All five variants share the same 32 named entries and ten roles. Painters resolve names through the active pack, rather than hardcoded texture RGB. Roles are audited for complete, non-overlapping coverage.

| role | named steps | purpose |
|---|---|---|
| shadow | `ink`, `umber` | Contact shadows, iron/wood seams |
| timber | `oak_0..2` | Weathered oak, beams, furniture |
| whitewash | `daub_0..2` | Plaster, cream practical-light cores |
| thatch | `straw_0..2` | Straw roofs, hay, restrained heraldic yellow |
| stone | `stone_0..4` | Rubble, ashlar, flagstones, winter haze |
| roof | `slate_0..1`, `clay_0..1` | Slate and tile roofs |
| foliage | `leaf_0..4` | Grass, trees and crops; blue-green moonlight or frosted tips in variants |
| sky | `sky_0..1` | Painted sky bands |
| heraldry | `red_0..1`, `blue_0`, `gold_0` | Original chevron/cross/pale/roundel charges and small gilt accents |
| lantern | `lamp` | Baked practical highlights; not a sunlit roof colour |

- Day: cream key, blue sky fill, green bounce, pale warm horizon.
- Dusk: peach horizon and dusky blue zenith; low cream key; illuminated windows. The rejected violet-blue-hour version is retained in earlier evidence.
- Night: navy zenith, slate-blue horizon, blue-green foliage, lit windows. This is deliberately readable moonlight, not black-night realism.
- Snow: snow role recipes on roofs/paths/ground and frosted tree tips. Interiors remain sheltered and firelit.
- Castle Keep: grey ashlar and slate with red/gold heraldry. `hall` and `dungeon` look profiles supply torchlit interiors; there is **not** an additional standalone `castle_keep_torchlit` pack.

Each pack supplies `village`, `bailey`, `tavern`, `hall`, `dungeon`, `exterior` and `interior` look profiles. Painted textures, baked height/ray AO, optional baked point pools and the existing runtime's capped vertex-light rig work together. Half the baked interior light's chroma is neutralized so a nominally neutral oak floor does not become the frame's warm accent. Practical pools are warm white rather than saturated straw. Snow bailey uses a lower winter key to separate stone from horizontal snow.

The full-bright sky's tint/emission response compensates for its baked vertex step and `unlit_level=0.88`. Godot's colour-parameter linearization is included in the calculation and unit test. The far mountains can hide the lowest painted horizon from camera b: the remaining N64 horizon mismatches are reported, not waived.

### Gates, without a threshold change on resume

The pre-existing lane style gate uses the core defaults or stricter values **except** `white_point_min=0.60` (core 0.80) and `contrast_range_min=0.40` (core 0.42). These deviations were already authored before resume, following the dungeon lane's calibration, and are explicitly recorded in `STYLE_GATE.note`. Accent means hue 8–55°, saturation at least 0.4, at most 15% of a frame. These are **not** claims that unmodified core-default thresholds passed.

This resume did not change any gate threshold, N64 convention or validator. It fixed the scene and look data. Final selection: **20/20 style-gate captures, 80/80 rooms**. N64 fidelity: **14/20 captures, 74/80 rooms**. The exact failing measurements are in the result document. A cuboid fraction is a structural control, not an aesthetic classifier.

## Grid and room compiler

`tools/medievalkit_rooms.py` compiles a lane plan to the ordinary room and presentation data consumed by the plugin. It is a local authoring helper, not a new plugin action.

- Cell: **4 m**; half cell: **2 m**. Village storeys, castle storeys, wall inset, doorway cut and apron values are in the socket manifest.
- Engine coordinates: glTF +Y up, +Z front/south; grid pieces turn in 90° steps.
- Room plot dimensions: cells × 4 m, with a 0.5 m apron on each side. Door placement uses the runtime's existing 0.4 m anchor inset.
- `cell`, `block`, `edge`, `door_to` and `attach` placements resolve anchors. Metric free placement is restricted to free/lot/landmark pieces.
- Door sockets require corresponding declared doors, and declared doors require cuts. Torch, lantern and hearth sockets auto-mount their respective pieces. Wall decorations require compatible sockets.
- Portcullis/drawbridge sockets take matching state pieces; the portcullis switches to its raised asset when `gate_open` is true.
- Budget estimate counts kit pieces, door frames and people. Runtime measurement is authoritative: estimates are not exact (final square 5,832 estimated vs 5,936 measured).

## Verification coverage

| method | coverage | limitation |
|---|---|---|
| Budget, naming, palette, origin, topology/intersection validators | Every one of the 1,140 listed builds | Default plus authored presets, not all numeric extremes/combinations |
| Role audit | Five kit palettes and referenced material ramps | Does not certify every lit pixel's hue; runtime gate does that |
| Cuboid gate | Listed structural families in `NO_CUBOID`, max 50% plain-box triangles | Does not prove artistic quality or test every prop silhouette |
| Socket gate + room compiler | Manifest anchors/ends/cuts and actual demo assembly; 10 connector rules | Not a continuous collision or watertightness proof |
| Water gate | Actual water material parameters and library GLBs | No fluid simulation or swimming validation |
| Determinism | Two independent builds of all 1,140 jobs; both equal the library | Seed 0; Python builder, not Blender |
| Real runtime | Four rooms × four views × five variants, with clean/character-close-up passes | Not all 227 pieces placed in demo scenes; no human acceptance |
| Story proof | Actual service scaffold → compile → check: 60 core states, 263 edges, reachable audience | Spatial reachability is an explicit abstraction, not physically proved |
| State swap | Additional day view-a capture with `gate_open` true | Starts open; not an end-to-end keyboard playthrough |

## Rebuild and capture

Python 3.9 and the installed numpy/Godot are used; no installs or network needed. Run from this worktree. Do not run two library writers concurrently.

```sh
python3 -B -m tools.medievalkit_packs write
python3 -B -m tools.medievalkit_style write
python3 -B -m tools.medievalkit_library all --jobs 8
python3 -B -m tools.medievalkit_demo write
python3 -B -m tools.medievalkit_library verify
python3 -B -m tools.medievalkit_library determinism --jobs 8
python3 -B -m tools.medievalkit_controls
python3 -B -m tools.medievalkit_demo plan
python3 -B -m tools.medievalkit_demo capture --round REVIEW --variant medieval_village --view a
python3 -B -m tools.medievalkit_demo capture --round OPEN --variant medieval_village --view a --flags gate_open
python3 -B -m unittest tests.test_medievalkit tests.test_n64_conventions tests.test_n64_gate tests.test_schema_budget
sh tools/verify_all.sh
hermes plugins validate .
```

Check `ps` and the process cwd before running `verify_all.sh`; other lanes can be verifying simultaneously. Never overwrite a retained capture round accidentally: the capture helper replaces an existing directory with the same round/variant/view/flags tag.

Raw captures/projects remain under gitignored `evidence/medievalkit/`. Committed review sheets and the selected reports live under `docs/medievalkit/`. All remaining limitations and full-suite failures must be carried forward from `MEDIEVALKIT-RESULT.md` and the checkpoint.
