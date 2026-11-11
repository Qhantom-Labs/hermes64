# FIRSTRUN report: Hermes64 first run for a stranger (Mac, simulated)

Lane FIRSTRUN, branch `firstrun-lane` from `main` 32a8ca48. Model header: [FIRSTRUN-MODEL.md](FIRSTRUN-MODEL.md). Plain user guide: [QUICKSTART.md](QUICKSTART.md).

## How the fresh user was simulated, and what that does not prove

- Package: `python3 -B -m tools.package --out <S>/pkg/hermes64 --zip <S>/hermes64-firstrun.zip` (4,960 files, zip 44 MB, 33 s). Rebuilt after the fixes as `hermes64-firstrun2.zip` from `d5551d8`.
- User: `env -i` with a private `HOME` and `HERMES_HOME` under a scratch folder `<S>`, `PATH=/usr/bin:/bin:/usr/sbin:/sbin`, HTTP(S) proxies pointed at a closed loopback port (no network). The real `~/.hermes` was never read or written by the plugin. The second run used the default macOS `TMPDIR` (`/var/folders/...`).
- Host: this Mac's installed Hermes (`~/.hermes/hermes-agent`). The `hermes` launcher cannot start in a brand-new `HERMES_HOME` offline (it tries a `uv sync` and stops with "no dependency environment is committed for this install"), so commands ran through the same install's venv Python (`venv/bin/python -m hermes_cli.main ...`), and tools/commands were called through Hermes's real plugin loader and tool registry (`hermes_cli.plugins.discover_plugins()`, `tools.registry.registry.dispatch`, `get_plugin_command_handler('hermes64')`). No LLM was in the loop: tool arguments were typed by hand.
- Mac state that leaked into the simulation and could not be removed: Godot 4.6.2 at `/Applications/Godot.app`, Blender 5.2 via Homebrew, numpy 2.4.3 in the Hermes venv (the plugin's default Python), Apple M4 Pro GPU. Godot export templates were absent from the scratch home (real first-run state) and then cloned into it from this Mac's copy to test export.
- "No Blender" and "no Godot" were simulated by making the plugin's program finder refuse them inside the driver process; "no numpy" by setting `python_path` to `/usr/bin/python3` (no numpy in isolated mode). These prove the messages, not a machine that truly lacks the programs.

## Step table

| # | Step (exact command or call) | What the user sees | Time | Result |
|---|---|---|---|---|
| 1 | `unzip -q hermes64-firstrun.zip -d ~/.hermes/plugins` | one `hermes64/` folder | <2 s | pass |
| 2 | `python3 ~/.hermes/plugins/hermes64/tools/check_install.py` (system Python 3.9) | `PASS hermes64 0.1.0 ...: 4960/4960 files verified (sha256), cameo present, source 50c539ce7310 (clean tree)` | 1.5 s | pass |
| 3 | `hermes plugins validate ~/.hermes/plugins/hermes64` (launcher) | only `uv sync` connection errors, then "run `hermes pm repair`"; no validation output | 15 s | fail (host, fresh offline home) |
| 3b | same via `venv/bin/python -m hermes_cli.main plugins validate ...` | 16 checks, one expected isolation note (`refpack/blender_proof.py:56`), `Validation passed.` | 89 s, no progress output | pass, slow (host) |
| 4 | `hermes plugins enable hermes64` | `AdmissionRefused: venv: uv sync exited 2 ... Connection refused` | 15 s | fail offline (host, known since MERGE4) |
| 4b | write `plugins: enabled: [hermes64]` into `~/.hermes/config.yaml` (documented fallback) | `hermes plugins list` shows hermes64; loader: 27 tools + `/hermes64` | | pass, confusing (hand-edit YAML) |
| 5 | `hermes64_doctor {}` before any game | before fix: `missing required or unknown arguments`; with `project`: "Choose an absolute projects_root in adventure-maker settings" | 0 s | **fail, fixed** |
| 5b | `hermes64_doctor {}` after fix (fresh home, `/var/folders` TMPDIR) | table + guidance; templates line (missing); temp probe folder removed | 0.2 s | pass |
| 6 | `/hermes64 new "A lighthouse keeper rescues sailors during a winter storm"` | `Made ... but it needs work: style audit FAIL 0/100`; `Style: village (n64_v0)`; badge `proof-checked · 2 bots played · assets built · style audit FAIL 0/100 · 0 softlocks · PLAYABLE (headless)`; `Play:` line | 16-18 s | pass, confusing (FAIL badge by default) |
| 7 | `hermes64_check {project}` (the verifier) | `proved`, witnesses for the one ending and collectible | 0.3 s | pass |
| 8 | `hermes64_replay {project}` | `passed`, save round trip true | 1.6 s | pass |
| 9 | `hermes64_export {targets:[web,macos]}`, no templates | one clear sentence: download the 1.25 GB templates, how to install, "(Missing target: web.)" | 0.2 s | pass (clear refusal) |
| 9b | same, templates present | `exported_local_only`; web 40 MB (verification not_run), macOS `.app` 186 MB (verification passed); `share/` under `.maker/runs/export-<hex>/` | 99 s, no progress | pass, slow; app named `Adventure Runtime.app` |
| 10 | card `Play:` line with `--headless --quit-after 120` | `BOOT game=lighthouse_keeper_rescues_sailors ... godot=4.6.2-stable` | 3.7 s | pass |
| 10b | exported `.app` binary `--headless` | `BOOT ... renderer=gl_compatibility` | 2 s | pass |
| 10c | `hermes64_open {seconds:8, screenshots:true}` (windowed) | capture report, assets and audio loaded, Apple M4 Pro | 16 s | pass |
| 11 | `hermes64_edit` move-entrance `room_a/passage` to east 2, `expected_changed_rooms:[room_a]` | `edited`, locality passed, room_b byte-identical | 1 s | pass |
| 11b | play the card's `Play:` line after the edit | before fix: still the pre-edit game (doors `north,1`); after fix: `play_runtime: refreshed`, doors `east,2`, boots | +1 s | **fail, fixed** |
| 12 | Studio backend: `settings_from_config()` + `api_catalogue()` (installed `dashboard/plugin_api.py`) | before fix: "No projects folder yet: set Projects root..." although `/hermes64 new` had made a game; after fix: the game is listed | <1 s | **fail, fixed** |
| 12b | Studio desktop tab in a real Desktop app | not run in this lane (MERGE4 ran a throwaway Desktop) | | not run |
| 13 | no Blender (simulated): `/hermes64 new "A fox searches the village for its lost lantern"` | `assets NOT BUILT (Blender not found; install Blender or set builder to auto with a numpy Python)`, `style audit FAIL 6/100`; last line claimed new character bodies need Blender | 10 s | pass, misleading line **fixed** |
| 14 | no Blender + no numpy (`python_path=/usr/bin/python3`): new + doctor | same badge; doctor shows static kits / characters / reference packs "no" but its only guidance said "set builder to python or auto", which cannot work without numpy | 18 s | confusing, **numpy guidance line added** |
| 15 | no Godot (simulated): `/hermes64 new ...` | one sentence: Godot 4.6.2 standard build, link, macOS and Windows steps, "nothing was created" | 0.7 s | pass |
| 16 | genre pack: `/hermes64 new "A robot gardener protects the last greenhouse on Mars" space_station --name mars-garden` | `needs work: missing_assets: 1`, `style audit FAIL 0/100`, `ROUGH (headless)` | 38 s, no progress | pass, confusing |
| 17 | `/hermes64` (no args), `/hermes64 hub search snow kits`, `/hermes64 hub install kit.polar_pod.props <game>` | help text; search list; refusal "locked to forest village (pack n64_v0)" | <1 s | pass, naming inconsistent |

## Fixes made (small, each with tests)

| Commit | Fix |
|---|---|
| `5de1668` | `hermes64_doctor` works before anything exists: `project` is optional; with no `projects_root` or no such game, the sandboxed Python probe runs in a temporary folder that is removed (path resolved, so a `/var` TMPDIR is fine). An existing game is still probed under its lock. Adds a doctor guidance line when numpy is missing. |
| `5de1668` | `hermes64_edit`, `hermes64_compile` and `hermes64_pack_select` refresh `/hermes64 new`'s `play/runtime` folder to the adopted revision (staged copy, swapped in only when complete; result field `play_runtime: refreshed / none / stale: ...`). Before, the card's `Play:` command kept opening the pre-edit game. |
| `09f50a1` | Studio backend falls back to the default games folder (`<HERMES_HOME>/plugin-data/<hermes64 namespace>/games`, via `hermes_cli.plugins_state.PluginState`) when `projects_root` is blank, matching the agent half. |
| `d5551d8` | New-game card's Blender line now says only `builder=blender` needs Blender and how to switch to `auto`; it no longer claims new character bodies need Blender. |
| `6c209fc` | `docs/QUICKSTART.md`, linked from the README. |

Tests: new `tests/test_firstrun.py` (6 tests: doctor with no settings, doctor with unknown game creates nothing, numpy guidance, edit refreshes Play folder, no Play folder left alone, Studio default folder) pass. `tests.test_newgame tests.test_merge_tools tests.test_merge4_doctor tests.test_registration tests.test_studio_catalogue tests.test_package tests.test_noblender`: 92 tests, 91 pass; the one failure (`test_merge4_doctor.test_export_templates_check_and_message`) is pre-existing and environmental: it uses a `/var/folders` temp dir, which the plugin's symlink guard rejects; it passes with `TMPDIR` inside the repository (6/6). Full `tools/verify_all.sh` was not run.

## Remaining issues, ranked by user impact (not fixed: design-level or another lane's files)

1. **The default first game fails its own style check.** Every `/hermes64 new` in this run ended "needs work": village (n64_v0) 0/100, forest 6/100 without assets, space_station 0/100 with `missing_assets: 1` and ROUGH. A stranger's first result is a red badge. Known since MERGE5 for n64_v0 (missing room shells); it hits the product principle "nailing the style by default".
2. **The one-line idea barely shapes the game.** The starter is the same two rooms ("Room A/B"), a "Traveller", a "keepsake" and "Finish the journey", with the pack's description text (a lighthouse in a winter storm got "Warm N64-era woodland village"). Only the title and style choice come from the premise, and keyword matching is rough ("winter storm" lost to "lighthouse/keeper/storm" -> village; "Mars" -> polar). The card does not say that Hermes (the model) should now author the real story with the tools.
3. **No Blender means no room models by default.** `builder` defaults to `blender` (parity-gated) even when the doctor reports the Python builder works. Strangers without Blender get "assets NOT BUILT" until they find the `builder` setting.
4. **numpy is an invisible dependency.** The default Python is Hermes's own; on this Mac it has numpy, but the Hermes manifest only brings numpy with optional extras (`voice`, `wake`). On a Mac without it, static builds, new character bodies and reference packs are off, and the user must find or make a Python with numpy (Hermes64 installs nothing). The doctor now says so; nothing makes it easy.
5. **Long silent steps.** Export 99 s, `hermes plugins validate` 89 s (host), `/hermes64 new` up to 38 s. Tool calls return only at the end, so there is no progress message in any of them.
6. **Enabling the plugin offline means hand-editing YAML.** `hermes plugins enable` needs the network (host `uv` step). Strangers must edit `config.yaml` correctly.
7. **Export templates are a 1.25 GB manual download**, required for the web build, the native app and `hermes64_demo`. The message is clear; the cost is real.
8. **Exported game is hard to find and oddly named.** It lands in `.maker/runs/export-<hex>/share/` and the Mac app is `Adventure Runtime.app` for every game. It is ad-hoc signed, so another Mac's Gatekeeper behaviour is unverified.
9. **Style discoverability and naming.** `/hermes64` help lists only `village|forest|polar` though 15 genre packs exist; n64_v0 is "village" on the card and "forest village" in the hub refusal.
10. **Controls differ between docs.** README: C camera, Enter/Space, R restart; export README.txt: E act, Q/Backspace cancel, hold R retry, Space dodge. QUICKSTART uses the export README's keys.
11. **README quick-start example is stale** (shows `style gate not run`; real cards now show `assets built · style audit ...`) and the README is written for maintainers (jargon, status caveats) rather than first-time users.
12. **Doctor row `proof preview` reads "no" when numpy is missing, even with Godot available** (`doctor.py`, `row(numpy, 'Godot preferred; ...')`). Left alone because windows-lane rewrites the adjacent lines of `doctor.py`.
13. **Next step "run hermes64_build_assets"** on a no-Blender card would fail again unless the user first changes `builder`; the reason text says so, but the next-step list does not.
14. **Test suite assumes a non-`/var` TMPDIR** (item above); developers on a stock Mac see one failure.

## Windows-lane overlap (not resolved here)

Files both lanes touch, different regions (expected to merge cleanly, check at merge): `adventure_maker/service.py` (windows: `encoding='utf-8'` in the theme read; firstrun: doctor routing, `doctor_anywhere`, `refresh_play`), `adventure_maker/newgame.py` (windows: platform check, `command_line`; firstrun: the Blender line), `dashboard/plugin_api.py` (windows: `api_launch`; firstrun: `settings_from_config`/`default_games_settings`), `README.md` (one line). `doctor.py` deliberately untouched (issue 12). `refresh_play` uses only `Path.rename`, `shutil.rmtree` and the existing `prepare_runtime`, so it is not POSIX-specific. The Studio fallback uses Hermes's own `PluginState.data_dir`, which is Windows-safe by design.

## What only a real second computer can prove

- A Mac that truly lacks Godot, Blender or numpy (here they were installed and discovery was stubbed), and the Godot first-open Gatekeeper prompt.
- That `python3` exists (on a Mac without Xcode Command Line Tools, `/usr/bin/python3` opens an install prompt instead of running `check_install.py`).
- The user's own Hermes install: `hermes plugins enable` with network, `hermes plugins validate` through the normal launcher, restart behaviour, and which Python Hermes ships with (numpy or not).
- The Hermes desktop app: Rescan, turning on Hermes64 Studio, the shelf after `/hermes64 new` with blank `projects_root` (only the backend half was exercised here), Settings > Plugins.
- Installing export templates from the `.tpz` through Godot's editor, then exporting.
- Opening the exported `.app` on another Mac (quarantine/Gatekeeper), the web build in a browser.
- Rendering on other GPUs (style audit scores, playtest frame times), an Intel Mac, other macOS versions, a home folder with spaces in its path.
- A model driving the tools from a plain chat request (here every argument was typed by hand).

## Copy-paste test prompt for the owner's MacBook

Paste this into Hermes on the MacBook (after copying `hermes64-firstrun2.zip` or a newer package from `firstrun-lane` into `~/Downloads`):

```text
Help me test the Hermes64 plugin as a first-time user on this Mac. Do not change any other Hermes plugins or settings beyond what these steps say, and do not install anything without asking me first. For each step, show me the exact command, its output (short), how long it took, and mark it pass, fail or confusing. At the end give me a table.

1. Report: macOS version, chip (Apple or Intel), whether /Applications/Godot.app exists and its version (Godot --version), whether `blender` is on PATH, and whether `python3 -c "import numpy"` works. Do not install anything.
2. Install: mkdir -p ~/.hermes/plugins, then unzip ~/Downloads/hermes64-firstrun2.zip -d ~/.hermes/plugins. If a hermes64 folder already exists there, stop and ask me.
3. Run: python3 ~/.hermes/plugins/hermes64/tools/check_install.py (expect a last line starting PASS).
4. Run: hermes plugins validate ~/.hermes/plugins/hermes64 (expect "Validation passed.").
5. Enable: hermes plugins enable hermes64. If it fails, tell me, and only with my OK add plugins.enabled: [hermes64] to ~/.hermes/config.yaml. Then tell me to restart Hermes and wait.
6. After restart: run hermes64_doctor with no arguments and show me its table and guidance lines.
7. Run: /hermes64 new "A lighthouse keeper rescues sailors during a winter storm". Show me the whole card.
8. Run the card's Play: line in Terminal with --headless --quit-after 120 added before -- and show me the BOOT line. Then tell me to run the Play: line myself without those flags and tell you what I see.
9. Run hermes64_check and hermes64_replay on that game.
10. Edit: hermes64_edit with a move-entrance operation on room_a's door "passage" to the east wall, position 2, expected_changed_rooms [room_a]. Confirm the result says play_runtime: refreshed, then ask me to play the Play: line again and confirm the door moved.
11. Export: hermes64_export with targets web and macos. If it refuses for missing export templates, show me the message and stop this step (do not download them unless I say so).
12. Desktop app: tell me how to turn on Hermes64 Studio (Capabilities > Plugins > Rescan, switch on Hermes64 Studio) and ask me whether the lighthouse game appears on the shelf.
Finally: list anything that was slow (over 30 seconds with no message), any error that was hard to understand, and anything that seemed to depend on this Mac.
```
