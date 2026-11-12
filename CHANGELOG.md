# Changelog

## Review fixes on rc8.2 (catalog review, 2026-11-12)

- Child processes: ffmpeg, the Godot version check, Blender, system tools and a game started from the Studio get the runner's minimal environment (system PATH, UTF-8 locale, home and temp folders in a scratch or project folder), never Hermes's environment or provider keys. Every place that starts a child is listed in `docs/REVIEWFIX-ENV-AUDIT.md`. A game started from the Studio keeps its saves in the project's `.maker/local` folders.
- Routing hint: a message that names another engine or language (Unity, HTML, pygame and others) gets the hint without its "Do NOT write HTML/..." sentence, so the user's explicit choice wins; the root and create skills say the same.
- Everything in the entries below.

## 1.0.0-rc8.1 (release candidate: rc8c plus routing, completion and text fixes, 2026-11-11)

- Routing: the root `hermes64` skill is a hard router to `hermes64-create` for any game request; `hermes64-author` is not an entry point for a new prompt; the pre-call hint and skill-loaded detection follow (HINTFIX).
- Completion rule: before replying, the create skill compares the build with every explicit requirement of the request and repairs missing parts for up to three rounds; if it stops, it lists the unmet requirements and the one next step. The root router says to finish the game that was asked for.
- Player-visible text: a pack's description is no longer shown as in-game narration; shipped style descriptions no longer name other companies' franchises (catalog and hub bindings regenerated) (SCRUB).
- README: dependency-skip note for non-interactive installs, rc8.1 zip recipe, and a short "What works best, and the limits" section.
- Not included: the accent-lamp repair (held), the create-skill rewrite and neutral stages for settings without ready-made rooms (not verified in time).
- Everything in rc8c below.

## 1.0.0-rc8c (release candidate: rc8 plus the variety change, 2026-11-11)

- The create run makes the game's own hero with the character maker and three or four pieces the brief names with the bounded generator loop (at most four tries each), from a plain prompt, with no extra parameter or tool; the entry layout is picked from the setting words. `CREATE-REPORT.md` has a `Made new for this game` line, and a hero or piece that was not made is a `Not applied` row with the closest stand-in.
- Everything in rc8 below.

## 1.0.0-rc8 (release candidate, 2026-11-11)

- Create flow: the medieval create patterns reserve accent floor lamps; the create output and `CREATE-REPORT.md` end with a **How to play** block (game folder, the `Play:` command for the built game, default keys); the quick starter's reply adds `Note:` lines for stock shapes, unsupported genres and a style audit below 90; the `castle_keep` window binding is fixed.
- Install and public text: the one-line `hermes plugins install Qhantom-Labs/hermes64 --enable` comes first in the README and both quick starts, with the release zip as the fallback; root `QUICKSTART.md`, `CHANGELOG.md`, `SECURITY.md` and `.gitignore`; `PLAY.md` ships at the package root; the catalog checklist and disclosure describe the current state; the dashboard manifest version is `1.0.0-rc`, as in `plugin.yaml`.
- Checked on the development Mac before the last documentation merge: the plugin's full test suite, 1,728 tests, with 1 failure (a check that reads a development evidence file the package does not carry); 27 tools, 5,998 of 6,000 schema tokens.

## rc8 documentation notes (merged)

- Put the install commands, first prompt, new-chat requirement, expected build time, storage location and platform limits at the top of the README.
- Add a root quick start and checksum/backup ZIP-install instructions. Separate local parser checks from unverified install/enable and Windows execution.
- Add security reporting guidance and local public-readiness findings. Keep submission drafts separate from the installed plugin.

These documentation changes are part of rc8.

## 1.0.0-rc baseline: rc7

The inspected rc7 package identifies source `807b472dcce4d1a63f7163afde602c614198a7fe`, version `1.0.0-rc`, 27 declared tools and a `pre_llm_call` hook. Its manifest lists 5,964 files, excluding the manifest itself. The local copy passed `tools/check_install.py` for all listed files.

The package contains game authoring, story checks, bot playtests, local export paths, 11 bundled skills and Desktop Studio sources. This inventory does not establish clean installation, current native Windows acceptance, universal prompt support, visual approval or catalog admission. See [README](README.md), [quick start](QUICKSTART.md) and [scope](docs/AUTHORING-SCOPE.md).
