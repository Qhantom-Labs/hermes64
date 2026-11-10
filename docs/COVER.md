# Staged covers (`hermes64_cover`)

Best three finals (original art, real renders):

- `docs/cover/thaw-box-2x.png` (also `-banner`, `-square`, `-card-alpha`, `-box-1x`)
- `docs/cover/moth_lantern_marsh-box-2x.png` (also `-banner`, `-square`, `-card-alpha`, `-box-1x`)
- `docs/cover/saltglass_bazaar-box-2x.png` (also `-banner`, `-square`, `-card-alpha`, `-box-1x`)

All seven finals at true card size: `docs/cover/sheet-finals.png`. Critique rounds: `docs/cover/CRITIQUE-1..7.md`.
These files are repository-only: the user package leaves `docs/cover/*` out ([PACKAGE-CONTENTS.md](PACKAGE-CONTENTS.md)).

## What it does

The cover is not a screenshot. Hermes stages a small diorama from your game's own kits, characters and style: a
landmark, up to three cast members, props, ground, sky and light. It renders the diorama through the real Godot runtime in
the N64 look and checks it against a cover gate. Then it finishes it as box art: a bold outlined title in an original
pixel face, a band in the style colour carrying the style name, and a small corner mark.

## Use it

1. **Propose.** "Make a cover for my game." Hermes writes three scene variants: **a** hero and landmark, **b** landmark
   shot, **c** portrait. It renders a preview of each and reports the gate verdict. You pick one; nothing is adopted
   for you.
2. **Edit in words.** "Move the lighthouse left", "make it dusk", "add the cat", "darker night sky", "title at the
   bottom", "closer". Each request becomes a typed edit (move, nudge, replace, add, remove, lighting, camera, title,
   particles, pose, finish, reframe), is validated, and is saved as a new revision of the scene file.
3. **Render.** This makes the final card, banner and square renders. If the gate rejects the render, it says why in plain
   words, for example "subject cut off by the frame edge", "no real darks", "blown-out whites", "low contrast at card
   size". Edit and render again.
4. **Export.** You get the box card at 245x170 (1x) and 490x340 (2x), a 1280x640 banner, a 1080x1080 square, a
   transparent-edged card, and title-free Studio art. Say "use this one" to adopt it: the Studio shelf picks it up from
   `.maker/studio/cover.png`.

Scenes live in `.maker/cover/scenes/<id>.json` (contract `contracts/cover/1.0.0.json`). You can hand-edit them;
everything is re-validated before a render.

## Rules it keeps

- **Deterministic.** The same scene and seed give the same bytes, from the render through every export.
- **Your game's own material only.** Kits come from the style's pack. Characters must be bound public cast. Colours
  are snapped to the style palette, and light energies stay inside the N64 look's ranges. Private references and the
  internal-only cameo are never used.
- **N64 look at a higher resolution.** Renders are 980x680 (four times the card), 1280x640 and 1080x1080. They use
  texel-painted textures with bilinear filtering, vertex lighting, fog matched to the horizon, MSAA, and a VI-style
  [1 2 1] tent resolve. Nothing is sharpened. The card is a clean 4x box downsample.
- **Local and confined.** Windowed Godot through the sandboxed runner, argv only, writes only inside the project, no
  network. Finishing is stdlib Python and does not need Pillow.

Details: `docs/COVER-INTEGRATION.md` (registration, Studio pickup) and `docs/COVER-RESULT.md` (commands and real
outputs).
