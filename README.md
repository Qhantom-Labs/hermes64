# Hermes64

A Hermes Agent plugin that makes small 3D adventure games in the style of late-1990s consoles. Describe a game in one sentence; Hermes64 builds a playable starter in Godot, checks its story, lets bots play it, and edits it when you ask in chat. Games are ordinary Godot projects on your disk. A starter is not a finished original game.

## What you get

- Ask your agent "make me a game about ...": it plans, builds, proves and bot-plays a game from your sentence. `/hermes64 new "<premise>"` makes a quick starter with a style and supported template picked from the premise, or named explicitly.
- Edits by chat: move doors, add endings, change roles or apply a bounded JSON patch, then re-check the story.
- Style packs, room kits, characters, audio and optional gameplay modules (arenas, timed courses), all as data files.
- Place archetypes (wizard tower room, frontier main street, subway platform, castle great hall, forest camp) dress a room from data in the chosen pack and mood, with a render-and-measure loop and an approval store: see [docs/PLACES.md](docs/PLACES.md).
- A proof badge per build: story proof, bot playtests and softlock count; it never claims more than its reports ([docs/PROOF-BADGE.md](docs/PROOF-BADGE.md)).
- Local exports for web, macOS and Windows; a local checked Hub of styles, kits, characters, sounds and games ([docs/HUB.md](docs/HUB.md)).
- 27 agent tools, the `/hermes64` slash command, eleven bundled skills, and a Studio tab for the Hermes desktop app. Setup reporting is included in `hermes64_doctor`, not a separate tool.

## Make an original game

Load **hermes64:hermes64-author** and ask the agent to design a world map, NPC dialogue, gates and endings, then compile/check/bot/replay it. The compact outline compiler and reusable quest patterns are data-driven, not a reskin selector. Worked purple tower: `examples/wizard-purple/world.json`. [Authoring guide](docs/AUTHORING.md) · [Supported mechanics and limits](docs/AUTHORING-SCOPE.md). `/hermes64 new` is the starter workflow, not this complete authoring process.

## Requirements

