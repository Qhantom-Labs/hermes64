# Platform parity: Windows and macOS

Rule (the owner, 2026-11-10): every plugin feature has a Windows path and a macOS path. macOS is verified on this Mac;
Windows is verified only by the owner's PC (the "WINDOWS TEST REPORT" entry in `PUBLISH-DECISIONS.md`, Win11 25H2,
Hermes Agent 0.18.2, plugin package from windows-lane cd15b620 in `play-win/`). Anything else is **built, not
verified on Windows**. Lane model: `docs/PARITY-MODEL.md` (development repository only; not in the package).

"Real Windows" = yes only when that report says the step ran and passed. "Here" = tests and probes on this Mac.

## Feature table

| Feature | Windows path | macOS path | How it is tested here | Verified on real Windows | Gaps |
|---|---|---|---|---|---|
| Install / load in Hermes | Unzip `hermes64-plugin.zip` (Explorer / `Expand-Archive`), point Hermes at it; `host_compat` adapter for Hermes 0.18.2-0.20.0 | Same package; native host API on 0.20.1+ | `test_merge4_windows_load` (win32, POSIX `os` removed), `test_host_compat` (stub 0.18.2 ctx), `test_registration` | **yes**, but only after a local compat fix on 0.18.2 (diff not received) | WIN2's adapter is untested on a real 0.18.2; HOST-COMPAT adopt slot still open |
| `check_install` (package check) | `py tools\check_install.py`; names CRLF damage and paths >= 250 chars | `python3 tools/check_install.py` | `test_windows_paths::InstallCheck`, `test_package` | **yes** (4962/4962) | none known |
| Doctor | `hermes64_doctor`; `--windows-checklist`; `%APPDATA%\Godot\export_templates\4.6.2.stable` | `~/Library/Application Support/Godot/...` | `test_windows_paths::Templates/Messages`, `test_platform_parity::WindowsFacingStrings` | **yes** (checklist READY) | none known |
| Find Godot / Blender / Python | `platforms.candidates`: `HERMES64_*` env, `%LOCALAPPDATA%\Programs\Godot`, Program Files, winget, scoop, Downloads, PATH | `/Applications/Godot.app`, Homebrew, PATH, Hermes's own Python | `test_windows_paths::Candidates`, `test_platform_parity` (no POSIX path leaks) | **yes** for Godot and Python (games were built); Blender **failed** | Blender failure cause unknown (missing vs crash); zerosetup `auto` covers only missing |
| `/hermes64 new` | Runner with Job Object (opt-in `HERMES64_WINDOWS_RUNNER=job`) | Runner under `sandbox-exec` | `test_windows_paths::Messages`, `test_platform_parity::WindowsRunnerEndToEnd` (fake Popen/Job) | **yes** (fox game) | needs the opt-in on Windows (see Runner) |
| Build assets (static kits, characters) | Python builder (Blender optional) through the runner | Blender default on rc3 (zerosetup makes `auto`), Python builder | NOBLENDER parity 249/276 strict (Mac), `test_platform_parity` | **yes** with the Python builder; Blender **no** | Python-vs-Blender strict parity 249/276 (NOBLENDER-PARITY.md) applies on both OSes |
| Playtest (headless bot) | Godot headless via runner | same | runner tests (structure), Mac playtests | **yes** (2 bot playtests) | none known |
| Export `windows` | `.exe` + `.pck` + zip; on Windows also boots the `.exe` headless | Builds the Windows target too (cross-export) | `tools/windows_export_check.py` byte checks, `test_windows_paths::Export` | **yes** (export + boot check; Thaw, relay_combat, reedland_mixed, puzzle_hall boot, 59-60 FPS) | audio, save/load, dodge, push/pull unverified (sheet v2) |
| Export `web` | same exporter; play via `py -m http.server` | same; Studio 127.0.0.1 server | exporter tests | exported **yes**; played in a browser **no** | browser play unverified on both OSes for these builds |
| Export `macos` | **refused** with one sentence (needs codesign) | `.app` | `test_windows_paths::Export` | n/a (by design) | Windows users cannot make Mac builds; documented, not fixable without Apple tooling |
| Studio (Desktop tab, dashboard API) | `dashboard/plugin_api.py`; shelf in checked-path mode (links, reparse points refused); web play on 127.0.0.1; native launch backend accepts `windows` | descriptor reads; `open` for `.app` | `test_windows_paths::StudioShelfPathMode`, `test_native_launch_target_windows` | **no** | `desktop/plugin.js` has no Windows launch button (studio owner); the shelf refuses **every** reparse point, so games inside OneDrive-placeholder folders may be hidden; dashboard on 0.18.2 unexercised |
| Audio import (ffmpeg) | audiopipe-lane `audio_import.py` (not in this branch): argv list, `ffmpeg.exe` via PATH/`ProgramFiles\ffmpeg`/bundled | Homebrew/PATH ffmpeg | audiopipe tests (in its worktree) | **no** | Not merged here. ffmpeg runs outside the runner on both OSes (no sandbox, no Job). Console window per call on Windows: patch [parity-patches/audiopipe-ffmpeg-no-window.patch](parity-patches/audiopipe-ffmpeg-no-window.patch) |
| Locomotion bake (shared run cycle) | chars lane `adventure_maker/locomotion/` (untracked in `wt-chars3`, not in this branch); pure Python | same | chars lane | **no** | `p.read_text()` without encoding (cp1252 on Windows): patch [parity-patches/chars-locomotion-utf8.patch](parity-patches/chars-locomotion-utf8.patch) |
| Godot + templates fetch (setup) | godotfetch-lane `godot_fetch.py`: pinned SHA-512 Windows x86-64 ZIP, cache `%LOCALAPPDATA%\hermes64\` | macOS universal ZIP, `~/Library/Caches/hermes64/`, quarantine handling | godotfetch tests (simulated Windows layout) | **no** | Not merged here; needs `docs/GODOTFETCH-WINDOWS-FINDER.patch` (godotfetch's) when composed with this branch's `platforms.py`; network fetch needs the owner's yes |
| Packaging (`tools/package.py`) | Same package for both; `.gitattributes * -text`; file names NTFS-safe (<180 chars, no case clash, no reserved names) | same | `test_package`, `test_windows_paths::RepoFileNames`, `test_platform_parity::LongPathsAndText` | **yes** (package installed); `tools/windows_gate` was missing and is now repo-only by rule (WIN2) | deep install roots (OneDrive Documents) can still pass MAX_PATH; `check_install` warns, does not fix |
| Runner / sandbox | Job Object: kill-on-close tree, 64 processes, 8 GB, private profile folders, system-only PATH, CRLF normalised; **no network block, no write confinement**; refused without opt-in | `sandbox-exec`: no network, writes only in the project | `test_windows_paths::Runner`, `test_platform_parity::WindowsRunnerEndToEnd/NoSandboxFailsClosed` | **yes, inferred**: new/playtest/export ran, which needs the runner; the report does not quote the env var | Weaker than macOS by design. Child starts before it is assigned to the job (no `CREATE_SUSPENDED`): a grandchild started in that window escapes the kill. Untestable here; not changed |
| Children outside the runner | `character_gate`, `static_preview`, `nbchars/preview`, audio ffmpeg call `subprocess.run` directly (argv lists, scrubbed or private env except `nbchars/preview`) | same, also **without** `sandbox-exec` | `test_platform_parity::SubprocessQuotingInSource` (no shell anywhere) | partly (character gate runs during builds) | Same on both OSes: not sandboxed, and on Windows they run even without the opt-in. `nbchars/preview` passes full `os.environ` (catalog audit F9) |
| Service / tool orchestration | `service.py` + `safety.Project`: project files via `relative()`/`inspect_path()` | same | `test_platform_parity::DriveLettersAndBackslashes/WindowsNames` | indirectly (tools ran) | **fixed here**: see below |
| Hub / catalog | pure Python, explicit UTF-8 | same | `test_catalog`, hub tests | no | none known |
| Exported game runtime | GL Compatibility (OpenGL 3.3), saves `%APPDATA%\Hermes64\<id>` | Metal/GL, `~/Library/Application Support/Hermes64/<id>` | byte checks | **yes** for boot/FPS; saves, audio, input steps **no** | sheet v2 items open; pre-SAVEFIX builds shared `Adventure Runtime` (wrong Godot key), fixed + legacy adoption in [SAVES.md](SAVES.md), Windows re-run pending |

## The runner off macOS (catalog audit F7): exactly what happens on Windows today

- **rc3-lane (add451d8) and main (32a8ca48)** do **not** contain windows-lane (`git merge-base --is-ancestor windows-lane rc3-lane` = no; no `platforms.py`, no `host_compat.py`). On Windows: the plugin loads; on Hermes 0.18.2 every tool call fails with `AttributeError` (`ctx.get_config`); on 0.20.1+ `locate()` checks only the macOS defaults then PATH (`godot not found; configure godot_path. Checked /Applications/Godot.app/...`); and any child is refused by `Runner.sandbox_argv` with `sandbox_unavailable: Required no-network/write-confinement sandbox unavailable on this host; no child started`, whatever env var is set. So `new`, build, playtest and export cannot run. Source: `git show rc3-lane:adventure_maker/runner.py`, `Runner.sandbox_argv` (`if sys.platform != 'darwin' ...`).
- **windows-lane / win2-lane (this branch)**: without `HERMES64_WINDOWS_RUNNER=job` the same refusal, plus the sentence telling the owner how to opt in. With it, children run in the Job Object above. This is the code the owner's PC ran (package cd15b620 contains it; sheet v1 step 4 sets the variable) and new/playtest/export passed.
- **Fix for the integrator**: merge win2-lane (runner, platforms, host_compat, safety). If only the runner is wanted on rc3, [parity-patches/rc3-windows-runner.patch](parity-patches/rc3-windows-runner.patch) (`runner.py` + new `platforms.py`, from windows-lane) applies cleanly to rc3-lane (`git apply --check` OK); probed on an rc3 archive with simulated win32: refuses without opt-in, passes argv unchanged with it. The catalog `platforms` field is truthful only at a SHA that contains it.

## Fixed in this lane (files this branch owns)

`adventure_maker/safety.py`, same rule on both OSes so a project made on a Mac opens on Windows:
- `relative()` refuses NTFS-reserved device names (`con`, `nul`, `aux.txt`, `com1`-`com9`, `lpt1`-`lpt9`), a trailing
  dot or space (`foo.` aliases `foo` on NTFS) and `<>"|?*`. Already refused before: `\`, `:`, drive letters, UNC,
  traversal.
