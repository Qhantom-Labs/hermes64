# Hermes64 external dependency inventory (ZEROSETUP lane)

Measured on this Mac (macOS 27, Apple M4 Pro) on 2026-11-10 with `du -sh`, `stat` and `unzip -l`. Licences are read
from files on disk; anything not on disk is marked **unknown**. Nothing was downloaded to make this table.

## Summary

| Dependency | Required? | Why | What breaks without it | Size on disk (measured) | Licence (file on disk) |
|---|---|---|---|---|---|
| Hermes Agent + its Python (3.9+) | yes | hosts the plugin; tools run in-process | everything | not measured (host) | host's own |
| Hermes64 plugin | yes | the product | everything | zip **44.3 MB** (44,292,797 B, 4,960 files); unpacked **121 MB** (kits 84 MB, audio 16 MB, characters 6.1 MB) | MIT (`LICENSE`); bundled third-party notices in `licenses/` |
| Godot 4.6.2 standard editor | yes, to play | runs, replays, screenshots, plays and exports every game | play, replay, playtest, style audit, export, demo (making and checking games still work) | `/Applications/Godot.app` **342 MB** (binary 356,290,656 B, sha256 `e6b5cfdc…0034`) | MIT (`licenses/godot-4.6.2/LICENSE.txt`, `COPYRIGHT.txt` in the plugin; the .app carries no licence file) |
| Godot export templates 4.6.2 (official) | only to export | the player binaries copied into exported games | web build, macOS `.app`, Windows `.exe`, `hermes64_demo` | official `.tpz` about **1.25 GB** (FIRSTRUN; not on this Mac). This Mac's folder already holds only 4 files: **230 MB** (`macos.zip` 127,030,773 B; `windows_release_x86_64.exe` 104,653,312 B; `web_nothreads_release.zip` 9,573,396 B; `windows_release_x86_64_console.exe` 188,928 B) | MIT (Godot) |
| **Hermes64 stub bundle** (new, replaces the templates) | only to export | exactly the three files the exporter reads, macOS reduced to release members | same as templates | **106,937,330 B (107 MB)**, one zip; unpacked cache 168 MB | MIT (unmodified Godot member bytes) |
| Blender 5.2.1 | no (optional) | `builder=blender` static kits, character review renders, Blender character exporter | with `builder=auto` (new default): nothing user-visible, room models come from the Python builder (needs numpy) | `/Applications/Blender.app` **907 MB** | GPL (`Blender.app/Contents/Resources/text/license/license.md`: GPL-2.0-or-later / GPL-3.0-or-later notices) |
| numpy (in `python_path`) | for room models without Blender | Python static kit builder, nbchars character exporter, rigkit, reference packs, software preview | without Blender **and** numpy: no new room models, no new character bodies, no reference packs; bundled kits/cast still work | Hermes venv numpy 2.4.3 **36 MB**; user-site numpy 2.0.2 **20 MB** | BSD-3-Clause (`numpy-2.0.2.dist-info/LICENSE.txt`: "Copyright (c) 2005-2024, NumPy Developers", redistribution clauses) |
| Pillow (in `python_path`) | for JPEG references only | JPEG / non-basic PNG reference images | JPEG reference packs | Hermes venv PIL 12.3.0 **14 MB**; user-site 11.3.0 **13 MB** | MIT-CMU (`pillow-11.3.0.dist-info/METADATA` `License-Expression: MIT-CMU`) |
| ffmpeg | **no** | plugin core never calls it; only the developer probe `tools/controls_movie_probe.py` (not shipped) | nothing in the plugin; converting FLAC/M4A/Opus/AIFF (new optional route) | Homebrew ffmpeg 8.1 **52 MB** + 34 linked dylibs (not measured) | Homebrew build is **GPL** (`--enable-gpl`, libx264) and dynamically linked: not redistributable as a drop-in file. Other builds: unknown |
| codesign (`/usr/bin/codesign`) | macOS export only | ad-hoc signs the exported `.app` | macOS export | part of macOS | Apple |
| python3 for `check_install.py` | install check only | stdlib script | on a Mac without Command Line Tools, `/usr/bin/python3` opens an installer prompt (FIRSTRUN) | 0 (system) | PSF |

