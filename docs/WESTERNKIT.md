# WESTERNKIT: frontier town and canyon style profiles and kit families

The lane adds an original wild-west / frontier pack to the kit system in the Ocarina-era N64 look:

- four style profiles: `frontier_town` at noon, golden hour and night, plus `canyon_mesa`;
- six deterministic kit families: town architecture, rail, mine, props, nature / terrain and sky backdrops;
- a FRONTIER GRID socket manifest with a room compiler that builds rooms from data;
- a five-room demo, "Redwater", run through the plugin's normal path.

It follows the DUNGEONKIT method: generators in `kits/core`, pack data, presets, painted textures by code, sockets,
gates, controls and critique rounds. All names, places and designs are original. No franchise assets, names, logos or
silhouettes are used.

Status, commands and the real outputs are in `docs/WESTERNKIT-RESULT.md`. Merge notes for the hub and catalog are in
`docs/WESTERNKIT-HUB-ENTRIES.md`.

## 1. Files

| file | what |
|---|---|
| `kits/core/gen_westernkit_paint.py` | Painted field generators registered into `texgen.FIELD_GENS`: lap / board-and-batten siding, plank decks, shingles, corrugated tin, adobe, brick, fieldstone, layered sandstone, desert ground with ruts, sage, cactus ribs, wallpaper, the back-bar bottle shelf, blank posters and sign boards, window panes, plank doors, spoked wheels and the frontier sky. Structured features sit exactly on ramp steps. |
| `kits/core/gen_westernkit_base.py` | FRONTIER GRID constants (`CELL` 4 m, `APRON` 0.5 m, `WALL_T` 0.12 m, storey 3 m, doorway 2.4 × 3.0 m, door anchor 0.1 m behind the lot line). Shared geometry: hewn six-sided tapered posts, chamfered boards, section beams, sweeps, lofted rock blobs, rock sheets, spoked wheels, gable / shed roofs, railings, windows, cards, and `planar_uv`, which runs siding level, shingles along the eaves and tin down the slope. |
| `kits/core/gen_westernkit_town.py` | `wtown.*`: 19 generators (buildings, facades, boardwalks, porches, balconies, interiors). |
| `kits/core/gen_westernkit_rail.py` | `wrail.*` (8) and `wmine.*` (12): track, station, trestle, rolling stock, tunnels, portal, mine gear. |
| `kits/core/gen_westernkit_props.py` | `wprop.*`: 24 prop generators. |
| `kits/core/gen_westernkit_land.py` | `wland.*` (16) and `wsky.*` (3): canyon walls, mesas, buttes, arch, hoodoos, boulders, ledges, dry riverbed, ground, talus, scrub, yucca, dead tree, grass, palm, oasis; sky dome, distant mesa ring, sun disc. |
| `kits/core/pipeline.py` | **One added import line** (the only edit to a shared file). |
| `tools/westernkit_packs.py` | Kit packs `kits/packs/<variant>/pack.json`: one shared 32-colour palette in 10 roles, materials, light rigs and ramps, fog, presets. |
| `tools/westernkit_presets.py` | Generator presets shared by all variants (one library build each). |
| `tools/westernkit_style.py` | Style packs `packs/<variant>/pack.json` and runtime themes `packs/<variant>/view.json`: look profiles, emitters, the style-gate thresholds. |
| `tools/westernkit_gates.py` | Data gates: cuboid share, socket grid, water bounds, palette-role audit. |
| `tools/westernkit_library.py` | Library build (4 variants, parallel), side manifest, bindings, socket manifest, geometry/role gates, shared N64 texture-library gate, verify, determinism, QA sheet. |
| `tools/westernkit_rooms.py` | Room compiler: plan → spec room + presentation, every connector rule checked. |
| `tools/westernkit_demo.py` | The Redwater demo (5 rooms × 4 cameras), capture through the plugin, critique sheets. |
| `tools/westernkit_controls.py` | Five known-bad controls; each must be rejected. |
| `tools/westernkit_moods.py` | Reference-to-pack check: two code-painted mood images → `refpack` → compare. |
| `tools/westernkit_identity.py` | Byte-identity sweep of the existing generators against a `git archive main` export. |
| `tests/test_westernkit.py` | Pure-python suite: data current, roles, gates, library hashes, determinism, identity, rooms, controls. |
| `kits/library/{frontier_town,frontier_town_golden,frontier_town_night,canyon_mesa}/` | Built GLBs (explicit sRGB8), textures, env maps, palettes. |
| `kits/library/westernkit-manifest.json`, `westernkit-sockets.json` | Side manifest (every build hashed) and the snap-socket manifest. |
| `packs/<variant>/bindings.json` | Hash-pinned bindings, including `arch.door` → `wtown.doorway`. |
| `examples/westernkit-demo/spec.json` | The demo spec (generated). |
| `docs/westernkit/` | Critique rounds, critique sheets, best-6 sheet, refpack check, main-hash sample. |

