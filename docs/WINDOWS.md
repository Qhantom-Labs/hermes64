# Hermes64 on Windows

**Status. Windows 11: one real run: runner/exports pass, bundled demo failed on Blender 4.5 (fixed in this candidate), game not played by a human. Not verified.**

The `6af4ba26` receipt records Windows 11 Home, Hermes 0.18.2, runner D9 6/6, and bot/export/headless-boot success on a diagnostic Python-builder project. Default auto selected Blender 4.5.11 LTS and failed on a missing material node tree; C5 clone hashes failed after CRLF conversion, while ZIP hashes passed. Candidate fixes and exact source-only receipts: [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). Rerun the PLATFORMS-2 addendum in [WINDOWS-TEST-SHEET.md](WINDOWS-TEST-SHEET.md). Agent execution with per-command approval is not owner play acceptance; Tested by the owner stays Not yet.

## Install

With Hermes working on the PC, in PowerShell:

```powershell
hermes plugins install Qhantom-Labs/hermes64 --enable
```

Approve numpy and Pillow when Hermes asks. If it says dependency install was skipped, run
`hermes plugins enable hermes64`. Restart Hermes and start a **new** chat, then type `/hermes64 setup`.

Release zip instead (check its SHA-256 against the published one first):

```powershell
$Zip = 'C:\Users\you\Downloads\hermes64-XXXX.zip'
(Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash     # must equal the published SHA-256
$HH = Split-Path -Parent (hermes config path)               # your Hermes home folder
Expand-Archive -LiteralPath $Zip -DestinationPath "$HH\plugins"   # result: $HH\plugins\hermes64\plugin.yaml
py -B "$HH\plugins\hermes64\tools\check_install.py"
hermes plugins enable hermes64
```

The Hermes home on Windows is `%LOCALAPPDATA%\hermes` (Hermes 0.18.2 and newer) unless `HERMES_HOME` points
elsewhere; `hermes config path` prints the config file inside the one in use. Move any older `plugins\hermes64` to a folder outside `plugins` first, or Hermes may load both. A full
checked recipe with backups is in [INSTALL-FOR-YOUR-AGENT.md](INSTALL-FOR-YOUR-AGENT.md).

Python: builds run the Python in the plugin setting `python_path` (or `HERMES64_PYTHON`), else Hermes's own. It needs
numpy (and Pillow for JPEG references) in its own site-packages; children run it with `-I`, so user-site packages do
not count. If a build stops on NumPy, set `python_path` to a `python.exe` that has it, for example a virtual
environment's `Scripts\python.exe`.

## Exact candidate install / locked folders

Hermes 0.18.2 has no plugin-install commit-selection flag. Use a **fresh** `git clone -c core.autocrlf=false https://github.com/Qhantom-Labs/hermes64 C:\H64\candidate`, then `git -C C:\H64\candidate checkout COMMIT_UNDER_TEST`, or a checksum-checked GitHub ZIP. Do not reuse a clone whose bytes were already converted.

For either staged tree, copy its inner plugin folder into the final destination with `robocopy`:

```powershell
$HH = Split-Path -Parent (hermes config path)
$Source = 'C:\H64\candidate'    # or the extracted ZIP's inner hermes64-<commit> folder
robocopy $Source "$HH\plugins\hermes64" /E
if ($LASTEXITCODE -ge 8) { throw 'Plugin copy failed; do not enable it' }
py -B "$HH\plugins\hermes64\tools\check_install.py"
```

First stop Hermes and the gateway **with owner approval** and back up/move any old plugin outside `plugins/`. If Windows says "folder in use", stop the gateway first; do not force repeated overwrites while it is loaded. GitHub archives use a `hermes64-<commit>` top folder; release ZIPs use `hermes64`. Verify the final destination's hashes, enable, then start a new chat. A configured working model is required for chat steps; HTTP 404/model-not-found is a prerequisite failure.

## What works where