| | |
|---|---|
| Hermes Agent | 0.18.2 or newer (`requires_hermes: ">=0.18.2"`). 0.18.2–0.20.0 uses the bundled compatibility adapter and needs an explicit `projects_root`. On 0.20.1–0.20.3, set `projects_root` for Studio. Old-host compatibility is tested with stub contexts; the real catalog host exercised is 0.22.7. [Host compatibility](docs/HOST-COMPAT.md). |
| Operating system | macOS (Apple silicon or Intel) and Windows 11 only (`platforms: [macos, windows]` in `plugin.yaml`). Linux authoring is refused. Windows needs the opt-in Job Object runner; see [Platforms](#platforms) for limitations. |
| Godot | 4.6.2 standard build (not .NET), from https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable. Export templates are needed only for exports. |
| Python packages | numpy and Pillow, declared in `plugin.yaml` (`numpy>=2.0,<3`, `Pillow>=11.3,<14`); Hermes installs them into its own Python when you install the plugin. A configured `python_path` must have the packages too. |
| Blender | Optional. Default `builder=auto` uses Blender when found, otherwise the Python static-kit builder with numpy. `builder=python` selects Python explicitly; new armatures still need Blender. Strict mesh parity is not proven ([parity](docs/NOBLENDER-PARITY.md)). |

## Quickstart

Installation and activation require the owner's approval. Once the release repository is available:

```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
```

Restart Hermes, then just ask your agent in the chat, the way you ask it for anything else:

```text
Make me a game about a wizard tower with a ghost and three crystal keys
```

No slash command or skill name is needed. The agent finds the bundled `hermes64:hermes64-create` skill (on hosts that do not list plugin skills, a one-line hint from the plugin points it there), plans the game, builds it, lets bots play it and replies with what is in the game, what was not applied, the gate results, pictures and how to play it. With no `projects_root` set, games go to the same default folder `/hermes64 new` uses (`plugin-data/hermes64/games` in your Hermes home). Keys: WASD move, E act, Tab actions, I inventory, Esc settings ([PLAY.md](PLAY.md)). [Step-by-step guide](docs/QUICKSTART.md).

Checkup (optional): type `/hermes64 setup` for a read-only checklist, or ask the agent for `hermes64_doctor`; both also give the official editor/export-template download plan and cannot download or accept consent. Quick starter without the agent: `/hermes64 new "A fox searches the village for its lost lantern"` gives the game folder, style, badge and `Play:` command (a model can use `hermes64_demo(premise="...")` for the same starter). In the desktop app a slash command's reply is shown as small grey plain text; the agent's replies are normal chat messages.

If Godot is missing, review `/hermes64 setup --fetch`, then type `/hermes64 setup --fetch --yes` yourself to approve the official download. Add `--templates` for exports. Do not have an agent infer download approval from a request to make a game. [Setup details](docs/SETUP-FETCH.md).

## Settings

Settings, Plugins, Hermes64, or `plugins.entries.hermes64.settings` in `config.yaml`:

- `projects_root`: existing absolute folder for your games. With the documented storage API, blank uses `<Hermes home>/plugin-data/hermes64/games`. Older hosts need the setting or use their available `ctx.state` fallback; Studio on those hosts needs the explicit setting. Earlier pre-release games in the old namespaced folder are not moved or deleted: point `projects_root` at that folder to keep using them.
- `godot_path`, `blender_path`, `python_path`, `ffmpeg_path`: override discovery. A bad explicit path is an error, never a silent fallback. Godot discovery includes its verified setup cache.
- `builder`, `character_exporter`: `python`, `blender` or `auto`.
- `hub_url`: an HTTPS Hub registry you trust. Blank keeps Hub downloads off; the separately approved setup fetch is described below.

## Platforms

- **macOS**: central build/check/play/export children run under `sandbox-exec`, with network denied and writes confined to the project.
- **Windows 11**: the runner refuses children until the owner opts in with `HERMES64_WINDOWS_RUNNER=job` and restarts Hermes. The Job Object limits resources and kills its child tree, but provides **no OS-enforced network or write confinement**. This composed tree has Mac simulation evidence, not a new native-Windows acceptance. Earlier PC results concern an earlier package: [platform parity](docs/PLATFORM-PARITY.md), [Windows details](docs/WINDOWS.md), [test sheet](docs/WINDOWS-TEST-SHEET.md).
- **Linux**: not a supported platform for this plugin. Authoring children fail closed because there is no Linux sandbox implementation. Exported web builds can still run in a browser.

Windows discovery checks Godot in `%LOCALAPPDATA%\Programs\Godot`, Program Files, winget, scoop, the verified cache and PATH; an explicit override wins. Check installation with `py tools\check_install.py` and `py -B -m adventure_maker.doctor --windows-checklist`. Windows export targets are `windows` and `web`; `macos` needs a Mac. To serve an exported web folder locally: `py -m http.server 8000`. Unsigned exported games can trigger SmartScreen: More info, then Run anyway. Saves and logs are per game under `%APPDATA%\Hermes64\<game id>` ([saves and legacy adoption](docs/SAVES.md)).

## What this plugin does on your computer

**Runs local programs.** To build, check, play and export games Hermes64 starts Godot 4.6.2, Blender (optional), Python (your Hermes Python by default) and, only for audio import, your own ffmpeg. Every run has a time limit (up to one hour for character exports). The central runner uses the platform isolation above. Some character/preview/audio subprocesses run outside that central sandbox: [platform parity](docs/PLATFORM-PARITY.md). Children started by the build runner, character gate and Godot previews get a scrubbed environment; ffmpeg audio import and the Blender character exporter still inherit Hermes's environment. On macOS it also uses `sips` (image resizing), `launchctl` (detect a desktop session), `open` (Studio launch) and the system `xattr` for an explicitly fetched, verified Godot app only.

**Network.** Off by default. If you set `hub_url`, it reads that Hub registry over HTTPS without redirects. Nothing is uploaded and there is no telemetry. Hermes itself installs numpy and Pillow from PyPI when you install the plugin.

**Setup download (only when you type it).** If you type `/hermes64 setup --fetch --yes` (or run `tools/hermes64_setup.py --fetch` and answer yes), Hermes64 downloads the official Godot 4.6.2 editor for your OS (`Godot_v4.6.2-stable_macos.universal.zip` or `Godot_v4.6.2-stable_win64.exe.zip`, capped at 512 MiB). With `--templates` it also downloads Godot's official export templates (`Godot_v4.6.2-stable_export_templates.tpz`, about 1.25 GB, capped at 1.4 GiB), keeps only the three players exports use and deletes the archive. Both come only from `github.com/godotengine/godot-builds` (redirects only to GitHub's release-asset hosts); every download must match Godot's published SHA-512 before unpacking. Files go to `~/Library/Caches/hermes64/` (macOS) or `%LOCALAPPDATA%\hermes64\` (Windows), never the plugin folder. It runs the verified Godot once with `--version`; on macOS it removes quarantine from that verified Godot.app only. The model-facing doctor only reports the plan and human command. No hosted stub bundle is used. [Full details](docs/SETUP-FETCH.md).

