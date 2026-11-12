# Changelog

## 1.0.0-rc9 (platforms: Linux runner and Windows fixes, 2026-11-11; post-submission product work)

- Platform claims now follow evidence: macOS verified; Windows 11 targeted, built and simulated, not verified (the only PC reports are relayed prose about older packages, no receipt); Linux authoring implemented behind bubblewrap, not verified. `docs/PLATFORM-EVIDENCE.md` maps every claim to its evidence; `PLATFORM-PARITY.md`, README, install docs and `WINDOWS.md` agree with it. No claim was upgraded.
- Linux: children run inside bubblewrap (new namespaces, no network, read-only system folders, home hidden, the project the only writable folder, rlimits, PID-namespace tree kill) after a one-time functional probe; without a working bwrap every child is refused with the cause (missing bwrap, Ubuntu AppArmor userns restriction, userns sysctls, container, WSL 1) and the fix. `HERMES64_LINUX_RUNNER=unconfined` is an explicit owner opt-in (no OS-enforced network or write confinement; process-group kill and rlimits only), disclosed in doctor, setup, the `/hermes64 new` reply and every run result.
- Linux discovery: official Godot 4.6.2 file names in the usual folders, Blender tarballs, `HERMES64_GODOT` / `HERMES64_BLENDER` / `HERMES64_PYTHON`; snap and flatpak builds are detected and skipped with a sentence. `python3 -m adventure_maker.doctor --linux-checklist`; a **Child runner** row in `/hermes64 setup` on Linux and Windows. Godot fetch on Linux is refused: no Linux SHA-512 is pinned (the docs say how a maintainer adds one; none was guessed). Exporting a macOS app from Linux is refused with the Windows sentence; native Linux export is not supported yet; Linux web exports use the hash-checked template copy inside the project.
- Windows: the Job Object child is created suspended, assigned to its job, then resumed (no grandchild can escape the kill); the Studio offers **PLAY WINDOWS BUILD** on a Windows backend (same explicit confirm); Blender is also found in Steam and unzipped portable folders, newest version first; no console windows from setup probes or the character-gate fallback; install docs give the PowerShell/zip route and the real Hermes home (`%LOCALAPPDATA%\hermes`).
- The core `hermes64` skill is shown on Windows and Linux too (it was macOS-only, so Hermes hid it there).
- New test sheets for real machines: `docs/LINUX-TEST-SHEET.md`, `docs/WINDOWS-TEST-SHEET.md` (v4), with receipt templates in `docs/receipts/`. "Tested by the owner" stays "Not yet."
- Known limits: nothing in this entry has run on Windows or Linux; macOS (and the Linux unconfined mode) cannot kill a grandchild that starts its own session; five skills stay macOS-only.

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