| Feature | macOS | Windows | Evidence on the Mac |
|---|---|---|---|
| Plugin loads, registers 27 tools and `/hermes64` | yes | built | `tests/test_merge4_windows_load.py` (simulated win32, POSIX `os` functions removed) |
| `hermes64_doctor`, Windows checklist, `/hermes64 setup` **Child runner** row | yes | built | `python -m adventure_maker.doctor --windows-checklist`; `tests/test_windows_paths.py` |
| `py tools\check_install.py` (package check) | yes | built; names CRLF damage and long paths | `tests/test_windows_paths.py::InstallCheck` |
| Find Godot | `/Applications`, PATH | `HERMES64_GODOT`, the verified fetch cache, `%LOCALAPPDATA%\Programs\Godot`, `Program Files\Godot`, winget, scoop, Downloads, PATH | `tests/test_windows_paths.py::Candidates` |
| Find Blender | Homebrew, `/Applications` | `HERMES64_BLENDER`, `Program Files\Blender Foundation\Blender <v>` (newest first), Steam, scoop, unzipped `blender-<v>-windows-x64` in Downloads/Desktop/home, PATH | `tests/test_windows_lane_fixes.py::BlenderOnWindows` |
| Export templates folder | `~/Library/Application Support/Godot/...` | `%APPDATA%\Godot\export_templates\4.6.2.stable` or `HERMES64_TEMPLATES` | `Templates` tests |
| Godot fetch (`/hermes64 setup --fetch`) | yes | built: pinned SHA-512 Windows x86-64 zip into `%LOCALAPPDATA%\hermes64\` | `tests/test_godotfetch.py` (loopback fixture; no real download anywhere) |
| Make, edit, check, replay, build assets, playtest, export | yes (sandbox-exec) | **opt-in**: `HERMES64_WINDOWS_RUNNER=job` | runner tests with a fake `Popen`/Job/`kernel32` (no Windows process was started) |
| Export target `windows` (.exe + .pck + zip) | yes | built; on Windows the export also boots the .exe headless | builds made on the Mac |
| Export target `web` | yes | built | same exporter |
| Export target `macos` | yes | refused with one sentence (needs codesign) | `Export` tests |
| Studio shelf (Desktop tab) | descriptor reads | checked-path reads; links and reparse points refused | `StudioShelfPathMode` tests |
| Studio web play (127.0.0.1) | yes | built (same code) | none Windows-specific |
| Studio native launch | **PLAY MACOS BUILD** (`open`) | **PLAY WINDOWS BUILD** when the backend runs on Windows (same explicit YES confirm) | `studio/harness/test_shared.mjs`, `test_windows_lane_fixes.py::StudioWindowsLaunch` |
| Play an exported `.exe` on a PC without Hermes | n/a | built | byte checks of exported builds |

## The child sandbox (why authoring on Windows is opt-in)

On macOS every Godot, Blender and Python child runs under `sandbox-exec`: no network, writes only inside the game
project. Windows has no one-line equivalent. With `HERMES64_WINDOWS_RUNNER=job` the plugin runs each child in a
Windows **Job Object**:

- the child is created **suspended**, placed in its job, and only then resumed, so it cannot start anything before
  it is in the job; whatever it starts stays in the job (breakaway is not allowed);
- the child and everything it starts are killed together on timeout, output overflow or the end of the run;
- at most 64 processes and 8 GB for the whole job; crash dialogs suppressed; no console windows;
- private `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `TEMP` inside the project's `.maker\local`; PATH holds only the
  Windows system folders; no ambient secrets or proxies are passed on;
- children are started with an argv list, never a shell string.

What it does **not** do: block the network or confine file writes at the OS level. The children are the official
Godot 4.6.2, your Blender and your Python running the plugin's own scripts, so in practice they write only in the
project, but Windows does not enforce it. Without the variable, every child is refused with
`sandbox_unavailable` and the sentence that says how to opt in, the same fail-closed behaviour as before.
Stronger routes (AppContainer or a restricted token plus a firewall rule, Windows Sandbox, WSL2) are not built.

Turn it on (PowerShell, current user, then restart Hermes):

```powershell
[Environment]::SetEnvironmentVariable("HERMES64_WINDOWS_RUNNER", "job", "User")
```

## Other Windows details

- **Text files**: every runtime read and write is explicit UTF-8, and writes keep LF (`write_bytes`), so files and
  their hashes are identical to the Mac's. Child output is decoded as UTF-8 and CRLF is turned back into LF.
- **Console windows**: runner children and the setup checklist's Python probes start with `CREATE_NO_WINDOW`.
- **Git**: `.gitattributes` (`* -text`) stops `core.autocrlf` from rewriting files on checkout. Unzipping the plugin
  ZIP with Explorer or `Expand-Archive` is the intended route.
- **Long paths**: keep the plugin and projects in short folders (for example `C:\H64`). `check_install` warns when
  the longest installed path reaches 250 characters; every tracked file is under 180 characters relative to the
  plugin (test `RepoFileNames`), with no case clashes, reserved names (`CON`, `AUX`, ...) or characters NTFS refuses.
- **Commands printed for people** use PowerShell form on Windows (`& 'C:\...\godot.exe' --path ...`) and `py` for
  Python.
- **Exported game saves**: `%APPDATA%\Hermes64\<game id>` (Godot custom user folder `Hermes64/<game id>`).
  Godot's own log is in the same folder, `logs\godot.log` (Godot 4 logs to a file by default on desktop).
- **SmartScreen**: the `.exe` is unsigned. Windows may show "Windows protected your PC": click **More info**, then
  **Run anyway**.
- **Graphics**: exported games use Godot's GL Compatibility renderer (OpenGL 3.3 on Windows). Not verified on any
  PC GPU.
- **Skills**: Hermes shows a skill only on the systems its `platforms` field names. The core `hermes64` skill (from
  rc9) and the create, places, generators, hub and audio skills are shown on Windows; `hermes64-author`,
  `-characters`, `-cover`, `-gameplay-modules` and `-playtest-and-ship` still declare macOS only (they contain
  POSIX or repository-only commands), so Hermes does not offer them on Windows. The tools they describe still work.