## 2. Style profiles

One palette serves all four profiles, so every kit is recolourable by role. Variants change light, fog and sky;
`canyon_mesa` also remaps terrain ramps and golden hour gives the street path a lighter ramp. There are 32 colours in 10 roles:

| role | colours | use |
|---|---|---|
| `shadow_violet` | void, shade_0..2 | cool desert shadow steps, night |
| `desert_sky` | sky_0..3 | deep blue zenith → pale horizon haze |
| `dusty_ochre` | dust_0..4 | streets, ground, adobe |
| `sunbleached_wood` | wood_0..3 | siding, boardwalks, timber |
| `red_rock` | rock_0..4 | canyon strata, brick, red paint grounds |
| `sage_scrub` | sage_0..2 | sagebrush, cactus, felt |
| `paint_trim` | paint_red, paint_teal | sparing painted trim (the accent) |
| `lamplight` | lamp_0, lamp_1 | flames, lamp pools, glow |
| `tin_iron` | iron_0, iron_1 | tin roofs, rails, stoves |
| `bone_white` | bone | sun key, paper, skulls |

| profile | light | fog / sky |
|---|---|---|
| `frontier_town` | High white sun, blue-violet shade steps, warm-white top step. | Pale-blue horizon haze (sky_3) that is the sky's lowest band. Fog 12–52 m outdoors. |
| `frontier_town_golden` | Low gold key from the west, violet shade. | Peach horizon (rock_4). Clouds tinted rock. |
| `frontier_town_night` | Cool moon key, indigo shade. Warm lamp pools baked into the vertex colour (`point_bake`, night only). Lit windows. | Night horizon (shade_1), stars. |
| `canyon_mesa` | Red-rock strata under a high sun. Red sand and path ramps. | Warm dust haze (dust_4). |

Look profiles in `view.json`:

- **Exteriors** (`street` / `canyon`): fog equals the background equals the sky's horizon band. Exposure 1.0, mild
  contrast.
- **`saloon` / `interior`**: neutral bone ambient, warm lamp key, cool window fill, shade_1 fog at 14–40 m.
- **`mine` / `passage`**: shade_0 fog at 9–30 m and a warm lantern key.

The lantern emitters (`wprop.lantern*`, the stove and the campfire) carry painted pools and bone-white glow halos.

**Gate thresholds.** The core defaults apply everywhere. The one documented deviation is the accent definition:
accent means a saturated teal (hue 165–200, saturation ≥ 0.4). Ochre and red rock are the base materials of a desert
town, so the core warm accent hues would count the whole street as accent. No threshold is loosened.

## 3. Kit families

There are 82 generators and 229 builds per variant (916 library builds). The complete, generated piece inventory
(default triangle count, class cap, named presets) is in `docs/westernkit/PIECE-INVENTORY.md`. Every build is:

- deterministic (seeded);
- painted by code;
- vertex-AO and vertex-light baked;
- GLB-validated: budget, palette, naming, origin / scale, topology;
- recolourable via palette roles;
- inside its class triangle budget.

The structural families are held to the cuboid gate: no more than 50% of triangles may sit in plain axis-aligned
boxes. So posts are hexagonal and tapered, boards chamfered, roofs pitched with eaves, and rock lofted and lumpy.