Hidden disk cost found while measuring (not fixed here): each project's first export copies the whole `Godot.app`
plus its templates into `<project>/.maker/local/export-editor/` (**513 MB per exporting project** in the parity run).
APFS clones (`cp -c`) or one shared, hash-checked editor copy would remove most of it; the code is `export.py` `run()`.

## Why each external program exists and what the plugin already does without it

- **Godot** is the runtime. It is not optional and cannot be shrunk inside the plugin (342 MB, signed bundle; the
  exporter needs the signed bundle intact). The plugin finds `/Applications/Godot.app`, Homebrew's cask, or
  `godot_path`; on Windows the windows-lane finder (`platforms.py`) adds winget/scoop/Program Files.
- **Export templates** are only player binaries. `adventure_maker/export.py` reads exactly
  `web_nothreads_release.zip`, `macos.zip` and `windows_release_x86_64.exe` (`TEMPLATES`, each sha256-pinned in
  `TEMPLATE_HASHES`). The other ~1 GB of the official archive (Android, iOS, Linux, debug, threaded web, ...) is
  never read. The stub bundle carries only the three, with macOS's 200 MB debug binary dropped.
- **Blender** was the default static builder because strict mesh parity of the Python builder is BLOCKED
  (`docs/NOBLENDER-PARITY.md`). The new default `auto` keeps Blender where it exists (no output change) and uses
  the Python builder only where Blender is missing (before: no room models at all).
- **numpy** is imported by 117 source files (static kit builder, nbchars, rigkit, refpack). A pure-Python fallback
  is not realistic in this lane; the setup check now detects it in the exact interpreter the plugin uses (which runs
  with `PYTHONNOUSERSITE=1`, so `pip install --user` does not help) and prints one working command (a private venv).
- **ffmpeg**: game audio is synthesised as WAV in pure Python (`audio_dsp.py`, stdlib `wave`), and Godot plays WAV,
  OGG Vorbis and MP3 natively. The new `audio_formats.py` routes WAV/OGG/MP3 with no decoder at all; only other
  formats need a converter, looked up only at a pinned path.

## Per-platform notes

| Platform | Godot | Templates / stubs | Blender | numpy | ffmpeg |
|---|---|---|---|---|---|
| macOS (Apple / Intel) | `Godot_v4.6.2-stable_macos.universal.zip`, Gatekeeper "Open" once; exporter needs the signed `.app` bundle | stub bundle verified here (export parity run below) | optional | Hermes's venv has numpy on this Mac; other installs unknown | not needed |
| Windows x86-64 | `Godot_v4.6.2-stable_win64.exe.zip`; windows-lane code, **untested on Windows** | same stub bundle (the `.exe` stub is byte-identical to the official template) | optional | unknown which Python Hermes ships on Windows | not needed |
| Linux | not a supported play host (runner refuses outside macOS / opt-in Windows job runner) | n/a (Linux templates not pinned) | n/a | n/a | n/a |
| Web player | no install; browser with WebGL2 | `web_nothreads_release.zip` (official bytes) | n/a | n/a | n/a |

## Sizes that matter to a new user, before and after this lane

| Item | Before | After |
|---|---|---|
| Export players | 1.25 GB `.tpz` download, 1.25 GB+ installed through Godot's editor | 107 MB stub bundle (one file; 168 MB once unpacked into the per-user cache) |
| Blender | needed by default for room models | not needed (auto) |
| numpy | invisible | detected and explained with one command |
| ffmpeg | listed as a dependency | not needed |
| Godot editor | 342 MB | 342 MB (unchanged; required) |