- **Blender**: supported compatibility targets are 4.2 LTS through 4.5 LTS and 5.x. **5.2.1 verified on Mac; 4.5 LTS fix untested on a real run until the Windows re-run.** The fix enables nodes only when `node_tree` is None; existing 5.x trees are untouched. Non-Mac automatic discovery prefers measured 5.2.1, then compatibility candidates; explicit `blender_path` / `HERMES64_BLENDER` still wins. Doctor prints the version, with a visible WARNING outside the exact tested version or when unreadable. Mac discovery and character-exporter selection stay unchanged. The version compatibility repair covers the static KITS builder. Character Blender export/review helpers are separate and still need 5.2.1; their 4.x compatibility is not claimed. A found Blender that fails is not silently replaced: deliberately select `builder=python` for diagnosis, not default-builder acceptance.

## Grep gate

`python -B -m tools.windows_gate` (repository checkout only: the gate is a developer tool and is not in the plugin
package, see `docs/PACKAGE-CONTENTS.md`) scans the runtime code (`__init__.py`, `adventure_maker`, `adventure_modules`,
`story`, `dashboard`, `tools/check_install.py`) for 15 POSIX/macOS-only patterns (`/tmp`, `/Applications`,
`/usr/bin`, `shell=True`, `os.killpg`, `start_new_session`, `python3` argv, `read_text()` / `write_text(` without
encoding, `text=True` without encoding, `Library/Application Support`, `~/`, POSIX signals, `/dev/null`, POSIX-only
modules). Each remaining hit has an ALLOW row with its reason (all behind a macOS/POSIX branch); stale ALLOW rows
fail the gate. `tests/test_windows_gate.py` plants one known-bad line per rule.

## Inventory (W0): every macOS/POSIX-only spot in the runtime code and what it became

| File | What it gated | Now |
|---|---|---|
| `adventure_maker/runner.py` | `sandbox-exec`, POSIX PATH, `killpg`, `start_new_session`, `/Applications` and `python3` defaults | macOS path unchanged; Windows branch: candidates, `windows_environment`, Job Object `_run_windows` with suspended start, opt-in; Linux branch: bubblewrap ([LINUX.md](LINUX.md)) |
| `adventure_maker/newgame.py` | refused off macOS (`new_platform`) | Windows allowed with the opt-in; refusal says how |
| `adventure_maker/audit.py` | display only on macOS Aqua | Windows: interactive session (`SESSIONNAME`) |
| `adventure_maker/doctor.py` | macOS templates folder; "needs macOS" note | per-platform folder, Windows checklist, honest opt-in note |
| `adventure_maker/export.py` | templates folder; `Godot.app` copy; `codesign`; `X_OK` zip modes | per-platform folder; single-exe self-contained copy on Windows; macOS target refused off Mac; host-independent zip modes; Windows boot smoke on Windows |
| `adventure_maker/nbchars/preview.py`, `select.py` | `/Applications` Godot/Blender | Windows candidates + env overrides |
| `adventure_maker/character_gate.py` | POSIX child env | Windows env branch |
| `adventure_maker/static_preview.py` | POSIX env, `which('godot')` | Windows profile vars, candidates |
| `adventure_maker/studio_catalogue.py` | `O_NOFOLLOW`/`dir_fd` descriptors, refused on Windows | checked-path mode on Windows |
| `dashboard/plugin_api.py`, Studio (`studio/`, `desktop/plugin.js`) | `/usr/bin/open` launch | plus Windows `.exe` launch, offered in the Desktop tab when the backend is Windows |
| `adventure_maker/setup_check.py` | no runner row | **Child runner** row on Windows and Linux; no console window for its probes |
| `adventure_maker/newgame.py`, `hub.py` | `shlex` quoting/splitting | PowerShell quoting; backslash-safe split |
| about 40 runtime modules | `read_text()` / `write_text()` locale + CRLF | explicit UTF-8, LF |

Not changed: the macOS sandbox policy text, simulation and replay code, `runtime/godot/**`, character art, pinned
template hashes, the privacy scanner, the `plugin.yaml` tool list. Developer tools under `tools/` (other than
`check_install.py` and `windows_gate.py`) and `tools/verify_all.sh` remain macOS-only.

## Not verified

The exact candidate's default 4.5 builder and new checkout fix need a real PC rerun. D9 passed six runner checks and D12 passed headless boot on the diagnostic Python-builder project; those do not cover console flash, graphics/audio/save, memory-cap exhaustion, SmartScreen, Studio shelf/PLAY WINDOWS BUILD, or a human playthrough. Chat-model 404 prevented C7/D11/D13 chat rebuilds; use a configured working model first.

## Tested by the owner

Not yet. Record the date, PC alias, Windows version, GPU and the owner's words here only from a receipt
(`docs/receipts/windows/`).
