---
name: hermes64-cover
description: Stage, render, gate and finish original box-art covers.
version: 0.1.0
author: Qhantom Labs, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [games, covers, box-art, n64, offline]
    related_skills: [hermes64]
---

# Hermes64 staged covers

`hermes64_cover` builds a small staged diorama from a game's own kits, cast and style. It renders the diorama through
the real Godot runtime in the N64 look, gates the result, and finishes it as box art: an original pixel logotype, a
style band and a corner mark. Local only: windowed Godot through the sandboxed runner, writes confined to the
project, no network, stdlib finishing.

## When to use
- A game needs a cover for the Studio shelf, a README banner or a social square.
- The user wants to change a cover in words: "move the lighthouse left", "make it dusk", "add the cat",
  "darker night sky", "title at the bottom".
- Do not use it to copy console box trade dress, logos or fonts; to put private references or internal-only cast in a
  cover; or to adopt a cover the user has not chosen.

## Prerequisites
The tool is registered with the plugin (merged at MERGE3; `docs/COVER-INTEGRATION.md` lists the registration lines).
The advertised schema is compact: each edit shows only its `op`, and the full shapes are the ones in this skill. You
need a scaffolded project under the configured `projects_root` and a Godot 4.6 executable (`godot_path`, the macOS
app path, or PATH).

## Procedure
1. `hermes64_cover(action="propose", project="game")`. Optionally pass `seed`, and `style_profile` (one of
   `n64_base`, `polar_pod_example`, `warm_desert_example`) to stage the game in a different look. This writes THREE
   scene files (`<id>-a` hero + landmark, `-b` landmark shot, `-c` portrait) and renders their previews. Each gets a
   gate verdict with readable reasons. Show the user the `preview_box_1x`/`preview_box_2x` paths and the verdicts,
   then let them pick. Never adopt on their behalf.
2. Edit in words through typed edits, for example `action="edit", scene="game-b", new_id="game-b-dusk",
   edits=[{"op":"lighting","mood":"dusk"}, {"op":"nudge","target":"hero:0","direction":"left","metres":3}]`.
   Targets are `hero:<i>`, `prop:<i>` or `cast:<id>`. Cast ids come only from the project's bound public characters.
   Add `preview=true` to render the edited scene. Every edit writes a new validated revision; nothing is overwritten.
3. `action="render", scene="<chosen>"` makes the final card (980x680), banner (1280x640) and square (1080x1080) renders
   and runs the cover gate. Rejected renders come back with reasons (blown whites, no dark anchor, subject cut off,
   flat frame, off-palette, low contrast at card size, depth separation). Fix them with an edit and render again.
4. `action="export", scene="<chosen>"` finishes the box art: 245x170 at 1x and 2x, the 1280x640 banner, the
   1080x1080 square, a transparent-edged card, and title-free Studio art (440x308). Pass `adopt=true` only when the
   user has chosen this cover. Adopting writes `.maker/studio/cover.png` (the Studio shelf reads it),
   `.maker/cover/current.json`, and, in a portable project with `project.json`, the optional `cover` field.
5. `action="list"` shows the scenes, renders, exports and the adopted cover.

## Edit shapes
Each edit is `{"op": ..., fields}`; a field that does not belong to the op is refused (`Unknown field(s)`).
Targets are `hero:<i>`, `prop:<i>` or `cast:<id>`; vectors are `[x, y, z]` metres; colours are `#rrggbb`.
- `move`: `target`, exactly one of `by` (within +-30) or `to`, optional `yaw` (-360..360).
- `nudge`: `target`, `direction` (`left`, `right`, `forward`, `back`, `up`, `down`, as seen from the camera), `metres` (0.05-30).
- `replace`: `target` `cast:<id>` with `id` (a bound public character), or `hero:<i>`/`prop:<i>` with `kit`.
- `add`: `kind` (`hero`, `prop`, `cast`); hero/prop need `kit` and `at`; cast needs `id`; optional `yaw`, `scale`, `clip`, `frame`.
- `remove`: `target`.
- `lighting`: `mood` (`night`, `dusk`, `day`, `dawn`, `interior`) and/or `key_energy`, `ambient_energy`, `fill_energy` (0-1),
  `key_azimuth_deg`, `key_elevation_deg` (5-85), `fog_near_m`, `fog_far_m`, `fog_density`, `glow_strength`, `stars` (0-400),
  `aurora_strength`, `clouds`, `exposure` (0.3-1.0).
- `camera`: `focal_mm` (18-85), `distance_m` (2-45), `azimuth_deg`, `elevation_deg` (-12..65), `roll_deg` (-8..8),
  `framing` (`poster`, `banner`, `square`), `target` (a point).
- `reframe`: `top` (0-0.9), `bottom` (0.1-1, more than `top` + 0.1), `subjects` (`all`, `cast`, `hero`).
- `title`: `text`, `subtitle`, `placement` (`top`, `bottom`), `letter` (`block`, `wedge`, `tall`), `size` (`m`, `l`, `xl`),
  `fill`, `fill2`, `outline`, `shadow`.
- `particles`: `kind` (`none`, `snow`, `fireflies`, `dust`, `embers`, `petals`), `count` (0-400), `color`, `size_m` (0.02-0.25).
- `pose`: `target` (`cast:<id>` only), `clip`, `frame` (0-47), `yaw`.
- `finish`: `vignette` (0-0.35), `contrast` (0.9-1.25), `saturation` (0.85-1.3), `lift` (0-0.12),
  `band_edge` (`bottom`, `left`, `right`, `top`, `none`), `mark` (true/false).

## Pitfalls
- Same scene and seed give the same bytes, from the render through every export. Change the seed, or edit the scene,
  to get a different picture.
- The gate judges the raw render, not the finished art, so a title cannot hide a bad render.
- Covers stage at most three cast members, and only bound public characters of the game. The optional cameo
  (public-with-notice, bound only through its hub install) is not admitted on covers, and private reference images
  never are.
- A long title wraps to two lines and never drops below the legibility floor (letters 18 px tall on the 1x card).

## Verification
`python3 -B -m unittest discover -s tests_cover` (stdlib; the determinism test renders twice when Godot is present).
`tools/cover_demo.py` reproduces the demo rounds. Human taste approval is not automated.
