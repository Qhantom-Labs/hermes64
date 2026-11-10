# ROOMLOOK round 3 critique: interiors with the real cast

All frames are real Godot 4.6.2 captures at 320×240. The real imported characters are staged through the character
lane's additive adapter (`tools/roomlook.py capture --actors`, read-only use of `characters.integration`).

- Rounds: r3-0 (baseline) … r3-20, then r3-final (ordinary facade, goldens) and r3-final-actors (real cast).
- Sheets: `evidence/roomlook/round-r3-*/sheet-*.png`. Sheets beside the private study references stay in a private
  folder outside the repository.

The gate measures defects; it is not art approval. Below is what the frames look like, written as harshly as the
gate numbers are kind.

## Baseline (r3-0, real cast, previous room look)

- **Value structure:** inverted. Bright pearl ceilings and upper walls sat above a floor of the same value, so the
  top third of every frame was a flat lilac slab: 63–80% of top-band pixels were flat in the flatness map.
- **Chrome:** read as pale blue-white plastic. The env map's bright upper half dominated and there was no dark
  reflected horizon.
- **Figures:** white hoods sat against white walls. In the dome shelter the player and Luma stacked into one
  silhouette, and a huge column filled the right third of the frame next to the lens.
- **Warm accents:** only 2/6 rooms showed a warm light. Additive orange halos over the cool room went magenta.
- **Budget:** pod bay 8,103 and workstation 6,216 triangles against the 6,000 cap.

## What changed (all pack data or theme-agnostic runtime; actor meshes untouched)

- **Room value structure** (`look.profiles.interior.room`, shader `n64_room`):
  - light falls off toward the ceiling;
  - wall bases sit in a contact-shadow band;
  - the floor centre carries a slight lift.
- **Per-pixel point lights on static surfaces** (`pixel_lights`): lamp pools are round instead of Gouraud wedges
  across 10 m floor triangles, and the floor's gloss comes from per-pixel specular glints.
  - The env-map floor gloss was dropped. Magnified on floors it drew stair-stepped white wedges, which an A/B
    capture proved; softer thresholds and an env blur did not remove them.
- **Ringed floor caps:**
  - Rings are packed toward the walls (`ring_bias`), so the baked AO band is narrow.
  - The cap is closed by a centre star (`cap_center`) instead of a long-triangle n-gon fan.
- **Textures:**
  - Wider value ramps on wall and ceiling, so texel detail survives in the dark.
  - Per-texel `grain`.
  - The luminous ceiling panels got a diffuser grid (`glow` `cells`), so they read as fixtures instead of clipped
    white.
- **Chrome** (`look.profiles.*.chrome`, `env_chrome`): split env (bright floor reflection below, dark navy above),
  a dark horizon band with a thin white catch line, env gamma 1.7, white-hot spots and a rim catch.
- **Actor rim and kicker** (`look.profiles.*.actors`, shader `n64_actor`/`n64_kicker`): a cool kicker from behind and
  above the subject relative to the fixed camera, plus a stronger rim, applied to `dynamic_light` surfaces only.
- **Warm halos** (`halo_mode: mix`, `n64_halo.gdshader`): mixed, not added, so amber stays amber. They are pulled
  toward the camera so emitters do not swallow them.
- **People framing** (`look.camera.people`, `room.gd frame_people`): after dressing, each inside camera orbits the
  room ring (±36°, optional +0.3 m lift and ±6° fov) and picks the least-bad view. Costs:
  - a figure looming at the lens;
  - figures stacked behind one another, with humans weighted over cats;
  - a tall piece covering the frame near the lens;
  - off-frame people.
  - The chosen score and every candidate are recorded in the capture audit.
- **Budget, scenery only:**
  - a 56-triangle support plinth replaces the 180-triangle side table;
  - an 8-segment hatch replaces the 14-segment one;
  - the pod bay drops its redundant chaise/bed/pillow dressing and has 14 wall segments and one window;
  - interiors no longer build a hidden sky dome;
  - actors are untouched.
- **Snow field:**
  - a footprint trail from the protagonist's mark into the picture, toward the deepest door building;
  - wind drift lines laid across the camera view;
  - cloud bands under the aurora;
  - softer framing conifers and rock.
- **Last Light (cheap only):** a rug under the protagonist's mark and a prop near her in each interior. The lamp-room
  column was moved off her head line and the cottage bench out of the camera line.

## Final frames (r3-final-actors), harsh

- **Pod bay:** the best room now.
  - Good: dark coffered ceiling, a lit floor pool, a warm amber lamp with a real glow, and figures that separate
    from the walls.
  - Still wrong:
    - The floor under the lamp blows out to near-white, a specular glare much wider than the lamp could throw.
    - Dropping the chaise and bed for the budget left the room sparse and slightly showroom-like.
    - The blue support plinths read as generic cylinders.
    - The chrome sofa at the right is cut by the frame edge.
- **Workstation:**
  - Good: the triple-CRT desk reads; screens glow cyan against a dark ceiling; chrome rims catch light.
  - Still wrong:
    - The foreground player is still oversized: the lifted camera helps but does not fix it.
    - Neri is still partly tangled with the desk silhouette.
    - The cyan screen pool competes with the warm lamp for attention.
- **Dome shelter:**
  - Good: the column no longer crowds the lens. It now stands in the back as a landmark with the warm pipe glow on
    it.
  - Still wrong:
    - Luma still overlaps the player's shoulder: framing reduced the stacking but did not remove it.
    - The warm accent behind the column is a dim orange smear, not a lamp.
    - Flatness is the highest of the interiors (0.33). The dome ceiling is a dark uniform field.
- **Conversation pit:**
  - Good: the sunken lounge, panoramic window and organic column compose well, and the value structure works.
  - Still wrong:
    - Sol is still small and far back.
    - The white cat still merges with silver furniture.
    - The ceiling light panel is a flat rectangle.
- **Curved corridor:**
  - Good: it reads as a corridor, with a warm lamp at the bend and chrome portholes.
  - Still wrong:
    - The dark railing counter is a black slab with no form.
    - The figures are small in a long, empty floor.
- **Snow field:**
  - Good: the footprints and drift lines now lead the eye from the protagonist toward the dome; the sky has cloud
    bands under the aurora.
  - Still wrong:
    - The marks are subtle at 320×240.
    - The right-hand conifer is still a dark mass even with softer shading.
    - The figure is a small dark astronaut against pale snow: readable, not characterful.
- **Last Light:**
  - Better: the rugs ground the protagonist, and nothing pierces her head in the lamp room any more.
  - Still wrong:
    - The interiors are still legacy cutaways. They fail the gate (void 15–18% with the closer cameras, washed-out
      contrast) exactly as before; this is the secondary demo and was not reworked here.
    - The same blue checker rug in all three rooms is lazy.
    - No second figure was added. Staging another story character is the character lane's presentation data, and
      inventing cast is out of scope.

## Not done / honest limits

- Human art approval of any of this. The goldens are blessed, not approved.
- The pod bay floor glare and the dome-ceiling flatness: both pass the gate but read as unfinished.
- The actor triangle budget assumes the current cast (max body 692, props ≤ 152). New models from lane-characters
  must keep to their separate budgets for the room totals to stay under 6,000.
