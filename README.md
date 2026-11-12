# Hermes64

Hermes64 is a plugin that lets your own Hermes agent make and edit small, room-based 3D adventure games in a late-1990s console style. You describe the game; your agent works with Godot, structured game data, story checks and bot playtests.

## Install, then ask

With Hermes already working, install from the public repository (https://github.com/Qhantom-Labs/hermes64):
```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
```
This needs the network: Hermes clones the repository and asks before preparing numpy and Pillow. Approve dependency preparation only after reviewing the prompt. **Restart Hermes, then start a NEW chat after install**; an existing chat may not see the plugin.
If Hermes says dependency install was skipped (non-interactive shell), run `hermes plugins enable hermes64` in a terminal and approve numpy/Pillow; the zip route needs numpy/Pillow in the Python the plugin runs under (set the `python_path` setting if a run stops on NumPy).

If the one-liner is unavailable, or you need an exact release, use the release zip (Mac, default Hermes home `~/.hermes`). The zip is attached to the GitHub release of this repository, when one exists; otherwise ask the maintainers. Move any older `plugins/hermes64` outside `plugins/` first:
```sh
ZIP=hermes64-rc81-XXXXXXXX.zip  # the rc8.1 file you downloaded
shasum -a 256 "$ZIP"            # must equal the published SHA-256
mkdir -p ~/.hermes/plugins
ditto -x -k "$ZIP" ~/.hermes/plugins
python3 -B ~/.hermes/plugins/hermes64/tools/check_install.py
hermes plugins enable hermes64
```
Zip steps for Windows (PowerShell, `Expand-Archive`) and Linux: [Windows guide](docs/WINDOWS.md) · [Linux guide](docs/LINUX.md). Full checksum/backup recipe: [Install for your agent](docs/INSTALL-FOR-YOUR-AGENT.md).

> Make me a game about a wizard tower with a ghost and three crystal keys.

**Expect minutes, not an instant finished game.** The agent plans, builds, lets bots play, and should report what it could not make. Missing Godot stops the build for your approval; it is not downloaded automatically.

**Games:** normally `<Hermes home>/plugin-data/hermes64/games`, or your configured `projects_root`. Older hosts need an explicit folder.

**Platforms:** macOS: verified. Linux: three real Debian 13/bwrap 0.12.0 runs; run 3 reached C7 12/12 and real private-Xvfb captures, but exposed an incorrect capture verdict and a PulseAudio symlink blocking later calls. Candidate repairs await a fourth Linux run. Windows 11: one real run: runner/diagnostic exports pass, default demo failed on Blender 4.5 (candidate repair pending native rerun), no human play. **Linux and Windows: Not verified. Tested by the owner: Not yet.** Linux play means bots. [What each claim rests on](docs/PLATFORM-EVIDENCE.md).

[Quick start and troubleshooting](QUICKSTART.md) · [Game-type strengths and measured limits](docs/GAME-TYPE-STRENGTHS.md) · [Honest scope](docs/AUTHORING-SCOPE.md)

## Demo

**Teknium vs. Tyrants** is a separate demo game built with Hermes64.
It was authored as data through the plugin's create, compile and bot tools.
It demonstrates combat waves and sequential CEO duels.
Bots exercise the authored encounters and prove completion of the tested route.
That is mechanical evidence, not a claim about player-facing polish or human playability.
The demo is separate from the plugin; its assets are not needed to install Hermes64.
Demo video: https://x.com/arkqhantom/status/2120627040840044863

## What works best, and the limits

Best supported settings (measured): medieval village and castle, snow village, night village, shore and lighthouse, island, western town, cyber city.
A plain brief gets a crafted hero, 3-4 made objects and an entry layout chosen from the setting.
Settings without ready-made rooms (for example space, underwater, desert, candy) have no ready-made rooms in this release: the flow stops with a clear message, and the agent may hand-author rooms or pick the nearest pack.
The default shape is two rooms, one outside and one inside; more rooms and mechanics can be added with the author skill.
No jumping or platforming. Games are checked by bots, not by human playtests. Windows and Linux are not verified.

## Requirements and setup

| Requirement | What to know |
|---|---|
| Hermes Agent | Manifest floor `>=0.18.2`. The older-host adapter is not a clean-install certification. The quick start separates local source checks for 0.18.2, 0.22.7 and 0.23.1 from actual runtime checks. |
| Godot | **4.6.2**, standard build, not .NET. Export templates are needed only for exports. |
| Python dependencies | `numpy>=2.0,<3` and `Pillow>=11.3,<14` are declared in `plugin.yaml`. Recent Hermes installers can prepare them with consent. A separately configured `python_path` must have the needed packages too. Do not assume old hosts install them. |
| Blender | Optional for the default static-room workflow: `builder=auto` can use the Python builder with numpy when Blender is absent. Some character workflows still require Blender; strict static-mesh parity is not established. |
| bubblewrap | Linux only: `bwrap` 0.4 or newer is the child sandbox; without a working one, making games is off. |

In a new chat, `/hermes64 setup` is a read-only checklist. The agent can call `hermes64_doctor` for the same setup guidance; it cannot approve downloads through that tool.

If Godot is missing:

1. Type `/hermes64 setup --fetch` to inspect the official download plan. It downloads nothing.
2. If you approve it, type `/hermes64 setup --fetch --yes` yourself.
3. Retry your game request. Add `--templates` to the approved fetch only when you need exports.

The fetch checks pinned SHA-512 before unpacking the official Godot release. It uses a per-user cache, not the plugin directory; on macOS it removes quarantine only from the verified fetched Godot app and checks `--version`. On Linux the fetch is refused until a Linux SHA-512 pin is added; install Godot by hand ([Linux guide](docs/LINUX.md)). Downloads and template storage are extra setup, not game-build time. [Setup details](docs/SETUP-FETCH.md).

## What the agent can do

- Plan a game with the bundled `hermes64:hermes64-create` skill, build it and read `CREATE-REPORT.md`, including every `Not applied` row. The create flow's output and report end with a **How to play** block (game folder, the `Play:` command for the built game, default keys), and the skill asks the agent to pass it on.
- Make a faster, narrower starter with `/hermes64 new "A fox searches the village for its lost lantern"`. This is not the full agent-designed workflow. Use its returned `Play:` command, not a guessed game path. Its reply has a `Note:` line when your names get stock shapes (in this example the fox is the standard human body and the lantern the pack's key model), when a requested genre such as racing is not supported, and with the measured reason when its style audit scores below 90.
- Author larger finite room graphs, dialogue, gates and endings with `hermes64:hermes64-author`. Grid puzzles use a separate module workflow.
- Edit supported story data, then re-check it. `hermes64_edit` requires a proved story; combat/course games can be conditional and need the create/module workflow instead.
- Build rooms and props from packs and bounded data recipes, reuse the public cast, work with audio, and export for macOS, Windows or web subject to each target's requirements.

The package declares **27 tools**, one `pre_llm_call` hint hook, the `/hermes64` command, **11 bundled skills**, and a Desktop Studio extension. These are inventories, not a claim that every workflow has passed on every host (`plugin.yaml`, `__init__.py`).

Games are local editable projects. Bot completion, finite story proof, replay and measured image checks are different results; none judges fun, balance or appearance. Games can fail the plugin's own measured style audit. Quick starters measured on the development Mac: no style word FAIL 84/100; a castle premise (`castle_keep`) FAIL 0/100, also after its window fix; `polar` after the premise WARN 97/100. Rebuilding 21 earlier agent-game briefs without the agent: 8 FAIL, 12 WARN, 1 PASS. Unsupported requests include general jumping, climbing, swimming, vehicles, player gun/aim/ammo systems, multiplayer, seamless open worlds and arbitrary per-game scripts.

## Time and evidence

A full agent-designed game takes minutes to craft; allow longer for more authoring, repairs and iteration. The create skill budgets 2–15 minutes for its build stage, not a guaranteed deadline. Setup and downloads are separate. Do not repeat a build just because a foreground call timed out: the agent should run the long build in the background and wait for its report.

The game-type table records earlier measured examples with their conditions and failures. Those numbers are not a success rate for new prompts or a certification of this candidate. No all-green test-suite or clean first-install claim is made here: before rc8's last documentation merge, the plugin's 1,728 tests ran on the development Mac with 1 failure (a check that reads a development evidence file the package does not carry).

## Settings and storage

Use the active profile's Hermes64 settings (`plugins.entries.hermes64.settings`):

- `projects_root`: an existing absolute games directory. On current storage-capable hosts, blank uses `<Hermes home>/plugin-data/hermes64/games`. The 0.18.2 adapter requires an explicit directory. Existing games are not migrated automatically.
- `godot_path`, `blender_path`, `python_path`, `ffmpeg_path`: explicit executable paths override discovery. A bad explicit path is an error, not a fallback.
- `builder`: `auto`, `python` or `blender`; `character_exporter` is a separate setting.
- `hub_url`: optional trusted HTTPS registry; blank disables Hub downloads.

[How to play and default keys](PLAY.md) · [Host compatibility](docs/HOST-COMPAT.md) · [Playtests and reports](docs/PLAYTEST.md) · [Exports](docs/EXPORT.md)

## Platforms and security boundaries

**macOS:** the central build/check/play/export runner uses `sandbox-exec`, denying network and confining writes. Not every helper uses that runner; consult [platform parity](docs/PLATFORM-PARITY.md).

**Windows 11:** child execution requires an owner opt-in to `HERMES64_WINDOWS_RUNNER=job`, followed by a restart. Job Objects limit resources and child lifetime (each child is placed in its job before it runs), but provide **no OS-enforced network or write confinement**. This candidate's native Windows install/build/export remains unverified. [Windows guide](docs/WINDOWS.md) · [test sheet](docs/WINDOWS-TEST-SHEET.md).

**Linux:** three real Debian 13/bwrap 0.12.0 runs now reach C7 12/12 and private-Xvfb rendering. Run 3 still failed D10's capture classification and D11 after a PulseAudio runtime symlink appeared; candidate repairs await a fourth run. **Not verified.** The bubblewrap design confines network/writes and hides home; without a working sandbox every child is refused. `HERMES64_LINUX_RUNNER=unconfined` is an explicit owner opt-in with **no OS-enforced network or write confinement** (process-group kill and rlimits only), never a sandboxed READY result. macOS exports and native Linux exports are not available from Linux. [Linux guide](docs/LINUX.md).

**Local processes:** Godot, Python, optional Blender and user-provided ffmpeg. Some character/preview/audio subprocesses are outside the central runner; shipped child sites use explicit sanitized environments, with the documented create-flow self-rerun exception. Sanitization is not OS confinement. [Child-environment audit](docs/REVIEWFIX-ENV-AUDIT.md). Plugin code is not a universal sandbox.

**Network:** normal game creation does not fetch Godot. Optional approved setup fetches and configured Hub reads use HTTPS; Hermes dependency preparation is a separate host action. The plugin manifest declares no credentials or required environment secrets. That declaration is not a guarantee about every external program it launches.

**Files and background work:** project data, generated assets, reports and exports use project/data roots; setup has a separate cache. One exception: when the agent create flow generates a style pack for a game, it saves that pack inside the installed plugin folder (285 to 288 files under `kits/library/`, `kits/packs/` and `packs/`, plus one `mood-report-*.json`, in 3 of 4 judged rc6 builds), and `tools/check_install.py` then lists those files as extra. Studio Play can serve an exported game on `127.0.0.1` at a random port, with a 30-idle-minute limit. [Disclosure](docs/DISCLOSURE.md) · [Setup download disclosure](docs/SETUP-FETCH.md).

## Licence and submission

MIT ([LICENSE](LICENSE)), copyright Qhantom Labs and Hermes64 contributors. Godot is not bundled; its notices are in [licenses/](licenses/). The default package excludes the optional cameo pack. A model waiver is not a licence or permission to redistribute private demo assets.

**Hermes64 itself is the plugin submission.** A showcase game illustrates it; installing the plugin does not require that demo. The repository is public; catalog submission, video/post and form submission are separate owner decisions.
