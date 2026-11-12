# Platform parity: macOS, Windows and Linux

**Answer.** Every plugin feature has a macOS, a Windows and a Linux path. **macOS is verified** on the development
Mac. **Windows 11 is built and simulated, not verified**: the only real-PC reports are two owner-relayed prose
summaries about older packages (windows-lane `cd15b620` and Mac-exported games), with no receipt. **Linux authoring
is implemented behind bubblewrap and not verified**: no Linux computer has run it. What each claim rests on:
[PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). The real tests: [WINDOWS-TEST-SHEET.md](WINDOWS-TEST-SHEET.md) and
[LINUX-TEST-SHEET.md](LINUX-TEST-SHEET.md). A row changes to "verified" only from a receipt under `docs/receipts/`.

"Tested here" = tests and probes on the Mac. "Real machine" = what a real Windows PC or Linux computer showed.

## Feature table

| Feature | Windows path | Linux path | macOS path | Tested here | Real machine | Gaps |
|---|---|---|---|---|---|---|
| Install / load in Hermes | `hermes plugins install Qhantom-Labs/hermes64 --enable`, or the zip with `Expand-Archive`; `host_compat` adapter for Hermes 0.18.2-0.20.0 | same `owner/repo` install (a bare catalog-name install follows the catalog entry's platform list, set outside this repository) | same; native host API on 0.20.1+ | `test_merge4_windows_load` (win32, POSIX `os` removed), `test_host_compat`, `test_registration` | Windows: relayed, older package, after a local fix that was never received; no receipt. Linux: none | the 0.18.2 adapter is unproven on a real PC |
| `check_install` (package check) | `py tools\check_install.py`; names CRLF damage and paths >= 250 chars | `python3 tools/check_install.py` | same | `test_windows_paths::InstallCheck`, `test_package` | Windows: relayed number for an older package; no receipt | none known |
| Doctor / setup checklist | `--windows-checklist`; setup **Child runner** row | `--linux-checklist` (Python, numpy, runner, Godot, Pillow, templates, Blender, ffmpeg, disk); setup **Child runner** row | `~/Library/Application Support/Godot/...`; no runner row | `test_windows_paths`, `test_linux_platform::ChecklistAndMessages` | none with a receipt | none known |
| Find Godot / Blender / Python | `HERMES64_*` env, the fetch cache, `%LOCALAPPDATA%\Programs\Godot`, Program Files, winget, scoop, Steam (Blender), portable Blender zips, Downloads, PATH | `HERMES64_*` env, official 4.6.2 file names in `/usr/local/bin`, `/usr/bin`, `/opt`, `~/.local/bin`, `~/bin`, `~/Applications`, `~/Downloads`; Blender tarball folders; snap/flatpak detected and skipped | `/Applications`, Homebrew, PATH, Hermes's own Python | `test_windows_paths::Candidates`, `test_windows_lane_fixes::BlenderOnWindows`, `test_linux_platform::Discovery` | Windows: relayed "Blender failed" (older package defaulting to `builder=blender`; error text never sent) | Linux discovery and snap/flatpak handling unproven |
| `/hermes64 new`, create, edit, build, playtest | runner with a Job Object (opt-in `HERMES64_WINDOWS_RUNNER=job`) | runner inside bubblewrap (default; fail closed), or unconfined by opt-in | runner under `sandbox-exec` | `test_platform_parity::WindowsRunnerEndToEnd`, `test_linux_platform::LinuxRunnerEndToEnd` (real local child, fake bwrap) | Windows: relayed for an older package; no receipt. Linux: none | both need the real sheets |
| Export `windows` | `.exe` + `.pck` + zip; on Windows also boots the `.exe` headless | cross-export as from a Mac | cross-export | `test_windows_paths::Export` | Windows: relayed boot/FPS for Mac-made builds; no receipt | Linux cross-export unproven |
| Export `web` | same exporter | same exporter; the preset names the hash-checked template copy inside the project (bwrap hides `$HOME`) | same; Studio 127.0.0.1 server | exporter tests, `test_linux_platform::Refusals` | none with a receipt | browser play unverified for these builds |
| Export `macos` | refused with one sentence (needs codesign) | refused with the same sentence | `.app` | `test_windows_paths::Export`, `test_linux_platform::Refusals` | n/a (by design) | not fixable without Apple tooling |
| Native Linux export | n/a | **not supported yet** (no Linux template pinned or kept) | n/a | `test_linux_platform` | n/a | needs a pinned Linux template |
| Studio (Desktop tab, dashboard API) | shelf in checked-path mode; web play on 127.0.0.1; **PLAY WINDOWS BUILD** when the backend is Windows | same code as macOS | descriptor reads; **PLAY MACOS BUILD** (`open`) | `StudioShelfPathMode`, `test_native_launch_target_windows`, `studio/harness/test_shared.mjs`, `test_windows_lane_fixes::StudioWindowsLaunch` | none | the shelf refuses every reparse point (OneDrive placeholders may be hidden) |
| Audio import (ffmpeg) | `CREATE_NO_WINDOW`; `ffmpeg.exe` via setting/PATH/Program Files | PATH / common folders | Homebrew / PATH | audio tests | none | ffmpeg runs outside the runner on every OS |
| Godot + templates fetch | pinned SHA-512 Windows zip into `%LOCALAPPDATA%\hermes64\` | **refused**: no Linux archive SHA-512 is pinned (docs say how a maintainer adds one) | universal zip into `~/Library/Caches/hermes64/`, quarantine handling | `test_godotfetch` (loopback fixture), `test_linux_platform::FetchPins` | none (no real download anywhere) | a real fetch on every OS |
| Packaging | same package; `.gitattributes * -text`; NTFS-safe names | same package | same | `test_package`, `test_windows_paths::RepoFileNames`, `test_platform_parity::LongPathsAndText` | Windows: relayed install of an older package | deep install roots can pass MAX_PATH; `check_install` warns |
| Runner / sandbox | Job Object: suspended start then assign, kill-on-close tree, 64 processes, 8 GB, private profile folders, system-only PATH, CRLF normalised; **no network block, no write confinement**; refused without opt-in | bubblewrap: new namespaces, no network, read-only system, home hidden, project the only writable folder, rlimits, PID-namespace tree kill; functional probe; refused without a working bwrap; `unconfined` opt-in = rlimits + process-group kill only | `sandbox-exec`: no network, writes only in the project; process-group kill | `test_platform_parity`, `test_windows_lane_fixes::SuspendedStart`, `test_linux_platform` | none with a receipt | macOS and the Linux unconfined mode: a grandchild that starts its own session survives the process-group kill |
| Children outside the runner | `character_gate` (CLI fallback only), `static_preview`, `nbchars/preview`, ffmpeg run `subprocess.run` directly (argv lists) | same | same, also without `sandbox-exec` | `test_platform_parity::SubprocessQuotingInSource` | none | not sandboxed on any OS; on Windows they run even without the opt-in; `nbchars/preview` passes the full environment |
| Exported game runtime | GL Compatibility (OpenGL 3.3); saves `%APPDATA%\Hermes64\<id>` | no native Linux build; web builds run in a browser | `~/Library/Application Support/Hermes64/<id>` | byte checks | Windows: relayed boot/FPS and play checks for older Mac-made builds; save fix not re-run | web play on Linux unverified |

## The runner off macOS

- **Windows** without `HERMES64_WINDOWS_RUNNER=job`: every child is refused (`sandbox_unavailable`) with the sentence
  that says how to opt in. With it, children run in the Job Object above; the child is created suspended, put in
  the job, then resumed (closed in rc9: before, a grandchild started in the gap between start and assignment could
  escape the kill).
- **Linux**: [LINUX-RUNNER-DESIGN.md](LINUX-RUNNER-DESIGN.md). Without a bwrap that passes the probe, every child is
  refused with the cause (missing bwrap, Ubuntu AppArmor, userns sysctls, container, WSL 1) and the fix; the owner
  may opt in to `HERMES64_LINUX_RUNNER=unconfined` (no OS-enforced network or write confinement; process-group kill
  and rlimits only), disclosed in doctor, setup, the `/hermes64 new` reply and every run result.
- **Other systems**: refused.

## Same rule on every OS (safety.py)

`adventure_maker/safety.py`, so a project made on one OS opens on another:
- `relative()` refuses NTFS-reserved device names (`con`, `nul`, `aux.txt`, `com1`-`com9`, `lpt1`-`lpt9`), a trailing
  dot or space and `<>"|?*`, plus `\`, `:`, drive letters, UNC and traversal.
- `inspect_path()` refuses directory junctions and symlinks reported as reparse points (`st_reparse_tag`
  name-surrogate bit); OneDrive/cloud placeholders are not name-surrogates and stay allowed. No effect on macOS or
  Linux (`st_reparse_tag` absent).

## Simulation tests

Each has a known-bad control next to it.

| File | What runs |
|---|---|
| `tests/test_platform_parity.py` | win32 runner end to end with a fake `Popen`/Job and POSIX `os` functions removed; subprocess quoting round trips; no-sandbox refusals; CRLF; drive letters and backslashes; case-insensitive and reserved names; long paths; hard-coded `/`; no shell in source |
| `tests/test_windows_lane_fixes.py` | suspended start against a fake `kernel32` (assign before resume, only the child's thread, every failure kills the child), THREADENTRY32 layout, CREATE_SUSPENDED in `Popen`, Blender candidates and newest-first order, the Studio Windows flag, no console window for setup and character-gate probes |
| `tests/test_linux_platform.py` | bwrap argv (namespaces, read-only system, minimal `/etc`, merged-usr symlinks, tool binds, project the only writable path, home hidden, argv untouched); the rlimit shim really lowering limits; probe parsing and every named cause; fail closed, exact-value opt-in, bwrap winning; the real POSIX run loop through bwrap/unconfined command lines (timeout, output cap, scrubbed env, isolation tag); macOS argv and environment unchanged; discovery with snap/flatpak; the missing Linux pin; checklist text; refusals |
| `studio/harness/test_shared.mjs` | the Studio reducer: PLAY WINDOWS BUILD only on a Windows backend, the same explicit YES confirm, macOS entry unchanged |

## Parity patches

The patches in [parity-patches/](parity-patches/) for other lanes are already contained in this tree:
`audio_import.py` passes `CREATE_NO_WINDOW` on Windows and the locomotion spec is read as UTF-8 (both
`audiopipe-ffmpeg-no-window.patch` and `chars-locomotion-utf8.patch` pass `git apply --check -R`, so they are
applied); `rc3-windows-runner.patch` is history for the rc3 integrator. The Studio Windows launch button this page
once listed as missing is in rc9.

## NOT verified

- Everything above on a real Windows PC or Linux computer for this release.
- That an earlier PC run had `HERMES64_WINDOWS_RUNNER=job` set (inferred from children running).
- Job Object behaviour on a real PC (suspended start, tree kill, memory cap); bubblewrap behaviour on any real
  distribution; audio import, the Godot fetch, Studio and web builds in a browser on Windows or Linux.