| family | generators |
|---|---|
| Town architecture (`wtown.`) | saloon, store, bank, sheriff, stable, hotel, church, water_tower, shack, facade (presets a–g), boardwalk, porch, balcony, hitching_post, stairs, doorway (`arch.door`), fence, room (interior shell), gallery |
| Rail (`wrail.`) | track (straight, curve R 6 m, bumper, crossing), platform, station, trestle, signal, car (boxcar, flatcar, caboose), locomotive, handcar |
| Mine (`wmine.`) | tunnel (straight, corner, tee, cross, end, end_door, with track), track (0.6 m gauge), portal, cart, headframe, ore_bin, ore_pile, ladder, shaft, timber_set, rubble, windlass |
| Props (`wprop.`) | barrel, crate, sacks, hay, cactus (saguaro, organ, prickly, barrel), wagon (covered, buckboard, broken), saloon_doors, table, chair, bar, piano, stove, wanted_board (blank posters), windmill, well, tombstone, lantern (hanging, wall, post, table), trough, signpost, wheel, bucket, bottles, skull, campfire |
| Nature / terrain (`wland.`) | canyon_wall (straight, corner, end, end_w), mesa, butte, arch, hoodoo, boulder, ledge, riverbed, ground, slope, scrub, yucca, dead_tree, grass, palm, oasis. Static dressing only: no tumbleweeds. |
| Sky (`wsky.`) | dome (inward hemisphere, horizon at v = 0.0875), mesas (distant ring, lit and fogged), sun (disc card) |

## 4. The FRONTIER GRID (interlocking)

The grid is the dungeon's 4 m cell with a 0.5 m room apron. A room plot is cells × 4 m + 1 m. A door on side cell i
has `door.position` = 4·i + 2, and its anchor sits 0.4 m in from the plot edge (room.gd). Anchors:

- **`lot_line`**: the origin sits on a cell-boundary line, mid-frontage. Buildings stand behind it (−Z).
  Boardwalks, porches and balconies stand in front of it (+Z, toward the street). Lot-line door sockets sit on the
  door anchor at a 2 m frontage step.
- **`cell_block_centre`**: the origin is the centre of a cell block (interior shells, ground and riverbed blocks).
- **`cell_centre`**: one cell's centre (track, tunnels, trestle).
- **`door_anchor`**: `wtown.doorway`, the frame room.gd places on every door.
- **`free`**: footprint-centred props.

Sockets: `door`, `frontage`, `frontage_fit` / `balcony_fit`, `walk`, `track`, `tunnel`, `lamp`, `gallery`,
`cliff_edge`, `prop`. They are listed per build key in `kits/library/westernkit-sockets.json`, together with the
connector rules.

## 5. Room compiler

`tools/westernkit_rooms.py compile_room(plan)` produces a spec room plus a presentation row. A plan places pieces by
`block`, `cell`, `lot` `[gx, gy, side]`, `at_m` (free props only), lamp sockets or doors. The compiler refuses a plan
when any of these fails:

- every door sits on a door socket of a placed piece, exactly at the room.gd anchor and facing out;
- every door socket carries a door: no dark doorway without a frame, no frame on an uncut wall;
- walk, track and tunnel sockets pair. A declared `open_ends` entry on the plot boundary is allowed: the line runs on
  out of the room;
- porch and balcony fits sit on a frontage of at least their span;
- lamp sockets get the wall lantern;
- grid pieces snap to the grid and turn only in 90° steps;
- the triangle estimate stays within 6,000. The estimate counts kit tris, door frames, the exterior sky dome and
  760 tris per person.

## 6. Runtime and shared files

- `runtime/godot/view/room.gd` is **not edited**. Kit rooms use the existing `kit_shell` path from the dungeon lane.
- No plugin tool is added and no schema changes (27-tool compact budget unchanged).
- The only shared-file edit is the one import line in `kits/core/pipeline.py`.
- Existing generators build byte-identical to main (140/140, `tools/westernkit_identity.py`).

## 7. Commands

```sh
cd <worktree>
export PYTHONDONTWRITEBYTECODE=1
python3 -B -m tools.westernkit_packs write && python3 -B -m tools.westernkit_style write
python3 -B -m tools.westernkit_library all            # build 4 variants (parallel), manifest, bindings, sockets, gates
python3 -B -m tools.westernkit_library verify         # every listed GLB == its sha256
python3 -B -m tools.westernkit_library determinism    # two independent builds, byte-compare
python3 -B -m tools.westernkit_demo write && python3 -B -m tools.westernkit_demo plan
python3 -B -m tools.westernkit_demo capture --round N --variant frontier_town --view a
python3 -B -m tools.westernkit_controls
python3 -B -m tools.westernkit_moods paint && python3 -B -m tools.westernkit_moods check
python3 -B -m unittest tests.test_westernkit
```