- `inspect_path()` refuses directory junctions and symlinks reported as reparse points (`st_reparse_tag` name-surrogate
  bit, which Windows `lstat` sets while reporting a plain directory); OneDrive/cloud placeholders are not
  name-surrogates and stay allowed. No effect on macOS (`st_reparse_tag` absent).

## Simulation tests

`tests/test_platform_parity.py` (18 tests; green on venv Python 3.11 and system Python 3.9). Each check has a
known-bad control next to it:

| Area | What runs | Known-bad control |
|---|---|---|
| Runner end to end on win32 | real `Project`, `Runner.run` with fake `Popen`/Job, `os.killpg`/`setsid`/`set_blocking`/`SIGKILL` removed: argv unchanged (spaces, quotes, `&`, `%`, `^`, `|`, trailing `\`, empty), `shell=False`, no `start_new_session`, `CREATE_NO_WINDOW`, Windows PATH, job assigned and closed | the macOS branch with the same POSIX functions removed raises `AttributeError` (POSIX-only call) |
| Subprocess quoting | `list2cmdline` of hostile argv parsed back with CommandLineToArgvW rules = argv | a `' '.join(argv)` shell-style string does not round-trip; a string argv is refused before any launch |
| No sandbox | win32 without opt-in, darwin without `/usr/bin/sandbox-exec`, linux: `sandbox_unavailable`, no Popen | only the exact `job` value opts in (existing test) |
| CRLF | child CRLF output becomes LF; CRLF JSON reads; project writes are LF | a raw decode keeps `\r`; a Windows text-mode writer emits CRLF |
| Drive letters, backslashes | `relative()` refuses `C:\`, `C:x`, `..\x`, UNC, `a\..\..\x`, ADS; PowerShell quoting; `split_args` keeps `\` | a `/`-only split keeps `a\..\..\x` whole and `ntpath` resolves it outside the project; POSIX `shlex` eats backslashes |
| Case-insensitive / reserved names | `Fox`/`FOX` project names refused (would alias `fox`); reserved names refused; junction tags refused, cloud tag allowed | casefold equality shows the collision a case-sensitive check misses |
| Long paths | short root fits MAX_PATH; checklist names long paths | a OneDrive Documents root + 180-char file reaches 260 |
| Hard-coded `/` | every Windows-facing candidate, templates folder, profile folder and command line has no `/` or POSIX location | planted `/Applications/...` and `str(home) + '/AppData'` are caught |
| No shell in source | AST scan of runtime code: no `shell=` other than `False`, no `os.system`/`os.popen` | four planted shell calls are caught |

## Patches for other owners (not applied here)

- [parity-patches/rc3-windows-runner.patch](parity-patches/rc3-windows-runner.patch): integrator, F7 (above).
- [parity-patches/audiopipe-ffmpeg-no-window.patch](parity-patches/audiopipe-ffmpeg-no-window.patch): audiopipe,
  `CREATE_NO_WINDOW` for ffmpeg on Windows (`git apply --check` OK in `wt-audiopipe`).
- [parity-patches/chars-locomotion-utf8.patch](parity-patches/chars-locomotion-utf8.patch): chars lane, explicit
  UTF-8 read of the locomotion spec (applies to the untracked file in `wt-chars3`).
- Studio (no patch, design choice for the owner): a Windows launch button in `desktop/plugin.js`; consider
  allowing non-name-surrogate reparse points (OneDrive) in `studio_catalogue._REPARSE` the way `safety` now does.
- godotfetch: its own `docs/GODOTFETCH-WINDOWS-FINDER.patch` when composed with this branch.

## NOT verified

- Everything in the table marked "no", and every Windows behaviour of this lane's `safety.py` change (simulated only;
  `st_reparse_tag` on a real junction was not observed).
- That the owner's PC had `HERMES64_WINDOWS_RUNNER=job` set (inferred from children running).
- Job Object behaviour on a real PC (process-tree kill, memory cap); audio import, locomotion bake and Godot fetch on
  Windows; Studio on Windows; web builds in a browser.
