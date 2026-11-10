---
name: hermes64-hub
description: Use when sharing or installing Hermes64 Hub entries.
---

# Hermes64 Hub (hermes64_hub, /hermes64 hub)

The hub is a local registry of styles, kits, characters, sounds, covers and whole games. The plugin ships one, `hub/`
(nothing is downloaded unless the owner sets `hub_url`). Full policy: `docs/HUB.md`.

## Actions

| Action | Arguments | What it does |
|---|---|---|
| `search` | `query`, optional `kind` (style, kit, character, sound, cover, game) | Ranked matches with id, kind, tier |
| `info` | `id` | Who made it, licence, checks run, compatibility, install command |
| `install` | `id`, `project` (omit `project` only for a `game` entry, which installs as a new game) | Verified install into the game |
| `pack` | `id` = a game, a catalog id (`kit:furn.lamp`) or a hub id; optional `version`, `licence`, `author` | Deterministic data-only archive in your hub folder |
| `publish` | `id` (something you packed) | A pull-request draft folder; never uploads |

Slash form: `/hermes64 hub search snow kits`, `/hermes64 hub install kit.polar_pod.props my-game`.

## Install rules (all refusals are one sentence with the next step)

- The archive sha256 and size must match the entry; every file must be listed with its hash in `HUB.json`.
- Data only: json, glb, png, wav, ogg, md, txt. Scripts, programs, nested archives, symlinks and zip bombs are refused.
- Compatibility (`compat` in the entry): hub contract, plugin version, the game's locked style, and for characters
  the rig (`compat.rig`, e.g. `human16_v1@1.0.0`); a character whose rig this Hermes64 lacks is refused (`hub_rig`).
- Files land under `assets/hub/<id>/` and are never overwritten. The install is recorded in the game's `catalog.json`
  (schema `hermes64-catalog/1.0.0`), the same file `hermes64_character` writes; both use one writer.

## Characters from the hub

1. `install` the character entry into the game.
2. Bind it to the cast with `hermes64_character` `action=bind source=community glb=assets/hub/<id>/models/<file>.glb
   display_name=...`. The bind runs the rig kit validator and reuses the hub row (licence, visibility).

The optional cameo (`character.cameo.<id>`, visibility `public-with-notice`) works the same way with
`source=cameo_pack`. Show the user its notice (`LICENSE-CAMEO.md`) before using it: likeness included with consent for
games made with Hermes64; not for impersonation, endorsement or misleading use. Packing refuses files that contain
the cameo's internal name, so the cameo is not re-shared inside community packs.

## Removing things

- From a game: delete `assets/hub/<id>/` and its `catalog.json` row (installs never overwrite, so this is the way to
  reinstall).
- The cameo from the plugin: delete the plugin's `cameo/` folder (the hub then stops listing it), or in the
  repository run `python3 -B -m tools.catalog remove-cameo`.
