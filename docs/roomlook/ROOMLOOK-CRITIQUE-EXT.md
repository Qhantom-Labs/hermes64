# ROOMLOOK exterior critique (outdoor rounds ext0–ext17)

Exteriors were the priority after STEER 1. Every outdoor round was put beside private study references
(screenshots of N64-era outdoor scenes). Those sheets stay in a private folder outside the repository;
no reference pixels, layouts or names are in this repository. We studied how such scenes are built, not what
they contain: every layout, prop and texture here is original and generated from pack data.

## Round ext0 (baseline, both games) — "a diorama on a plate"
- Snow Field: a flat dune slab in a void ring (19% void), two free-standing doors, no sky in frame worth the
  name, one depth band (everything 10–32 m), no landmark. Gate: FAIL (depth layering 1/3, no landmark, no darks,
  flat frame 54%, uncut doors).
- Fog Street: a brown fog box. Contrast 0.15, 44% of pixels drowned in fog, no sky (0%), free-standing doors.
- Both read as test scenes. Nothing pulls the eye; there is no foreground, no distance, no horizon.

## What the references taught (verified by looking, not copied)
Layered depth with a dark chunky foreground, a mid-ground path, a hazy distance; fog matches the horizon colour;
terrain is terraces and enclosing ridges, not a noise plane; ground is big soft painted patches; cliffs have
vertical streaks; a landmark sits on the skyline; skies are bright gradients; every screen has near/mid/far.

## What changed (all pack data; the runtime stays theme-agnostic)
- **Terrain** (`terrain.yard`, kit 3.2): playfield = room grid; terraced ledges and a bowl-shaped enclosing
  ridge with jagged crests; passes cut where the story's doors are; light path strips from each exit to the
  centre; optional ice/water slabs. A **view gap** lowers the ridge where the fixed camera looks so the distance
  shows. Planned per room by `adventure_maker/yards.py`; built and validated through the kit pipeline; safer
  candidates on rejection, legacy floor only if all fail.
- **Distance** (`terrain.vista`): two silhouette rings standing on the terrace plane, painted with a vertical
  haze gradient and fogged toward the horizon colour (`look.materials.vista*`).
- **Sky**: gradient dome with the ramp mapped onto the part of the dome a fixed camera sees (`sky_range` /
  `sky_gamma`), clean bands (no checker dither), aurora/haze/cloud layers per pack.
- **Fog-tinted-to-horizon rule**: exterior profile fog colour = horizon colour; the gate measures it.
- **Composition** (`look.exterior`): low camera on the first ledge looking across the field; landmark on the
  skyline inside the view gap (crystal tree / lighthouse tower); dark framing objects near the lens (rock,
  conifer); rock clusters; rhythmic posts along the paths; vegetation on the ledges; particle field (snow /
  sea motes); door buildings at the exits.
- **Ground**: `blotch` painted ground with wind ripples (`field` role); cliffs use `streaks`.
- **Window views** (interiors) now show the same world as the exterior: dark blue sky with aurora, ridges,
  the crystal tree and lit domes.

## Snow Field now (ext17) — closer to a finished N64 screen
Dark rock and conifer frame the bottom corners; the yard reads as a snow bowl with terraces and a ridge; pale
hazy peaks sit in the gap; the crystal tree stands on the skyline; deep-blue sky fades to a pale horizon; snow
falls. Depth bands near/mid/far luma ≈ 0.31 / 0.52 / 0.73 (gap 0.20); far band 0.08 from the horizon colour.
Gate: PASS.

**Still weak (harsh):**
- The playfield is still a big pale plane: the painted ripples are subtle; no snow drifts, footprints or
  stepping stones lead the eye. The references always lead the eye with a path or rhythm; ours barely does.
- Terrace walls read as horizontal bands, not rock: the 0.8 m risers show only a sliver of the streak texture.
- The crystal tree reads as a crystal tree now (it read as a candelabra in ext10 and was redesigned), but it is
  thin; a real landmark would be bigger, chunkier and lit.
- The camera is a rule, not a composition: one low diagonal view per room. Good default, not art direction.

## Fog Street now (ext17) — secondary demo, intentional but plain
Lighthouse tower on a bright dusk horizon, dark cliffs with grassy ledges, the boathouse and pier in the
mid-ground, a dark framing rock. Depth bands near/mid/far ≈ 0.17 / 0.31 / 0.82. Gate: PASS (with a pack-specific
accent definition: in this warm-earth pack the browns and cream are base colours, so only saturated lamp/straw
golds count as accents; documented in `packs/n64_v0/view.json`).
**Still weak:** the cliffs are a dark brown wall; the sea is barely present; the horizon is nearly white; the
pack borrows the forest kit palette, so a truly coastal look needs its own kit pack. Last Light interiors remain
legacy cutaways (secondary demo; not reworked in this lane).

## Gate numbers
See `docs/ROOMLOOK-RESULT.md` for the before/after table and the exact thresholds.
