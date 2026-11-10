# ROOMLOOK critique 2 — enclosed shells, inside cameras, nothing hovers

Sheet: `evidence/roomlook/round-2/sheet-thaw.png`. Gate: `evidence/roomlook/round-2/thaw/style-gate.txt`.

## What changed (data-driven, default for every game on a pack with `shells` data)
- `hermes64_build_assets` now builds one enclosed `arch.room_shell` per interior room through the kit pipeline + validators (`adventure_maker/shells.py` plans plan/ceiling/coves/openings from `packs/<pack>/view.json "shells"`; doors are cut where the story's doors are, windows sized to the pack's own window modules; safer candidates on rejection; legacy cutaway only if every candidate fails, reported in `room_shells`).
- Kit `arch.room_shell` gained `floor_rings` (ring-tessellated floor/ceiling for per-vertex light) and `ceiling_panel` (luminous ceiling panel / dome oculus). Defaults unchanged, so existing library builds are byte-identical.
- Runtime: shell placement, door/window modules dropped into the cut openings (walk targets just inside), pack backdrop around every room, pack camera policy (`look.camera`: authored outside cameras are pulled inside on the same side; elongated rooms framed along the long axis), pack support policy (`look.supports`: props authored in mid-air rest on furniture, stand on the floor, or get a side table). Gloss on big surfaces is per-fragment (no more 10 m reflection wedges).
- Fixed two runtime errors introduced in round 1 (editor-only global listing; global transforms read before the room entered the tree). `open` stderr is clean again (1 pre-existing ObjectDB warning).

## Does it look like a finished hand-made N64-era game? Closer; not yet.
The frame is now a place: walls, ceiling and floor fill 100% of the image (void 0.000 in all five interiors), the camera stands in the room at eye-ish height, doors are hatches in walls, the panoramic window shows a starry snow village. Chrome pedestals and rims glint. This is the first round where a screenshot could pass for a game screen at a glance.

## Where it still reads as a test scene
- **Big flat planes**: 45–55% near-uniform neighbourhoods. Walls are one gradient with no moulded panels, ribs or trim; floors are plain lilac; the ceiling panel is a blown-out white slab (pit, workstation).
- **Empty floor area**: furniture islands in 100 m² halls. References are packed edge to edge (cushions, throws, lamps, cables, plants).
- **No warm accent anywhere** (accent fraction 0.000 in every room): lamps do not read as warm light sources.
- **Darks**: corridor/pod bay p2 0.15–0.18; nothing near black except glass.
- **Portholes** read as mirrored discs (good per the brief) but show no outside view.
- **Snow Field** (exterior) unchanged: flat dune slab, 19% void, free-standing doors. Now the top priority (STEER 1).

## Gate
All rooms still FAIL on flatness and accents; interiors now pass void, floating, uncut doors, camera placement, fog swallowing and palette.
