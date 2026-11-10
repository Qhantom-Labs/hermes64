# Hermes64 Hub

A shared shelf of styles, kits, characters, sounds, covers and whole games that anyone using Hermes64 can search,
install into their own game, and add to. Version 0 is **a folder of files**: an `index.json`, data-only archives and
preview pictures. The plugin ships one such folder, `hub/`, seeded with what Hermes64 already contains. It is built to
move to a public repository later without code changes.

```text
/hermes64 hub search snow kits          find things (words, plus an optional kind)
/hermes64 hub info kit.polar_pod.props  what it is, who made it, how it was checked
/hermes64 hub install kit.polar_pod.props my-game
/hermes64 hub pack my-game              turn your game (or a kit, character or sound) into a hub entry
/hermes64 hub publish game.my_game      a ready pull-request draft folder; nothing is uploaded
```

The same actions are one tool for agents, `hermes64_hub`. Browse offline by opening `hub/site/index.html`. It is a
static page that needs no network and works from `file://`; the copy button copies the install command.

## What an install does

1. Finds the entry in the registry (the bundled `hub/`, the folder in the `hub_registry` setting, or the `hub_url`
   registry), plus anything you packed yourself.
2. Checks that the archive's sha256 and size match the entry. Bundled entries are rebuilt from the plugin's own files
   and must hash to the committed value.
3. Runs the data-only validator (`adventure_maker/hub_archive.py`):
   - **Allowed file types**: json, glb, png, wav, ogg, md and txt, each parsed for real.
   - **Always refused**: scripts and programs (.gd .py .js .sh .exe .dll .so and more), unknown types, nested
     archives, symlinks, executable bits, path traversal, hidden files and oversize files.
   - **Zip bombs refused**: high compression ratios, unpacked totals, overlapping members and size lies.
   - **Also refused**: CRC errors, GLBs over the triangle budget (kits 1,500, characters 1,000), and any file not
     listed with its sha256 in the archive's own `HUB.json`.
4. Checks the hub contract (`hermes64-hub-pack/1`), the plugin version, and your game's locked style. A Polar Pod kit
   is refused by a game locked to the Forest Village kits, with a one-line reason. Character entries also name their
   rig (`compat.rig`, e.g. `human16_v1@1.0.0`, the rig kit contract in `rigs/<id>/rig.json`); an install is refused
   when this Hermes64 does not have that rig at the same major version.
5. Writes everything under `assets/hub/<id>/` and never overwrites anything. A theme pack also lands in
   `packs/<id>/`, where `hermes64_pack_select` can adopt it.
6. Records the install, with every file hash, in the game's `catalog.json`. That file uses the same schema as the
   asset catalog (`hermes64-catalog/1.0.0`). `hermes64_character` records the characters it builds or binds in the
   same file through the same writer (`adventure_maker/catalog.py`: `read_project`, `upsert`, `write_project`), so
   either tool can extend what the other wrote. A hub character bound to the cast reuses its install row.
7. A whole game installs as a new game. It is then compiled and proof-checked, and the result is reported as returned.

Every refusal is one plain sentence with the next step. Downloads are **off** unless the owner sets `hub_url`. Even
then, only that address is fetched: https only (plain http only for 127.0.0.1), no redirects, and a size cap.

## How to contribute

1. Make something with Hermes64: a game, a theme pack, or a pick of bundled kits, characters and sounds.
2. Pack it: `/hermes64 hub pack <game | catalog id | hub id> [version=1.0.0] [licence=CC-BY-4.0] [author="Your Name"]`.
   - Packing runs the same validator.
   - It refuses home-folder paths, email addresses and internal names in text files.
   - The archive is deterministic: the same files always give the same bytes.
3. Publish: `/hermes64 hub publish <id>` writes `drafts/<id>-<version>/` in your hub folder (`<Hermes plugin data>/hub`).
   - The draft holds `entry.json`, the archive, `README.md` and `PR.md`.
   - `PR.md` lists the checks already run, the honest verification tier and every file hash.
4. Fork the public registry, copy the draft folder into `drafts/`, and open a pull request with `PR.md` as the
   description.
5. The maintainer runs `python3 -B -m tools.hub add-draft drafts/<id>-<version> --registry hub`.
   - It validates the draft again and refuses a different archive under an existing id and version.
   - It then merges the draft into `index.json`, whose `entries_sha256` integrity hash is recomputed.

Ids look like `kind.name` (`kit.furn_lamp.polar_pod`). Ids never change; to change an entry, publish a new version.

## Licence policy

Every entry needs an SPDX licence id from this allow-list:

- CC0-1.0, CC-BY-4.0, CC-BY-SA-4.0
- MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC

The recommended licences are **CC-BY-4.0** for art and sound and **MIT** for code-free data such as games, theme
packs and style profiles. Missing or unknown licences are refused. The allow-list lives in the plugin
(`adventure_maker/hub_index.py`, `contracts/hub/1.0.0.json`); a registry cannot widen it.

- Authors are names, never email addresses.
- Each archive carries `LICENSE.txt`.
- Bundled assets keep their author (Qhantom Labs) and licence when re-packed.
- The optional cameo pack is `public-with-notice` and ships `cameo/LICENSE-CAMEO.md`. Its likeness is included with
  consent, for games made with Hermes64, and not for impersonation, endorsement or misleading use. Remove it in one
  step: delete `cameo/`, or run `python3 -B -m tools.catalog remove-cameo`.

## Moderation and takedown (draft policy)

- **Before merge.** A maintainer reviews every pull request. The tooling checks data-only content, hashes, licence and
  privacy patterns. A human checks that the submitter can grant the licence, that the content is not hateful,
  harassing, sexual or deceptive, that it does not impersonate a real person or brand, and that the tier label is
  honest.
- **Takedown.** Anyone can open an issue titled `takedown: <id>` for rights, likeness, safety or privacy problems. The
  maintainer hides the entry in the next index (its id is never reused). Clear rights or likeness claims are acted on
  first and discussed after. Hermes64 never deletes anything from a user's installed games; a later `info` shows the
  entry is gone.
- **Appeals.** The uploader replies on the same issue. Decisions and reasons are recorded in the registry's history.
- **Tiers are labels, not promises.** `proved` means the story checker proved the game. `validated` means it passed the
  data gates. `machine-checked` sounds are not human-approved. `data-only` means no render was ever judged.

## Moving the registry to a public repo

1. Copy `hub/` into a new repository, then run `python3 -B -m tools.hub archives <repo>/archives` to materialise the
   seed archives.
2. Point users at it with the `hub_url` setting (`https://<host>/<path>`), or at a local clone with `hub_registry`.
3. From then on, community entries arrive through `add-draft`. `tools.hub build` regenerates only the bundled entries
   and keeps merged community entries.

## Not included

- No accounts, logins, ratings, comments, payments or server.
- No telemetry and no automatic updates; nothing is pushed or uploaded by the plugin.
- No executable content of any kind: no scripts, shaders or engine scenes.
- Covers are a supported kind, but none are in this branch's seed. The four sample games from other lanes are not on
  this branch either.

Generated files: `catalog/catalog.json` (`python3 -B -m tools.catalog build|check`) and `hub/index.json`,
`hub/previews/`, `hub/site/` (`python3 -B -m tools.hub build|check`). Rename people or items in
`catalog/names.json`, then rebuild both. Results and commands: `docs/HUB-RESULT.md`. Next steps: `docs/HUB-ROADMAP.md`.
