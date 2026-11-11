# WIN3 demo: Windows/web export recipe and receiving-PC steps

**Not a Windows demo acceptance receipt.** The canonical `demo-game/teknium-vs-tyrants` was inspected read-only. It has retained web/macOS exports, no `Adventure.exe` or top-level demo ZIP. WIN3 does not overwrite it, guess its scene-specific changes, or relabel its Mac bundle as a Windows build.

## Static findings

| Check | Result | Evidence |
|---|---|---|
| Demo build entry | RISK | Frozen `_bundle/docs/demobuild/build.py:39–44,49,125–129`: `--plugin`, `--project-dir`, `--name`, `--stages export`, `--targets windows,web`; **handlers are loaded from project-dir/_bundle**, not directly from --plugin. Its full bundle stage invokes `sh`. Export failure is recorded but driver returns 0: inspect notes JSON, never trust exit code alone. |
| Frozen exporter | RISK | `_bundle/adventure_maker/export.py` still assumes a Mac Godot.app and Mac template folder. The retained `export-084902f234024c1bbf6bc05cf7755122/report.json` lists web/macOS only. Rebuilding the frozen bundle on Windows is not supported as-is. Main/demo owner must compose the Windows-capable exporter with the demo's overlay/scene-card support in a NEW scratch bundle, not copy over the only source. |
| Saves | RISK | Frozen release/project.godot uses ignored `config/custom_user_dir`; ship/main.gd uses shared `user://saves/slot1.json`. SAVEFIX in this lane uses real `config/custom_user_dir_name="Hermes64/<id>"` plus namespaced web slots. The demo must be regenerated with that save code, not just its old PCK wrapped in an exe. |
| New Windows preset | OK, static | `adventure_maker/export.py:preset`: `platform="Windows Desktop"`, x86_64, `binary_format/embed_pck=false`, `codesign/enable=false`, `application/modify_resources=false`, console wrapper 0. Resource/icon mutation is disabled; rcedit is NOT required. No custom Windows icon is specified: default engine/template icon is expected, not a custom-icon claim. No real rcedit warning was observed here. |
| Exact engine/templates | OK, static + local lookup | `export.run` checks official 4.6.2 version; template_path hashes Windows release x86_64 player and web_nothreads_release.zip. Both pinned template files are present on this Mac; no download was needed or attempted. This is not PC template verification. |
| Godot import/export | OK, static | Export writes a fresh Ship preset for each target, runs explicit --editor --import then --export-release Ship, fails on nonzero/ERROR:/SCRIPT ERROR. Windows native smoke runs only on Windows. On a Mac, the exe is labelled UNVERIFIED. |
| Web support | OK, static | Web preset disables threads, extensions, PWA and icon export. No-threads still needs **both** index.audio.worklet.js and index.audio.position.worklet.js. Frozen loader maps both (index.js:552–558). HTTP localhost/HTTPS, WebGL2 and user click for audio; opening index.html as a file is insufficient. |
| Separate PCK / website splitting | OK, static | Windows: keep Adventure.exe + Adventure.pck and licenses/ together. Web: tools/site_pack.py preserves loader/worklets; configurable 25 MiB max / 20 MiB parts, not a verified hosting-service limit. Frozen SITE-PACK.json: PCK 54,941,672 bytes / 3 parts; WASM 37,695,054 bytes / 2 parts. Read-only rejoin verified their recorded hashes and both worklet hashes. No website upload performed. |
| Audio dependencies | OK | Export stages checked original audio bytes; Godot plays imported WAV/OGG/MP3. ffmpeg may be needed during conversion/import, **not at play time**. Headless BOOT is not audio-by-ear evidence. |

## Exact build request for Main / demo composer (not a command to run against the old bundle)

The composed scratch copy must retain the demo's scene/overlay changes and consume this lane's Windows runner/discovery, export preset/template handling and SAVEFIX runtime. Keep all current proof/physical qualification requirements. Do not lower gates, hand-edit generated game data, or use --fresh on the canonical game.

With that verified scratch copy already supplied at `C:\H64\demo-source` and a numpy-capable interpreter selected as `$Python`:

```powershell
$Plugin = "$env:USERPROFILE\.hermes\plugins\hermes64" # use actual profile-local copy if appropriate
$Demo = 'C:\H64\demo-source'
# The _bundle below MUST already be the composed Windows-capable bundle.
& $Python -B "$Demo\_bundle\docs\demobuild\build.py" --plugin $Plugin --project-dir $Demo --name teknium-vs-tyrants --stages export --targets windows,web
Get-Content -LiteralPath "$Demo\notes\build-teknium-vs-tyrants.json" -Raw | ConvertFrom-Json | Select-Object -ExpandProperty stages
```

Require the `export` stage `ok=true` and the underlying exported report's targets exactly windows/web. Copy its returned share/windows directory whole into `teknium-vs-tyrants-windows`, and its share/web directory whole into `teknium-vs-tyrants-web`. Hash/package those exact folders; do not infer success from the recipe driver's zero exit. The native receiving-PC test below remains mandatory.

## Exact receiving-PC steps once Main supplies that Windows ZIP + checksum

No Hermes, editor, templates, Python, Blender or ffmpeg is needed to run the native demo. Do not install anything merely to play it.

1. Put the supplied archive and SHA256SUMS in a short user-owned local folder (sheet v3 uses C:\H64). Validate the hash first. If no current demo Windows archive is supplied, record **NOT SUPPLIED**, not pass.
2. Extract the archive (Explorer or `Expand-Archive`). Confirm `Adventure.exe`, `Adventure.pck`, licenses and README remain together; do not move just the exe.
3. From that directory in PowerShell:

   ```powershell
   & .\Adventure.exe -- --quit_after=5 | Out-String
   & .\Adventure.exe
   ```

   If a GUI exe does not relay stdout, do not treat silence as a pass or failure: inspect `%APPDATA%\Hermes64\teknium_vs_tyrants\logs\godot.log`. A properly regenerated build reports BOOT game=teknium_vs_tyrants and official 4.6.2, Windows display and the GPU. Do not substitute the old shared-save build if this path is absent.
4. Play for one minute: WASD/arrows, Shift run, Alt precision, E act, hold Z focus, Space dodge, Tab actions, I inventory, Esc pause/settings. Note whether the controls hint and pause text can be read on your display; send a screenshot, no aesthetic score needed.
5. At a safe checkpoint outside an active combat attempt: F5, move away, F9; quit and relaunch, F9 again. Record position restored yes/no and the per-game save folder. Combat-attempt saves are intentionally refused. Never reset/delete an existing personal save for this test.
6. Listen with audio on; mute/unmute using Windows volume controls. No in-game mute action is currently bound. Report heard/silence/restored separately from headless boot.
7. Optional web:

   ```powershell
   py -m http.server --bind 127.0.0.1 8060 --directory C:\H64\teknium-vs-tyrants-web
   ```

   Open http://127.0.0.1:8060/, click the canvas, test movement/audio, then reload. Do not press browser F5 expecting game quick-save. Keep the same localhost origin/port when testing IndexedDB persistence; a different origin is a different save store. Ctrl+C stops the local server. If Main supplies split web assets, keep every part and sitepack-loader.js too.

## Remaining handoff

Current demo Windows archive is **NOT BUILT / NOT INCLUDED** in WIN3 kit. No checksum is invented for it. Main/demo composition and receiving-PC execution remain open, and Windows submission readiness must stay conditional until they pass.
