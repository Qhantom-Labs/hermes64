# Windows test sheet v2 (about 30 minutes)

v1 worked most of the way on your PC (Win11, Hermes Agent 0.18.2): plugin installed, doctor READY, fox game built,
two bot playtests, Windows + web exports, boot checks, 59-60 FPS. v2 covers what is still unverified and fixes three
v1 problems: the `tools.windows_gate` step is gone (it is a developer check, not in the package), the Reedland Arena
example (`relay_combat`) now has a player character, and Hermes older than 0.20.1 loads Hermes64 in compatibility
mode.

Copy the whole `play-win` folder to the PC, for example `C:\H64\play-win` (short path). Open **PowerShell** and paste
each grey block. For every step: do it, compare with **Expected**, send back what it asks for. Stop a part when a step
fails. If `py` is not found, use `python` everywhere. If a blue "Windows protected your PC" box appears: **More
info**, then **Run anyway**.

## A. What arrived (2 min)

1. Folder listing with sizes, zipped, to send back:

   ```powershell
   cd C:\H64\play-win
   Get-ChildItem -Recurse -File | Select-Object @{n='Path';e={$_.FullName.Substring((Get-Location).Path.Length+1)}}, Length | Export-Csv -NoTypeInformation .\play-win-listing.csv
   Compress-Archive -Force .\play-win-listing.csv .\play-win-listing.zip
   (Import-Csv .\play-win-listing.csv).Count
   ```

   Expected: a number (files in the folder) and `play-win-listing.zip` in the folder. Send back:
   **play-win-listing.zip**.
2. Checksums:

   ```powershell
   Get-Content .\SHA256SUMS | ForEach-Object { $h, $f = $_ -split '  ', 2; if (-not (Test-Path -LiteralPath $f)) { "MISSING  $f" } elseif ((Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash -ne $h.ToUpper()) { "BAD  $f" } }; "check done"
   ```

   Expected: only `check done`. Send back: any `MISSING` / `BAD` lines.

## B. Boot lines (2 min)

3. Each game opens a window for 5 s and closes it:

   ```powershell
   foreach ($g in 'thaw','reedland-combat','reedland-relay','puzzle-hall') { & ".\$g-windows\Adventure.exe" '--' '--quit_after=5' | Out-String }
   ```

   Expected: four lines like `BOOT game=thaw ... godot=4.6.2-stable (official) display=Windows ... adapter=<your GPU>`.
   Send back: the four lines. Only if a window stays black or nothing prints:
   `Expand-Archive .\thaw-windows-diagnostic.zip -DestinationPath .\thaw-diagnostic -Force; & .\thaw-diagnostic\Adventure.console.exe`
   and send the console text plus `Get-Content $env:APPDATA\Hermes64\thaw\logs\godot.log -Tail 60`.

## C. Play checks still unverified (15 min)

Double-click each game's `Adventure.exe`. Keys: W/A/S/D move, Shift walk, E use, Space dodge, Esc menu, F5 quick-save,
F9 quick-load, hold R retry/reset.

4. **Audio on.** In Thaw, walk for 20 s. Expected: background sound plus footstep/effect sounds.
5. **Audio off.** These builds have **no in-game mute key** (none is bound in the runtime). Press the keyboard's mute
   key (or click the taskbar speaker icon and mute), wait 5 s, unmute. Expected: silence while muted, sound back
   after unmuting, the game keeps running. Send back for 4-5: sound yes/no, came back yes/no.
6. **Save/load in each game** (Thaw, Reedland Combat, Reedland Relay, Puzzle Hall): walk somewhere you will
   recognise, press **F5**, walk away, press **F9**. Expected: a small checkpoint glyph after F5; after F9 you are
   back where you saved. Then quit (Esc menu), start the game again, press **F9**. Expected: back at the save.
7. Saves on disk:

   ```powershell
   Get-ChildItem $env:APPDATA\Hermes64 -Recurse -File | Select-Object FullName, Length
   ```

   Expected: one folder per game you saved in, each with a save file and `logs\godot.log`. Send back: works / not
   per game for step 6, and this list.
