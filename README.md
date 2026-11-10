# Hermes64

A Hermes Agent plugin that makes small 3D adventure games in the style of late-1990s consoles. You describe a game in one sentence; Hermes64 builds a two-room playable starter in Godot, checks that it can be finished, lets two bots play it, and then edits it when you ask in chat. Games are ordinary Godot projects on your disk.

## What you get

- `/hermes64 new "<premise>"`: a new game from one sentence, with a style picked from the premise (or named).
- Edits by chat: the agent moves doors, adds endings, changes roles or applies a bounded JSON patch, then re-checks the story.
- Style packs, room kits, characters, audio and optional gameplay modules (arenas, timed courses), all as data files.
- A proof badge per build: story proof, bot playtests, softlock count; it never claims more than its reports ([docs/PROOF-BADGE.md](docs/PROOF-BADGE.md)).
- Local exports for web, macOS and Windows.
- A local Hub of styles, kits, characters, sounds and games, checked before install ([docs/HUB.md](docs/HUB.md)).
- 27 agent tools, the `/hermes64` slash command, 7 bundled skills, and a Studio tab for the Hermes desktop app.

## Requirements

| | |
|---|---|
| Hermes Agent | 0.20.1 or newer (`requires_hermes: ">=0.20.1"`). On 0.20.1 to 0.20.3, Studio cannot find the default games folder: set `projects_root`. Tested on 0.22.7 only. |
| Operating system | macOS (Apple silicon or Intel). Windows: see [Platforms](#platforms). |
| Godot | 4.6.2 standard build (not .NET), from https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable. Export templates only if you export. |
| Python packages | numpy and Pillow, declared in `plugin.yaml` (`numpy>=2.0,<3`, `Pillow>=11.3,<14`); Hermes installs them into its own Python when you install the plugin. |
| Blender | Optional. The default room builder setting is `blender`; set `builder` to `python` or `auto` to build without it. |

## Quickstart (about 2 minutes once Godot is installed)

```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
```

Restart Hermes, then in a Hermes chat:

```text
/hermes64 new "A fox searches the village for its lost lantern"
```

After 10 to 40 seconds you get a few lines: where the game was saved, the style chosen, the badge, and a `Play:` command. Run the `Play:` command in a terminal to open the game. Keys: WASD move, E act, Tab actions, I inventory, Esc settings ([PLAY.md](PLAY.md)).

If Godot is missing, the command says so and prints the install steps for your OS; ask the agent to run `hermes64_doctor` for a read-only check of everything it needs. A model can do the same as the slash command with `hermes64_demo(premise="...")`. Step-by-step guide: [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Settings

All optional (Settings, Plugins, Hermes64, or `plugins.entries.hermes64.settings` in `config.yaml`):

- `projects_root`: existing absolute folder for your games. Blank: games go to `<Hermes home>/plugin-data/hermes64/games`.
- `godot_path`, `blender_path`, `python_path`, `ffmpeg_path`: override discovery. A bad explicit path is an error, never a silent fallback.
- `builder`, `character_exporter`: `python`, `blender` or `auto`.
- `hub_url`: an https Hub registry you trust. Blank (the default) means no network.

## Platforms

- **macOS**: supported. Every child process runs under `sandbox-exec`.
- **Windows 11**: not supported at this version. The process runner needs a sandbox and fails closed off macOS (`sandbox_unavailable`), so builds, checks and exports do not start. Windows support is a separate change.
- **Linux**: not supported (same reason).

## What this plugin does on your computer

**Runs local programs.** To build, check, play and export games Hermes64 starts Godot 4.6.2, Blender (optional), Python (your Hermes Python by default) and, only for audio import, your own ffmpeg. On macOS these run inside `sandbox-exec` with no network and writes limited to the game's folder; every run has a time limit (up to 1 hour for character exports). Children started by the build runner, the character gate and the Godot previews get a scrubbed environment (no API keys, tokens, proxies or Hermes flags); the ffmpeg audio import and the Blender character exporter still inherit Hermes's environment. On macOS it also uses `sips` (image resizing), `launchctl` (to detect a desktop session) and `open` (Studio's Launch button).

**Network.** Off by default. If you set `hub_url`, it reads that Hub registry over HTTPS (no redirects). Nothing is ever uploaded and there is no telemetry. Hermes itself installs numpy and Pillow from PyPI when you install the plugin.
<!-- A3 (godotfetch merge): add the setup-download paragraph from docs/SETUP-FETCH-DISCLOSURE.md here. -->

**Background process.** Studio's Play button serves one exported web game from `127.0.0.1` on a random port; it stops when you close it or after 30 idle minutes.

**Files it reads or writes.** Games go to the folder you set as `projects_root` (default: `<Hermes home>/plugin-data/hermes64/games`). It reads Godot, Blender and ffmpeg where you installed them, Godot's export templates folder (read and hash-checked, never written), and reference images or audio you point it at. It never reads your Hermes credentials, `.env` files or other apps' data, and never writes into its own plugin folder.

**Credentials.** None needed or stored.

## Limits

- The first game is a two-room starter, not a finished game.
- Bot playtests show a game can be finished; they do not judge fun, balance or how it looks.
- The default first game can fail its own style audit; the default `builder` needs Blender.
- Long steps (export about 100 s, checks about 50 to 90 s) show no progress output.
- Character placeholders are marked as such; actual rig and animation acceptance is not claimed.
- Windows and Linux: see [Platforms](#platforms).

## Docs

[Quick start](docs/QUICKSTART.md) · [Playing](PLAY.md) · [Hub](docs/HUB.md) · [Exports](docs/EXPORT.md) · [Proof badge](docs/PROOF-BADGE.md) · [Disclosure details](docs/DISCLOSURE.md) · [Package contents](docs/PACKAGE-CONTENTS.md)

The Studio tab's `desktop/plugin.js` is generated from `studio/prototype/js/*`, `studio/prototype/studio.css` and `studio/plugin/glue.js` by `python3 -B studio/tools/sync_shared.py`.

## Licence

MIT ([LICENSE](LICENSE)). Godot is MIT-licensed and is not bundled. The optional cameo pack carries its own notice ([cameo/LICENSE-CAMEO.md](cameo/LICENSE-CAMEO.md)); delete `cameo/` to remove it. Third-party notices: [licenses/](licenses/).
