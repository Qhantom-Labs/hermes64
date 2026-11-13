# Designing pieces that look right after conform (house N64 style)

The conformer keeps your shapes and replaces colour, light and texture with the pack's. So the LOOK comes from
your silhouette, proportions and colour regions. Design for a 427x240 screen seen from 4-8 m away.

## Rules

1. **Silhouette first.** Ask: is it recognisable as a black shape from the front and the side? Exaggerate the one
   feature that names it (the clock's tall case + round face, the torii's curved top beam, the periscope's elbow).
2. **3 to 5 chunky parts**, then details. Main mass 60-80% of the triangles; details are a few simple shapes.
3. **Flat colour regions:** one main role, one secondary, 1-2 small accents (`trim`, `chrome`, `light`). Detail
   comes from colour blocks and shape breaks, never from many tiny parts or noise.
4. **Pick roles by meaning, not by colour:** wood things `wood`/`bark`, masonry `stone`/`wall`, machines
   `metal`/`hull`/`body_alt`, cloth `fabric`, glow `light`/`screen` (small: glowing areas are counted), living things
   `body`/`fur`/`foliage`. The pack turns them into its own palette, so the piece fits any setting.
5. **Proportions:** chunky. Heads, handles, knobs, eyes and feet ~1.3x real size; legs and posts thick (at least
   6 cm for a prop, 12 cm for furniture, 20 cm for structures). Nothing thinner than a finger at game distance.
6. **Triangle budget per part:** prop 150, furniture 300, structure 500 in total. Typical: box 12, chamfer_box 44,
   cylinder sides=8 ~32, sphere 8x6 ~80, lathe 8 segs ~16 per profile step, sweep sides=5 ~10 per path point. Over
   budget is decimated automatically, but you choose better where triangles go than the decimator.
7. **Mirror and repeat:** model one side and `mirror(p, 'x')`; rings with `polar`, rows with `array`/`along`.
8. **Stand on the ground:** the lowest point at z = 0, a base or feet wide enough to stand; parts must touch
   (no floating parts: the room gate checks it).
9. **Front faces -Y.** The game camera mostly sees the front and the three-quarter view.

## What the gates catch and the fix

| Gate line | Fix |
|---|---|
| `budget: N triangles > M` | conform decimates; better: fewer sides/segs on small parts |
| `texture energy X > 0.050` | conform softens it; fewer different roles on small faces, larger colour regions |
| `largest side X outside [lo, hi]` | the class follows your size automatically for scripts; scale the piece to real size |
| `floating pieces` (room) | lower the part to touch the one below; add a base |
| not closed / open edges | use closed shapes (box, lathe with r=0 ends, capped tubes); flat sails/flags as `card` |
| `non-manifold edges` / `inconsistently wound` | two parts share exact corners (halves meeting face to face): overlap them 1-2 cm |
| a card vanishes from behind | cards are one-sided (back faces are culled): use a thin `beam`/`box` to see both sides |
| `unknown role` | use a role from the list in builder-api.md |

## Checklist before you submit

- [ ] Front and side silhouettes say what it is (sketch the 3-5 parts and their sizes first).
- [ ] Real-world size in metres; lowest point at z = 0; parts touch.
- [ ] 1 main + 1 secondary role, at most 2 accents; glowing roles small.
- [ ] No part thinner than the minimum above; nothing tiny that will vanish at 6 m.
- [ ] Within the budget the needs_design record gives (piece and room).
- [ ] After make: open the preview sheet, compare with your intent, revise (same id) up to 3-5 times.