8. **Manual dodge, Reedland Combat.** Walk up to an enemy; when it winds up (telegraph), press **Space**. Expected:
   your character dodges and the hit misses; standing still through an attack costs health. Send back: dodge seen
   yes/no, hit avoided yes/no.
9. **Push, Puzzle Hall.** Walk straight into a block. Expected: it slides one step the way you walk.
10. **Pull, Puzzle Hall.** Stand against a block, **hold E** and walk backwards. Expected: the block follows one step.
    Then **hold R** (about 0.6 s). Expected: the room's blocks return to their start. Send back for 9-10: push,
    pull, reset each works / not.
11. **Web build in a browser**, served by a local static server (double-clicking `index.html` does not work):

    ```powershell
    py -m http.server --bind 127.0.0.1 8000 --directory C:\H64\play-win\thaw-web
    ```

    Open http://127.0.0.1:8000/ in Edge or Chrome, click the page once, play a minute. Do not press F5 in the
    browser (it reloads the page). Expected: the game starts with picture and sound. Ctrl+C in PowerShell stops
    the server; repeat with `puzzle-hall-web` if there is time. Send back: works / not, and any red lines in the
    browser console (F12).

## D. Plugin on Windows (10 min, needs Hermes on the PC)

12. Unpack, check, list what works:

    ```powershell
    Expand-Archive .\hermes64-plugin.zip -DestinationPath C:\H64 -Force
    py C:\H64\hermes64\tools\check_install.py
    cd C:\H64\hermes64
    py -B -m adventure_maker.doctor --windows-checklist
    ```

    Expected: `PASS  hermes64 1.0.0-rc at C:\H64\hermes64: N/N files verified` (both numbers equal), then `OK` /
    `MISSING` / `OFF` lines with a fix each and a `RESULT` line. Send back: both outputs.
13. `hermes --version`. Hermes 0.18.2 to 0.20.0 runs Hermes64 in **compatibility mode**: settings come from
    `config.yaml` and there is no default games folder, so set the plugin setting `projects_root` to an existing
    folder (for example `C:\H64\games`). 0.20.1 or newer needs nothing extra. Send back: the version line.
14. Install the plugin into Hermes as before (point it at `C:\H64\hermes64`; keep
    `HERMES64_WINDOWS_RUNNER=job` from v1), restart Hermes, then in Hermes:
    `/hermes64 new "A fox searches the village for its lost lantern"`. Expected: four lines (Made / Style / Badge /
    Play). Send back: the four lines or the exact error.
15. Ask Hermes: "make the bundled relay_combat example and playtest it". Expected: it builds and has a **player
    character** without adding one by hand. Send back: yes/no and a screenshot of the first room.
16. If any build says Blender failed: send the Blender error text (it shows whether Blender was missing or crashed),
    then ask Hermes to set the plugin setting `builder` to `python` and rebuild.

## E. Export any local fix as a patch file (2 min)

17. If your PC agent changed **any** plugin file (for example the 0.18.2 compatibility fix), export it. With Git
    installed, compare against a fresh unzip:

    ```powershell
    Expand-Archive C:\H64\play-win\hermes64-plugin.zip -DestinationPath C:\H64\fresh -Force
    git diff --no-index C:\H64\fresh\hermes64 C:\H64\hermes64 > $HOME\Desktop\hermes64-local-compat.patch
    (Get-Item $HOME\Desktop\hermes64-local-compat.patch).Length
    ```

    Without Git, ask your Hermes agent: "write every change you made to the hermes64 plugin as one unified diff file
    hermes64-local-compat.patch on my Desktop". If it changed Hermes itself rather than the plugin, ask for that too
    as `hermes-local-compat.patch`. Expected: a non-empty `.patch` file. Send back: the patch file(s) unchanged.

## What to send back

- `play-win-listing.zip`, the patch file(s), and for each step: works / does not work plus the text it asks for
  (copy-paste, not retyped).
- PC model, Windows version (`winver`), graphics card
  (`Get-CimInstance Win32_VideoController | Select Name, DriverVersion`).
- Screenshots where a step asks, or when something looks wrong.