**Background process.** Studio's Play button serves one exported web game from `127.0.0.1` on a random port; it stops when you close it or after 30 idle minutes.

**Files it reads or writes.** Games go to your chosen/default games folder. It reads your installed Godot, Blender and ffmpeg, Godot export templates (hash-checked on export), verified setup cache, and reference images or audio you point it at. It never reads Hermes credentials, `.env` files or other apps' private data, and never writes into its own plugin folder.

**Credentials.** None needed or stored.

## Scope

Hermes64 makes room-based 3D games in a late-1990s console style: exploration and story, bounded melee arenas and bosses, grid puzzles and timed on-foot courses. It is not a general game engine for any prompt. Stories, gates and effects use finite contracts, and puzzle authoring is a separate workflow ([supported mechanics and limits](docs/AUTHORING-SCOPE.md)).

- **Not supported:** general jumping or air control, climbing, swimming, vehicles, a general shooter system, multiplayer, seamless open worlds, crafting or economy systems, and arbitrary per-game scripts. A requested thing can be missing; the plugin reports the gap instead of renaming a stock object.
- **Proof, bots and the style audit are separate results.** Bots follow bounded paths and cannot judge difficulty, fun or looks. On this release the default fox starter (`/hermes64 new "A fox searches the village for its lost lantern"`, Blender hidden) built its assets and 2 bots finished; its measured style audit scored **WARN 88/100** (2 rooms, none failing).
- Starter rooms are small (a 4 x 4 grid); a room-size setting is not in this release.
- Per game type, what is strong, what is rough and what is not supported, with measured numbers: [docs/GAME-TYPE-STRENGTHS.md](docs/GAME-TYPE-STRENGTHS.md).

## How long does it take?

**Starter: seconds. Agent-designed game: minutes. Polished game: plan for hours of iteration.** The hours are a planning allowance, not a measured benchmark. Setup and downloads are extra.

| What | Measured | Conditions |
|---|---|---|
| Starter: `/hermes64 new` with the fox premise | 18 s | One run of this release's package on the development Mac (Apple M4 Pro, other jobs running), Python room builder, Blender hidden. Style audit WARN 88/100 |
| Agent-designed game with the bundled `hermes64-create` skill, Claude Opus 5.5 (medium) | median 329 s, 10 tool calls per game | 6 detailed prompts, one run each, on the pre-release tree with this skill. 6/6 games built, 6/6 bot runs finished |
| The same with GPT-6.1 Sol (low) | median 277 s, 12 tool calls per game | Same prompts and tree. 6/6 built, 6/6 bot runs finished |

These are single samples on one machine, not latency promises. Reasoning levels are the requested settings.

## Tested hardware

| Platform | What ran | Not established |
|---|---|---|
| macOS, development Mac (Apple M4 Pro, 64 GB, macOS 27.0.1, Godot 4.6.2) | Native renders, bots, exports, and this release's package checks | Intel Macs; Gatekeeper and notarization on another machine |
| A second Mac (MacBook) | An earlier interim build: official Godot 4.6.2 download verified, Python room builder without Blender | Clean install, create, edit and export of this release |
| Windows 11 PC (RTX 4070 Ti SUPER, Hermes 0.18.2) | An earlier package: fox starter built, 2 headless bots passed, Windows and web exports booted, examples at 59-60 FPS | This release's package on Windows |

## Limits

- Starters need further authoring; module support is scoped to the exact build's reports.
- Bot playtests do not judge fun, balance or appearance. The default game can fail its own measured style audit.
- Some exported steps take time. Individual step timings and receipts are not continuous progress guarantees.
- Native-Windows execution of this exact composed package, real upstream setup downloads and installation with fresh dependencies need separate verification. Simulation and loopback fixtures are not substitutes.
- Character/rig and visual acceptance are specific to their recorded evidence; no human art approval is implied.

## Docs

[Quick start](docs/QUICKSTART.md) · [Authoring](docs/AUTHORING.md) · [Playing](PLAY.md) · [Hub](docs/HUB.md) · [Exports](docs/EXPORT.md) · [Proof badge](docs/PROOF-BADGE.md) · [Disclosure details](docs/DISCLOSURE.md) · [Package contents](docs/PACKAGE-CONTENTS.md)

The Studio tab's `desktop/plugin.js` is generated from shipped `studio/prototype/js/*`, `studio/prototype/studio.css` and `studio/plugin/glue.js` by `python3 -B studio/tools/sync_shared.py`.

## Licence

MIT ([LICENSE](LICENSE)), copyright Qhantom Labs and Hermes64 contributors. Godot is MIT-licensed and is not bundled. This package does not include the optional cameo pack. Third-party notices: [licenses/](licenses/).
