# Child-process environment audit (catalog review fix)

Every child process the shipped plugin starts now gets an explicit, minimal environment. None inherits Hermes's
environment, so provider keys, tokens, proxies and Hermes flags never reach ffmpeg, Godot, Blender, a system tool or
an exported game. The one exception is the plugin re-running its own `create_flow` command (see "Allow-listed" below).

## One rule, reused

`adventure_maker/runner.py` `Runner.environment()` (lines 115-152) builds the minimal environment for every
`Runner.run` child. Its macOS/Windows mappings are unchanged; the original reviewfix measured macOS output was byte-identical to the submitted version (sha256 of the
JSON-encoded dict for a fixed project: `107e2480…`, 1,074 bytes, on both trees; Windows branch with a fixed parent
mapping: `5561af69…`, 1,374 bytes, on both trees).

Two small helpers reuse it for children started outside `Runner.run` (`runner.py` lines 241-251):

- `child_env(folder)`: `Runner.environment()` with its `.maker/local` folders placed in `folder`.
- `scratch_env()`: `child_env()` in a new temporary folder that is removed when the child has finished.

What a child gets:

- macOS: `HOME`, `TMPDIR`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_DATA_HOME` in the folder;
  `PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`; `LANG` and `LC_ALL` set to `en_US.UTF-8`;
  `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1`; `BLENDER_USER_CONFIG`, `BLENDER_USER_SCRIPTS` and
  `BLENDER_USER_DATAFILES` in the folder.
- Linux: the same project/scratch-local folders and Python/Blender flags; `PATH=/usr/local/bin:/usr/bin:/bin`,
  `LANG=C.UTF-8` and `LC_ALL=C.UTF-8`, through `linux_sandbox.environment()`.
- Windows: `USERPROFILE`, `HOME`, `APPDATA`, `LOCALAPPDATA`, `TEMP` and `TMP` in the folder. `SystemRoot` and `WINDIR`
  come from the parent (default `C:\Windows`). `PATH` is System32, the Windows folder and Wbem only. The child also
  gets `PATHEXT`, `COMSPEC`, `NUMBER_OF_PROCESSORS` and `PROCESSOR_ARCHITECTURE` (from the parent), `PYTHONUTF8`,
  `PYTHONIOENCODING`, the Python flags above and the Blender folders.
- Nothing else from the parent. These are not needed by the sites below: `DISPLAY`, `WAYLAND_DISPLAY` and
  `XDG_RUNTIME_DIR` (no Linux window is opened here), and `PYTHONPATH` (the Python children run `-I` or need none).
  The Godot, Blender, ffmpeg and Python paths are resolved by the parent from the plugin settings or the
  `HERMES64_*` overrides and passed as the program path.

## Sites changed by reviewfix (18 calls in 11 files)

Line numbers are for this version; the submitted version's line is in brackets.

| Site | Child | Environment now |
| --- | --- | --- |
| `adventure_maker/audio_import.py:108` [105] and `:111` [108] | ffmpeg (probe, decode, version) | `scratch_env()` |
| `adventure_maker/godot_fetch.py:292` [240] | the newly fetched Godot, `--version` | `scratch_env()` |
| `adventure_maker/godot_fetch.py:280` [231] | `xattr`, quarantine on the fetched Godot.app | `scratch_env()` |
| `dashboard/plugin_api.py:365` [345] | the exported Windows game (Studio launch) | the game's Runner environment, `child_env(<game>/.maker/local)` |
| `dashboard/plugin_api.py:400` [380] | `/usr/bin/open -n` on the exported .app (Studio launch) | the same |
| `adventure_maker/audit.py:51` [49] | `/bin/launchctl managername` | `scratch_env()` |
| `adventure_maker/create_flow.py:2519` [2517] | `python -I -c 'import numpy'` | `scratch_env()` |
| `adventure_maker/setup_check.py:48` [46] and `:64` [60] | `python -I` numpy and Pillow probes | `scratch_env()`; merged with Windows-only `CREATE_NO_WINDOW` |
| `adventure_maker/scene_capture.py:57` [56] | Godot replay capture (command-line tool) | `scratch_env()` |
| `adventure_maker/nbchars/api.py:248` [246] | Blender, the `blender` character exporter | `scratch_env()` |
| `adventure_maker/nbchars/parity.py:338` [336] | Blender, parity re-export | `scratch_env()` |
| `tools/roomlook.py:104` [102], `:110` [107], `:111` [108] | `/usr/bin/sips` (reference crops) | `scratch_env()` |
| `tools/place_maker.py:54` [52] and `:60` [57] | `cp -cR` (developer bundle copy) | `scratch_env()` |

The Studio backend (`dashboard/plugin_api.py`) is loaded by path, so it loads `adventure_maker/runner.py` by path too
(`_load_runner`, line 343), as it already does for the catalogue scanner.

Measured on macOS 27 with a scratch probe app: `/usr/bin/open -n` passes its own environment to the app it starts.
With the submitted call, a sentinel variable in the parent reached the app. With the fix, the app saw Runner's 13
variables plus the ones launchd adds to every app (`COMMAND_MODE`, `LOGNAME`, `OSLogRateLimit`, `SHELL`,
`SSH_AUTH_SOCK`, `USER`, `XPC_FLAGS`, `XPC_SERVICE_NAME`, `__CFBundleIdentifier`, `__CF_USER_TEXT_ENCODING`), and HOME in
the project folder. A game started from the Studio therefore keeps its saves and settings in the project's
`.maker/local` folders. The same build started from Finder or Explorer uses the player's own folders.

`adventure_maker/nbchars/api.py` is one of the files that fingerprint the character exporter's parity verdict
(`nbchars/select.py`). That verdict was already STALE in the submitted version: recorded `c2ec6e38…`, submitted tree
`be0486eb…`, this tree `3149c5e5…`. So exporter selection is unchanged.

## New platforms children (2 calls)

| Site | Child | Environment |
| --- | --- | --- |
| `adventure_maker/linux_sandbox.py:269` (`_help`) | bwrap `--help`, before the functional probe | `scratch_env()`; temporary home/config/cache/temp folders removed after it exits |
| `adventure_maker/linux_sandbox.py:304` (`probe`) | bwrap functional probe and its isolated Python | `child_env(<writable probe project>/.maker/local)`; every writable environment folder is inside the existing writable bind and removed with the probe tree |

The probe's `env` parameter is host-discovery input only, never the child's environment. The rlimit shim replaces
itself with bwrap/the target via `os.execv`, retaining the explicit Runner environment; it starts no extra inherited-
environment subprocess. Normal Linux authoring and Windows Job Object launches still use the two Runner sites below.
No new Windows spawning site was added by the platforms lane: suspended start/resume changes the existing job
launch, and Studio Windows launch already uses `child_env(<game>/.maker/local)`.

## Other explicit sites (6 calls)

| Site | Child | Environment |
| --- | --- | --- |
| `adventure_maker/runner.py:188` and `:384` | every `Runner.run` child (macOS sandbox, Linux rlimit shim/bwrap or opt-in unconfined mode, Windows suspended/job launch) | `Runner.environment()`, the rule above |
| `adventure_maker/static_preview.py:122` | Godot still capture | `PATH`, `LANG`, `LC_ALL`, `SystemRoot`, `WINDIR` and `PATHEXT` from the parent; HOME, TMPDIR and XDG (Windows: profile and temp) in the capture folder |
| `adventure_maker/nbchars/preview.py:56` | Godot character preview | allow-list of OS basics (`PATH`, `LANG`, `LC_ALL`, `LC_CTYPE`, `TZ`, `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_RUNTIME_DIR`, `SystemRoot`, `WINDIR`, `COMSPEC`, `PATHEXT`, `NUMBER_OF_PROCESSORS`, `PROCESSOR_ARCHITECTURE`, `TMPDIR`, `TEMP`, `TMP`) plus a scratch HOME and profile folders; the display variables are kept for a windowed preview |
| `adventure_maker/character_gate.py:99` | the plugin's own rig validator (`python -m adventure_maker.rigkit`), command-line fallback used only when the rig kit cannot be imported in-process (the package ships it, so the in-process path runs) | macOS/Linux: `PATH=/usr/bin:/bin`, `LANG=C.UTF-8`, `PYTHONDONTWRITEBYTECODE`, plus `HOME` and `TMPDIR` from the parent. Windows: `SystemRoot`, `WINDIR`, `TEMP`, `TMP`, `USERPROFILE`, `APPDATA` and `LOCALAPPDATA` from the parent, plus a System32 `PATH`. The real home folder is kept so that numpy installed in the user's site-packages stays importable (this child runs without `-I`); Windows-only `CREATE_NO_WINDOW` is retained |
| `refpack/tool.py:44` | the refpack worker (`python worker.py`) | `PATH` and `HOME` from the parent, `TMPDIR` set to the work folder, `LANG`/`LC_ALL=C`, `PYTHONDONTWRITEBYTECODE`; HOME kept for the same site-packages reason |

None of these passes a credential. They were left as they are to keep this change small.

## Allow-listed (1 call)

| Site | Child | Environment and reason |
| --- | --- | --- |
| `adventure_maker/create_flow.py:2661` (`rerun_env`, line 2649) | the same `create_flow` command, re-run once under the configured numpy Python when the starting Python has no numpy | the parent environment plus `HERMES64_CREATE_RERUN=1` and the plugin root on `PYTHONPATH`. The child is the plugin's own code with the same arguments, not a third-party program. It needs `HERMES_HOME` and the `HERMES64_*` settings, and every tool it starts goes through Runner. |

## Through Runner (no direct child)

`adventure_maker/adapters.py` (story, asset build, replay and open children), `doctor.py`, `export.py` (Godot export,
version check, `codesign`), `newgame.py` (numpy probe), `gen_tools.py` and `character_tools.py` call
`Runner(project).run`, so they get `Runner.environment()`.

## Nothing else starts a child

Outside the rlimit shim's replacement `os.execv` described above, the shipped Python has no `os.system`, `os.popen`, `os.exec*`, `os.spawn*`, `pty`, `asyncio` subprocesses,
`webbrowser` or `multiprocessing`. The GDScript runtime has no `OS.execute`, `OS.create_process` or `OS.shell_open`.
The Studio's JavaScript runs in the desktop app and starts no process.

## Checks

- Repository tests (not shipped in the plugin): `tests/test_reviewfix_childenv.py`. Sentinel provider-key variables
  (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `HERMES_SECRET_SENTINEL`) are set in the parent. Each changed
  site runs a fake child that writes its environment to a file. The test checks that no sentinel arrives and that
  only Runner's variables do. A control case runs the same child without `env=` and must see every sentinel. On the
  submitted tree all nine site tests fail with the sentinels found. A static scan of every shipped `.py` fails on a
  `subprocess` call without `env=`, with `env=None` or `os.environ`, or on a whole-environment copy outside the
  allow-list above. It also requires each file that starts a child to be listed here.
- Windows was not run. The Windows branch is the existing `windows_environment()`, checked by unit test with
  sentinels in the parent mapping.
- Platforms merge regression tests: `tests.test_linux_platform.ProbeEnvironment` runs real POSIX stand-in children
  for bwrap help and the probe, with parent sentinels and the Linux platform decision simulated. They require the
  exact Runner mapping (not just missing keys), local writable folders and cleanup. Before the repair, help leaked
  a sentinel and the probe lacked ten Runner variables. These are macOS simulation/child-environment checks, not
  native Linux or Windows receipts. Real platform status remains unverified.
