# Characters

New characters in the house style, with little tinkering: a character is a **recipe**, the project's **style lock**
decides its colours, and **gates** reject anything off-style before you see it.

## Make one

```text
hermes64_character action=propose project=<p> brief="A city courier in a teal jacket with a ponytail and a datapad"
```

1. **propose:** a one-sentence brief, plus optional reference images. It returns three variants, a/b/c, each with a
   contact sheet. The sheet shows front, three-quarter and side over snow and dark, plus a room shot at game scale.
   You pick a variant. Nothing is adopted automatically.
2. **edit (optional):** typed edits only:

   | Edit | Fields |
   |---|---|
   | `height` | `value` |
   | `build` | `head`, `shoulders`, `waist`, `legs`, `age` |
   | `hair` | `style`, `color` |
   | `color` | `slot`, `role` |
   | `swap` | `part` |
   | `face` | `preset`, `expression`, `eyes`, `beard` |
   | `prop` | `part` (omit `part` to remove the prop) |
   | `name` | `display` |

   `render=true` redraws the sheet.
3. **build:** writes the GLB, its clips, `characters/manifest.json` and a row in `catalog.json`. All of this happens
   only if every gate passes.
4. **bind:** `id=<built> display_name=...` adds the character to `characters/cast.json`.
   - The optional cameo binds from its hub install: `/hermes64 hub install character.cameo.cameo_visor_01 <game>`,
     then `glb=assets/hub/character.cameo.cameo_visor_01/models/cameo_visor_01.glb source=cameo_pack` (MERGE4).
   - A community file binds with `glb=... source=community`.
   - Both pass the same rig kit validator.
   - A refused file gets one plain line (`reason`) plus the validator errors.

### A bound character in the game (CHARBIND)

The cast row is used when the runtime is staged (`adventure_maker/cast_binding.py`). A game id takes the cast row
that `metadata.presentation.cast` names, else the cast row with its own id. A game id is a story character, a combat
archetype (robot or boss) or a scene card actor.

- Premise fields fill `presentation.cast`: `hero.binding`, `npcs[].binding`, `bosses[].binding` and
  `robots[].binding`, when the value is not a bundled public character. `bind` reports the ids that use the row
  (`used_by`).
- **Player:** the bound file, plus any missing fight clips. These come from the file's rig clip pack, else from a
  rig with the same bones (human16_v3 for human16_v1). Each clip is kept only if the rig kit accepts it on this body.
  `swing` may come from the file's own `interact`. A fight clip still missing is the runtime's labelled POSE TEST
  hold, and the HUD shows POSE TEST.
- **Room actor or captive:** plays its authored clip (`npcs[].clip`, for example `captive`), else idle.
- **Scene actor:** a story character, a boss/robot id, or a `presentation.cast` id. A clip the file lacks shows
  idle and is listed as a warning.
- **Boss or robot body:** telegraph, attack and recover come from the file. If it lacks them, they are made from
  its swing keys (or its `interact` keys) and checked by the rig kit. hurt, death and idle_combat come from a clip
  pack the rig kit accepts on the body, else that state shows the held POSE TEST pose. A body that cannot show
  telegraph, attack and recover keeps the stock robot art.
- Every decision and warning is written to `runtime/cast-binding.json`.
- With no cast row and no mapping, staging is byte-identical to before.

Declared clip forms accepted by the validator, within fixed limits:

- **Run flight:** the base_v1 locomotion block's `run.flight_keys` may leave the floor by at most 0.15 x height.
- **Seated clips:** declared with `rigkit.declare.declare_seat`. They hold one horizontal placement within 0.5 m of
  rest and never go below the floor.

Lossless conversion: `rigkit.conform.rigid_pieces_to_props` turns floating pieces weighted to one joint into props
on that joint. `keep_clips` and `drop_props` are explicit, lossy steps.

Cast preset revisions (CEOFIX): `cast.recipe(name, revision=2)` builds a later revision. Revisions are listed in the
`revisions` block of `adventure_maker/nbchars/cast_presets.json`, and `cast.revisions(name)` returns them. Revision 1
is the preset as listed, and its files keep their bytes. Revision 2 of the three CEOs uses bind dials of the cast_v1
generator (`coat_top`, `coat_seam`, `guard_clear`) and the `faceted` prop form, so the files pass the bind gates.
`docs/CEOFIX-RESULT.md` has the measured change.

