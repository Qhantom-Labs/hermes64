---
name: hermes64-characters
description: Make house-style characters with hermes64_character.
version: 0.1.0
author: Dylan (Qhantom), Hermes Agent
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

## Look-ups

`action=list what=parts|bodies|styles|recipes|cast`, `action=info id=<part, body, style or recipe>`.

## Rules

- People display names stay placeholders (`placeholder: true`) until Dylan names them; the masked lead is Qhantom.
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
