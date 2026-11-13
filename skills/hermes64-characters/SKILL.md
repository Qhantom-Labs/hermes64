---
name: hermes64-characters
description: Make house-style characters with hermes64_character.
version: 0.1.0
author: Qhantom Labs, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [characters, games, n64, rig, recipes]
    related_skills: [hermes64]
---
# Hermes64 characters

Characters are recipes: body + rig, build, palette ROLES, parts, face, prop. The project's style lock turns roles
into colours, so a style change recolours every character with no recipe edits. Every built or bound character
passes the gates (rig kit `validate_character`, palette, no cuboids, hair, silhouette, determinism, GLB audit).

## Flow

1. `hermes64_character action=propose project=<p> brief="<one sentence>"` (optional `references` = project PNG/JPEG
   paths, `style` = lock id). Returns three variants, each with a contact sheet (front / three-quarter / side over
   snow and dark, plus a game-scale room shot). Show the sheets; **the user picks**. Never build unprompted.
2. Optional: `action=edit recipe=<proposal>.<a|b|c> edits=[...]` with typed edits only:
   `height{value}`, `build{head,shoulders,waist,legs,age}`, `hair{style,color}`, `color{slot,role}`,
   `swap{part}`, `face{preset,expression,eyes,beard}`, `prop{part}` (omit part to remove), `name{display}`.
   `render=true` returns a fresh sheet. Out-of-style values are clamped with a one-line reason; impossible ones
   are refused with a code (RANGE, UNKNOWN_PART, ROLE, SLOT, BUDGET, RIG, LOCK).
3. `action=build recipe=<id or proposal.variant>`: GLB + clips + `characters/manifest.json` + a `catalog.json` row
   (hub asset shape), only if every gate passes.
4. `action=bind id=<built id> display_name="..."` adds it to `characters/cast.json`. Files bind with
   `glb=<project path> source=cameo_pack|community` and pass the same rig kit validator:
   - cameo: only from its hub install, unchanged: `/hermes64 hub install character.cameo.cameo_visor_01 <game>`,
     then `glb=assets/hub/character.cameo.cameo_visor_01/models/cameo_visor_01.glb` (same sha256, its
     `LICENSE-CAMEO.md` next to it); visibility public-with-notice. Show the user the notice first.
   - community: a loose file stays `internal` (licence unknown); a hub-installed file keeps its hub row.
   - The game uses a cast row for the game id that `metadata.presentation.cast` maps to it, or for the same id.
     Ids can be the player, NPCs or captive, scene actors, and bosses or robots; premise `binding` fields fill the
     mapping. Read `used_by`, then rebuild the runtime. Refusals come as one `reason` line; pass it to the user
     as is. Role details and warnings: `runtime/cast-binding.json` and docs/CHARACTERS.md.
5. Owner waiver (docs/WAIVER.md). Only the owner may accept a file the rig kit refuses for `mesh.deformation`,
   `mesh.silhouette.floor` or `budget.body` (at most 800 triangles). After the owner has seen it and told you so,
   bind with `waive=true owner_approved=<their name, as they gave it> brief="<their words>"`, once the game names
   the character (so the player's fight clips are measured too). Never fill these in yourself. The result lists
   every waived failure as WAIVED with its numbers: show them to the user. Hub pack/publish refuse a waived
   character unless the user asks for `waived=true`.

## Creatures no body fits

Bodies: people and robots (rig human16_v1; with `style=creator64` also elf, dwarf, goblin, cat, fox, bear and rabbit
people), cat and dog (quad16_v1), two enemy creatures (dasher16_v1,
warden15_v1). A brief for anything else (dragon, snake, spider, horse, bird, blob, jellyfish, tentacle monster)
makes `propose` return `needs_design` instead of a person: there is no rig for it. Options: (a) design it as a
static prop with a builder script (`make ... render=true`, skill hermes64-generators); the runtime does not
animate props, so it stands still; (b) a person/robot/cat/dog body if the user accepts that. Never present a
human body as the creature. A generic creature skeleton with procedural clips is designed, not built yet.

## Character creator (`style=creator64`)

For "make me a character: <words>" use the creator: original characters in one measured card style (body under 700
triangles, one 64x64 baked-light texture, one material, the human rig and all 13 clips). It reads plain words:
species (human, elf, dwarf, goblin, robot, cat, fox, bear, rabbit), build (stocky, lean, tall, child, bulky), role
(wizard, knight, merchant, barista, chef, ranger, queen ...), hair, beard, hat, cape, backpack, glasses, a held item
and colour words ("a green cloak").

1. `action=propose project=<p> brief="<their words>" style=creator64`: three variants, each with a contact sheet
   (front, three-quarter, side and back) and `card` numbers (triangles, colours, height, heads tall). Blender is not
   needed. `project` must be an existing game; if there is none, make one first with `hermes64_scaffold`.
   **The user picks.**
2. The same typed edits apply: `swap{part, value}` with a size ("make the hat taller": `part=hat.star_wizard value=1.3`),
   `color{slot, role}` with a colour name ("her cloak to green": `slot=cape role=green`),
   `face{preset: face.round|face.anime|face.dot|face.sleepy, expression: neutral|smile|worried|surprised, beard}`,
   `hair{style: long|bob|bun|crop|curly|ponytail|spiky|bald, color}`,
   `prop{part}`, `height{value}`. Module ids, colours and examples: `action=list what=parts style=creator64`.
3. `action=build recipe=<proposal.variant>` and then `bind` work as above. `info id=creator64` shows the card.
   Words it cannot make are listed in the notes as "not available: ...". Tell the user.

## Look-ups

`action=list what=parts|bodies|styles|recipes|cast`, `action=info id=<part, body, style or recipe>`.

## Rules

- People display names stay placeholders (`placeholder: true`) until the owner names them; the masked lead is Qhantom.
  The plugin's own cast is renamed only in `catalog/names.json`; ids never change.
- Brief words the library cannot express on that body are listed in the recipe `notes` ("not available: ..."):
  tell the user instead of silently substituting.
- Robots and bosses are original designs; never imitate a real company mark or a protected character.
- New bodies build without Blender: the python exporter (numpy in `python_path`) writes the skinned, animated GLB
  for every body, robots included, and every gate runs, the rig kit validator first. Blender is optional
  (`character_exporter=blender` uses it to build; when it is configured it also renders the review images).
  Without Blender there are no contact sheets and the silhouette gate is reported under `not_run`: say so, and
  describe the variants from their summaries instead of showing sheets. Never call a not-run gate passed.
- The cameo pack is optional and removable; it is bound as an asset, never generated.
