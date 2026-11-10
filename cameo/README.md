# Optional cameo pack

Status: **available** (assembled at MERGE4). This folder holds one character model, `cameo_visor_01.glb`, based on
the likeness of Teknium, with its notice `LICENSE-CAMEO.md` (read it first) and the pack manifest `cameo.json`.
The core plugin never needs this folder.

| File | What it is |
|---|---|
| `cameo_visor_01.glb` | 111,204 bytes, 690 triangles, rig `human16_v1` (rig kit 1.0.0), clips idle, walk, run, interact, talk, carry, sit; sha256 `3df7030d6a4c4a9460def532a3779b43be1aedee39f242a2637d1f826e2c2f87` |
| `LICENSE-CAMEO.md` | the conditions for the likeness (consent, allowed uses, no impersonation, endorsement or misleading use) |
| `cameo.json` | the pack manifest the asset catalog and the hub read (`status`, expected sha256, rig, visibility) |

The asset catalog lists it as `character:cameo/cameo_visor_01` with visibility `public-with-notice`; the bundled hub
lists `character.cameo.cameo_visor_01` with the same notice and `compat.rig` `human16_v1@1.0.0`.

## Use it in a game

1. Install it into the game from the hub: `/hermes64 hub install character.cameo.cameo_visor_01 <game>`. This copies
   the model and `LICENSE-CAMEO.md` into `<game>/assets/hub/character.cameo.cameo_visor_01/` and adds one catalog row.
2. Bind it: `hermes64_character action=bind project=<game> source=cameo_pack
   glb=assets/hub/character.cameo.cameo_visor_01/models/cameo_visor_01.glb display_name="..."`. The bind accepts only
   that installed file, unchanged (same sha256) and next to its notice, and runs the rig kit validator.

## How it was assembled (re-verify any time)

1. In `lane-characters/published-r21/`, `shasum -a 256 -c SHA256SUMS` (30 files OK at MERGE4).
2. `cameo/cameo_visor_01.glb` is a byte copy of `published-r21/cameo_visor/cameo_visor_01.glb`; both hash to the
   sha256 above (as does the internal staging copy under `characters/internal/`).
3. `cameo.json` `status` set to `available`; then `python3 -B -m tools.catalog build` and `python3 -B -m tools.hub build`
   (the catalog hashes the model; the hub turns the old pending note into the `public-with-notice` character entry).
4. `tests/test_merge4_cameo.py` re-checks the hash, the rig kit validation, the hub install + bind path, the package
   rules and the one-step removal.

## Removing it (one step)

- **Plugin install:** delete this `cameo/` folder. The hub stops listing the entry and cannot install it; nothing
  else in the plugin reads this folder.
- **Repository:** `python3 -B -m tools.catalog remove-cameo` deletes the folder and rebuilds the asset catalog and the
  hub registry without it.

A game that already installed the cameo keeps its own copy (with the notice) until you delete that game's
`assets/hub/character.cameo.cameo_visor_01/` folder and its cast row.