Look-ups: `action=list what=parts|bodies|styles|recipes|cast` and `action=info id=...`.

## Recipe

Contract: `contracts/character/1.0.0.json`. A recipe holds:

- `rig` (`id` and `version`)
- `body`
- `build`
- palette **roles**, never hex values
- `outfit` part ids, `face`, `prop` and `seed`

Bodies, each registered on a rig from the rig kit:

| Body | Rig | Notes |
|---|---|---|
| `person` (face head) | `human16_v1` | |
| `person_masked` | `human16_v1` | |
| `robot_walker`, `robot_brute` | `human16_v1` | |
| `robot_floater` | `human16_v1` | Legs weightless; hovers through `hover_m`. |
| `animal_cat`, `animal_dog` | `quad16_v1` | |

Parts (`characters/library/parts.json`, 120 entries, `action=list what=parts`):

- **People:** tops, sleeves, legs, boots, hands, collars, hats/hoods, hair, beards, faces, patterns, accessories, props.
- **Masked bodies:** a cape.
- **Robots:** heads, hands, feet, visors and accessories, plus the boss crown and emblem.
- **Animals:** coats.

## Style lock

The style lock lives at `profiles/character-styles/<id>.json` (contract `contracts/character/style-1.0.0.json`). It
maps every role to a colour of the lock, sets the proportion ranges and lists the parts it denies. There are two
kinds:

- **profile:** the palette is derived from a style profile's 8 anchors. Switching profile recolours every character
  without touching a recipe.
- **legacy_pack:** the palette the shipped cast uses today (`pack_polar_pod`, `pack_forest_village`).

Values outside the lock's range are clamped, and a one-line reason is reported. Impossible values are refused with a
code: `RANGE`, `UNKNOWN_PART`, `PART_BODY`, `ROLE`, `SLOT`, `BUDGET`, `RIG`, `LOCK`, `CLIPS`.

## Gates (every built or bound character)

| Gate | What it checks |
|---|---|
| Rig kit | `validate_character` from lane NBCHARS: bones, inverse binds, weights, budgets, 3 mm joins on every key of every clip, no NaN. |
| Palette | Every texel and vertex colour is in the lock. |
| No cuboids | No part is a box. |
| Hair | The face never pokes through the hair. |
| Silhouette | Readable on snow and dark, calibrated on the approved cast. |
| Determinism | Two builds produce identical bytes. |
| GLB audit | Structural audit of the file. |

## Names

- People keep `placeholder: true` until Dylan names them.
- The masked lead (`new_arrival`) shows as **Qhantom**; ids never change.
- The plugin's own cast takes its display names from `catalog/names.json`, the one editable names file (owned by the
  hub lane).
- Project characters are named at bind.

## Limits

- **New bodies build without Blender (MERGE4).** `propose`, `edit render=true` and `build` export through
  `character_exporter` (`auto` by default): the python exporter (`python -m adventure_maker.nbchars export --job`,
  numpy in `python_path`, parity PASS) builds every item kind. Robots use `adventure_maker/character_robot.py`, a
  port of `ext/robot_blender.py`; 4 robot recipes (walker, brute, floater, crowned boss) are equivalent within
  tolerance to their Blender builds (skinned error <= 7.5e-7 m, textures byte-identical; `tools/merge4_robot_parity.py`).
- **Review renders are still Blender's.** With Blender configured, it renders its own build of the same items for
  the contact sheets and the silhouette gate (the shipped GLB is the python one). Without Blender there are no
  sheets and the silhouette gate is reported under `not_run`, never as passed; every other gate runs.
  `character_exporter=blender` keeps the original Blender build.
- **Budgets:**

  | Kind | Limit |
  |---|---|
  | Human | < 700 tris |
  | Robot or creature | < 500 tris |
  | Prop | ≤ 200 tris |

- Head size is capped per age and clip set, so necks stay closed in rolls.
- A child cannot carry the combat staff.
- Clips are fixed per body: STEP at 15 fps, 16 keys, no root motion.
- References are measured for colour blocks only. Faces stay painted in the house style; no face is traced.
- The cameo is a bound asset from its optional pack, never generated. It follows `cameo/LICENSE-CAMEO.md` and is
  removable in one step.
