# Hermes64 on Windows

**Status: built, untested on Windows.** All Windows behaviour below was built and checked on a Mac by simulation
(patched `sys.platform`/`os.name`, `PureWindowsPath`/`ntpath` path tests, a grep gate, removed POSIX `os`
functions). Nothing here has run on a Windows PC yet. Dylan's run of [WINDOWS-TEST-SHEET.md](WINDOWS-TEST-SHEET.md)
is the first real test; results go under "Tested by the owner" at the end.

## What works where

| Feature | macOS | Windows (this lane) | Evidence on the Mac |
|---|---|---|---|
| Plugin loads, registers 27 tools and `/hermes64` | yes | built | `tests/test_merge4_windows_load.py` (simulated win32, POSIX `os` functions removed) |
| `hermes64_doctor`, Windows checklist | yes | built | `python -m adventure_maker.doctor --windows-checklist`; `tests/test_windows_paths.py` |
| `py tools\check_install.py` (package check) | yes | built; names CRLF damage and long paths | `tests/test_windows_paths.py::InstallCheck` |
| Find Godot, Blender, Python | `/Applications`, PATH | `%LOCALAPPDATA%\Programs\Godot`, `Program Files\Godot`, winget, scoop, Downloads, PATH, `HERMES64_GODOT` | `tests/test_windows_paths.py::Candidates` |
| Export templates folder | `~/Library/Application Support/Godot/...` | `%APPDATA%\Godot\export_templates\4.6.2.stable` or `HERMES64_TEMPLATES` | `Templates` tests |
| Make, edit, check, replay, build assets, playtest, export | yes (sandbox-exec) | **opt-in**: `HERMES64_WINDOWS_RUNNER=job` | runner tests (structure only; no Windows process was started) |
| Export target `windows` (.exe + .pck + zip) | yes | built; on Windows the export also boots the .exe headless | `play-win/` builds made on the Mac |
| Export target `web` | yes | built | same exporter |
| Export target `macos` | yes | refused with one sentence (needs codesign) | `Export` tests |
| Studio shelf (Desktop tab) | descriptor reads | checked-path reads; links and reparse points refused | `StudioShelfPathMode` tests |
| Studio web play (127.0.0.1) | yes | built (same code) | none Windows-specific |
| Studio native launch | `.app` via `open` | backend accepts target `windows`; the Desktop tab still only offers the macOS button | `test_native_launch_target_windows` |
| Play an exported `.exe` on a PC without Hermes | n/a | built | `evidence/windows/export.json` byte checks |

## The child sandbox (why authoring on Windows is opt-in)

On macOS every Godot, Blender and Python child runs under `sandbox-exec`: no network, writes only inside the game
project. Windows has no one-line equivalent. With `HERMES64_WINDOWS_RUNNER=job` the plugin runs each child in a
Windows **Job Object**:

- the child and everything it starts are killed together on timeout, output overflow or the end of the run;
- at most 64 processes and 8 GB for the whole job; crash dialogs suppressed;
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
- **Git**: `.gitattributes` (`* -text`) stops `core.autocrlf` from rewriting files on checkout. Unzipping the plugin
  ZIP with Explorer or `Expand-Archive` is the tested route.
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
| `adventure_maker/runner.py` | `sandbox-exec`, POSIX PATH, `killpg`, `start_new_session`, `/Applications` and `python3` defaults | macOS path unchanged; Windows branch: candidates, `windows_environment`, Job Object `_run_windows`, opt-in |
| `adventure_maker/newgame.py` | refused off macOS (`new_platform`) | Windows allowed with the opt-in; refusal says how |
| `adventure_maker/audit.py` | display only on macOS Aqua | Windows: interactive session (`SESSIONNAME`) |
| `adventure_maker/doctor.py` | macOS templates folder; "needs macOS" note | per-platform folder, Windows checklist, honest opt-in note |
| `adventure_maker/export.py` | templates folder; `Godot.app` copy; `codesign`; `X_OK` zip modes | per-platform folder; single-exe self-contained copy on Windows; macOS target refused off Mac; host-independent zip modes; Windows boot smoke on Windows |
| `adventure_maker/nbchars/preview.py`, `select.py` | `/Applications` Godot/Blender | Windows candidates + env overrides |
| `adventure_maker/character_gate.py` | POSIX child env | Windows env branch |
| `adventure_maker/static_preview.py` | POSIX env, `which('godot')` | Windows profile vars, candidates |
| `adventure_maker/studio_catalogue.py` | `O_NOFOLLOW`/`dir_fd` descriptors, refused on Windows | checked-path mode on Windows |
| `dashboard/plugin_api.py` | `/usr/bin/open` launch | plus Windows `.exe` launch (backend) |
| `adventure_maker/newgame.py`, `hub.py` | `shlex` quoting/splitting | PowerShell quoting; backslash-safe split |
| about 40 runtime modules | `read_text()` / `write_text()` locale + CRLF | explicit UTF-8, LF |

Not changed: the macOS sandbox policy text, simulation and replay code, `runtime/godot/**`, character art, pinned
template hashes, the privacy scanner, the `plugin.yaml` tool list. Developer tools under `tools/` (other than
`check_install.py` and `windows_gate.py`) and `tools/verify_all.sh` remain macOS-only.

## Not verified

Everything in the table above on a real Windows PC, in particular: the Job Object runner starting Godot, Blender and
Python; Godot's stdout through pipes; the exported `.exe` starting, rendering, playing sound and saving; GPU drivers;
SmartScreen wording; winget/scoop install folders; long-path behaviour; Hermes on Windows loading the plugin;
the Studio shelf on NTFS.

## Tested by the owner

Not yet. Record the date, PC, Windows version, GPU and Dylan's words here after the test sheet.
