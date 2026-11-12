# Windows test sheet v4 (about 60 minutes)

**Every command on this sheet needs the PC owner's approval before it runs.** Commands are kept small: run one
block, show the output, get the next approval. Nothing here has passed on this release yet: earlier Windows reports
were prose about older packages, with no receipt ([PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md)). Record what really
happens; never retype or tidy output. Receipt template:
[receipts/WINDOWS-RECEIPT-TEMPLATE.md](receipts/WINDOWS-RECEIPT-TEMPLATE.md).

Rules:
- Use **PowerShell** (not cmd). Short folders: `C:\H64`. If `py` is missing, use the full path of a Python 3.9+
  `python.exe` everywhere `py` appears.
- No secrets in receipts: no tokens, `.env`, `config.yaml`, user names or the PC name (write `<user>`, `<pc>`).
- A blue "Windows protected your PC" box: **More info**, then **Run anyway** (the exported game is unsigned).
- On a FAIL: save the output, note the step, continue with the next part unless the step says stop. Do not change
  plugin code or gates to make a step pass; if the PC's agent changes anything, export it as in step 17.

## A. The PC (5 min)

1. Folders and facts (no PC name is collected):

   ```powershell
   $T = 'C:\H64'; $R = "$T\receipt"; New-Item -ItemType Directory -Force -Path "$R\outputs" | Out-Null
   Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture | Format-List | Out-File "$R\outputs\a1-machine.txt"
   Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion | Format-List | Out-File -Append "$R\outputs\a1-machine.txt"
   "PowerShell $($PSVersionTable.PSVersion)" | Out-File -Append "$R\outputs\a1-machine.txt"
   Get-Content "$R\outputs\a1-machine.txt"
   ```

   **PASS if** it shows Windows 11, the build number, the graphics adapter and the PowerShell version.
2. Python, Hermes and the Hermes home folder:

   ```powershell
   py -0p; py -c "import sys, numpy, PIL; print(sys.version.split()[0], numpy.__version__, PIL.__version__)"
   hermes --version; hermes config path
   ```

   Save the output as `$R\outputs\a2-versions.txt`. **PASS if** Python is 3.9+ with numpy 2.x and Pillow, Hermes is
   0.18.2 or newer, and `hermes config path` prints a `config.yaml` path. Its folder is the Hermes home
   (normally `%LOCALAPPDATA%\hermes`; `HERMES_HOME` overrides it). If numpy
   is missing, stop and ask the owner which Python the plugin should use (`python_path`); do not pip-install into
   Hermes's own environment without approval.

## B. Runner opt-in (2 min)

3. Making games on Windows needs the owner's explicit opt-in. Read this first: the Job Object runner stops a child
   and everything it starts together and caps processes and memory, but it gives **no OS-enforced network or write
   confinement** ([WINDOWS.md](WINDOWS.md)). With approval:

   ```powershell
   [Environment]::SetEnvironmentVariable('HERMES64_WINDOWS_RUNNER', 'job', 'User')
   [Environment]::GetEnvironmentVariable('HERMES64_WINDOWS_RUNNER', 'User') | Tee-Object "$R\outputs\b3-runner.txt"
   ```

   **PASS if** it prints `job`. Close this PowerShell window and Hermes, then open a new PowerShell window (so the
   variable is visible) and set `$T`/`$R` again as in step 1.

## C. Install and check (10 min)

4. Install the exact package under test. With the release zip and its SHA-256 from the maintainers:

   ```powershell
   $Zip = 'C:\H64\hermes64-XXXX.zip'          # the file the maintainers sent
   (Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash | Tee-Object "$R\outputs\c4-unzip.txt"
   ```

   **Stop if** the hash differs from the one sent with the zip. Then (Hermes stopped; move any older
   `plugins\hermes64` to a folder outside `plugins` first):

   ```powershell
   $HH = Split-Path -Parent (hermes config path); New-Item -ItemType Directory -Force -Path "$HH\plugins" | Out-Null
   Expand-Archive -LiteralPath $Zip -DestinationPath "$HH\plugins"
   $PLUGIN = "$HH\plugins\hermes64"; Test-Path "$PLUGIN\plugin.yaml" | Tee-Object -Append "$R\outputs\c4-unzip.txt"
   ```

   **PASS if** it prints `True` (not `plugins\hermes64\hermes64`). Without a zip: `hermes plugins install
   Qhantom-Labs/hermes64 --ref COMMIT_UNDER_TEST --enable`, then `$PLUGIN = "$HH\plugins\hermes64"`.
5. Package check:

   ```powershell
   py -B "$PLUGIN\tools\check_install.py" 2>&1 | Tee-Object "$R\outputs\c5-check-install.txt"
   ```

   **PASS if** `PASS  hermes64 ... N/N files verified` with both numbers equal. **FAIL if** it names CRLF damage or a
   long path: send the output.
6. The Windows checklist:

   ```powershell
   Set-Location $PLUGIN; py -B -m adventure_maker.doctor --windows-checklist 2>&1 | Tee-Object "$R\outputs\c6-checklist.txt"
   ```

   **PASS if** `Child runner (job-object)` is `OK` and Python/numpy are `OK`. Godot and templates may be `MISSING`
   until step 8.
7. Enable in Hermes (approve numpy/Pillow if asked), restart Hermes, open a **new** chat and type `/hermes64 setup`:

   ```powershell
   hermes plugins enable hermes64; hermes plugins list --enabled
   ```

   Save the chat reply as `$R\outputs\c7-setup.txt`. **PASS if** the reply has the line `This is Hermes64 ...
   running from ...` naming the package under test, and a `Child runner` row marked ok whose detail starts with
   `job-object:`.

## D. Making games (25 min)

8. Godot 4.6.2. In the chat: `/hermes64 setup --fetch` shows the plan (official URLs, SHA-512, cache folder) and
   downloads nothing. Only if the owner approves the plan, **the owner types** `/hermes64 setup --fetch --templates
   --yes`. Save both replies as `$R\outputs\d8-fetch.txt`. **PASS if** the second reply ends with a checklist where
   Godot 4.6.2 is ok. (By hand instead: unzip `Godot_v4.6.2-stable_win64.exe.zip` from the official release to
   `%LOCALAPPDATA%\Programs\Godot` and run step 6 again.)
9. Runner checks: save the probe, then run it (it starts only small Python children and kills only processes
   carrying its own marker). Paste this block as it is:

```powershell
Set-Content -Encoding ASCII -Path "$T\h64_winprobe.py" -Value @'
"""Hermes64 Windows runner probes. py -B h64_winprobe.py PLUGIN WORK"""
import os, socket, subprocess, sys, threading, time
plugin, work = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
sys.path.insert(0, plugin)
from adventure_maker import platforms, runner, safety
from adventure_maker.safety import Fault
iso = platforms.isolation()
print('ISOLATION', iso['mode'], '|', iso['note'])
if not iso['available']:
    print('RESULT runner off: no child was started (set HERMES64_WINDOWS_RUNNER=job and restart)')
    sys.exit(2)
games = os.path.join(work, 'games')
os.makedirs(games, exist_ok=True)
name = 'probe%d' % int(time.time())
proj = safety.Project(games, name, create=True)
run = runner.Runner(proj)
tag = 'h64mark' + name
results = []


def child(code, timeout=20):
    try:
        out = run.run([sys.executable, '-I', '-S', '-c', code], proj.root, timeout=timeout)
        return out['returncode'], out['stdout'], out['stderr'][-200:]
    except Fault as exc:
        return 'FAULT:' + exc.code, '', str(exc)[:200]


def check(label, ok, detail):
    results.append(bool(ok))
    print('%-4s %-30s %s' % ('PASS' if ok else 'FAIL', label, detail))


def marked():
    """Process ids whose command line holds this run's marker (CIM query through PowerShell)."""
    query = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*%s*' -and "
             "$_.Name -ne 'powershell.exe' } | ForEach-Object { $_.ProcessId }" % tag)
    out = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', query], capture_output=True,
                         text=True, encoding='utf-8', errors='replace', timeout=60,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)).stdout
    return [int(x) for x in out.split() if x.isdigit() and int(x) != os.getpid()]


try:
    code, out, err = child('print("hello")')
    check('suspended start resumes child', code == 0 and out.strip() == 'hello', '%s %r %s' % (code, out.strip(), err))
    code, out, err = child('import sys; sys.stdout.buffer.write(b"a\\r\\nb\\r\\n")')
    check('CRLF normalised', out == 'a\nb\n', repr(out))
    os.environ['H64_SECRET_TEST'] = 'should-not-pass'
    code, out, err = child('import os; print(" ".join(sorted(k.upper() for k in os.environ)))')
    allowed = {'USERPROFILE', 'HOME', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'SYSTEMROOT', 'WINDIR', 'PATH',
               'PATHEXT', 'COMSPEC', 'NUMBER_OF_PROCESSORS', 'PROCESSOR_ARCHITECTURE', 'PYTHONDONTWRITEBYTECODE',
               'PYTHONNOUSERSITE', 'PYTHONUTF8', 'PYTHONIOENCODING', 'BLENDER_USER_CONFIG', 'BLENDER_USER_SCRIPTS',
               'BLENDER_USER_DATAFILES'}
    extra = sorted(k for k in set(out.split()) - allowed if not k.startswith('='))
    check('env scrubbed', out and 'H64_SECRET_TEST' not in out and not extra, 'extra=%s' % extra)
    code, out, err = child('import sys; sys.stdout.write("x" * 1200000)')
    check('output cap', code == 'FAULT:output_limit', str(code))
    KEEP = ('import subprocess, sys, time\n'
            'flags = 0x00000008 | 0x00000200\n'          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            'subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)  # %s"], creationflags=flags)\n'
            'time.sleep(600)\n' % tag)
    t0 = time.time()
    code, out, err = child(KEEP, timeout=5)
    time.sleep(3)
    left = marked()
    check('timeout kills detached grandchild', code == 'FAULT:timeout' and not left,
          '%s after %.1fs; leftovers=%s' % (code, time.time() - t0, left))
    BREAK = ('import subprocess, sys\n'
             'try:\n'
             ' subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)  # %s"], creationflags=0x01000000)\n'
             ' print("BREAKAWAY_STARTED")\n'
             'except OSError as e:\n'
             ' print("BREAKAWAY_REFUSED", e.winerror if hasattr(e, "winerror") else e.errno)\n' % tag)
    code, out, err = child(BREAK, timeout=10)
    time.sleep(3)
    left = marked()
    check('no escape by breakaway', not left, out.strip() + '; leftovers=%s' % left)
    srv = socket.socket()
    srv.bind(('127.0.0.1', 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
    code, out, err = child('import socket\ntry:\n socket.create_connection(("127.0.0.1", %d), 3).close(); print("OPEN")\n'
                           'except OSError as e:\n print("BLOCKED", e)\n' % port)
    print('INFO network inside the Job Object runner: %s (expected OPEN: Windows has no OS network block here, as '
          'documented)' % out.strip())
finally:
    for pid in marked():
        subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
print('RESULT %s (%d/%d checks passed)' % ('PASS' if all(results) else 'FAIL', sum(results), len(results)))
'@
```

   ```powershell
   py -B "$T\h64_winprobe.py" "$PLUGIN" "$T" 2>&1 | Tee-Object "$R\outputs\d9-runner.txt"
   ```

   **PASS if** the first line is `ISOLATION job-object | ...` and the last is `RESULT PASS (6/6 checks passed)`:
   a child starts and is resumed after being placed in its job, CRLF output becomes LF, the environment holds only
   the listed names, more than 1 MiB of output stops the child, and neither a detached grandchild nor a
   breakaway attempt survives the run (expected `BREAKAWAY_REFUSED 5`). The `INFO network` line is expected to say
   `OPEN`: record it (Windows does not block the network here, as documented). Also record: did any console window
   flash during the probe (yes/no)?
10. A bundled example through the whole pipeline (scaffold, compile, proof, build, bot playtest, web export):

    ```powershell
    New-Item -ItemType Directory -Force -Path "$T\games" | Out-Null; Set-Location $PLUGIN
    py -B -m adventure_maker.demo --projects-root "$T\games" --project thaw1 --example thaw 2>&1 | Tee-Object "$R\outputs\d10-demo.txt"
    ```

    **PASS if** it prints `HERMES64 — local demo ready`, one line per stage, `Playtest:` with a verdict and a
    `Web/share:` path. **FAIL if** it prints `HERMES64 DEMO FAILED:` (send the JSON after it).
11. In the Hermes chat: `/hermes64 new "A fox searches the village for its lost lantern"`. Save the reply as
    `$R\outputs\d11-new.txt`. **PASS if** it returns the Made / Style / Badge / Play lines. Run its PowerShell
    `Play:` line, walk with W/A/S/D, press E near something, Esc to pause, and record what you saw.
12. Playtest and exports of that game, then the macOS refusal (use the project name the `Made` line gave, `fox`
    below; the games folder is the one `/hermes64 setup` names):

    ```powershell
    $Games = 'GAMES_FOLDER_FROM_SETUP'; Set-Location $PLUGIN
    @'
    import json, sys
    from adventure_maker import demo
    s = {'projects_root': sys.argv[1], 'python_path': sys.executable}
    for tool, args in (('hermes64_playtest', {'project': sys.argv[2], 'mode': 'winning'}),
                       ('hermes64_export', {'project': sys.argv[2], 'targets': ['web', 'windows']}),
                       ('hermes64_export', {'project': sys.argv[2], 'targets': ['macos']})):
        r = json.loads(demo.handle(s, tool, args))
        print(tool, args.get('targets', ''), 'ok=%s' % r.get('ok'), json.dumps(r.get('error') or
              {k: r[k] for k in ('verdict', 'share_path', 'zip_path') if k in r})[:600])
    '@ | py -B - $Games fox 2>&1 | Tee-Object "$R\outputs\d12-export.txt"
    ```

    **PASS if** the playtest and the web + windows export say `ok=True` (on Windows the export also boots the `.exe`
    headless), and `macos` says `ok=False` with `export_target` and `The macos target needs a Mac ... Nothing was
    exported.`
13. Blender (only if it is installed; a report on an older package said Blender failed, cause unknown):

    ```powershell
    Set-Location $PLUGIN; py -B -c "from adventure_maker import runner; print(runner.locate('blender'))" 2>&1 | Tee-Object "$R\outputs\d13-blender.txt"
    ```

    **PASS if** it prints the path of your `blender.exe` (Program Files, Steam, scoop, winget or an unzipped
    `blender-<version>-windows-x64` folder in Downloads/Desktop/home are searched; newest version first). If it says
    `missing_tool`, record where Blender actually is. Then in the chat ask for one room rebuild with the plugin
    setting `builder` set to `blender`; on an error, save the whole Blender error text.

## E. Playing (10 min)

14. Double-click the exported `Adventure.exe` (from step 12's windows export). Play a minute: picture, sound,
    W/A/S/D, E, Esc menu, F5 quick-save then F9 quick-load. Record works / not per item and a screenshot.
15. The web export in a browser (double-clicking `index.html` does not work):

    ```powershell
    py -m http.server --bind 127.0.0.1 8000 --directory 'WEB_FOLDER_FROM_STEP_12'
    ```

    Open http://127.0.0.1:8000/ in Edge or Chrome, click once, play a minute (do not press F5 in the browser).
    Ctrl+C stops the server. Record works / not and any red lines in the browser console (F12).
16. Studio (only if your Hermes has the desktop app or dashboard with the Hermes64 tab): open it, pick the fox game,
    choose **PLAY WINDOWS BUILD**, move to **YES**, confirm. **PASS if** the game starts outside Hermes. Record
    a screenshot of the menu. If the tab or the entry is missing, record that (SKIPPED with the reason).

## F. Local changes and the receipt

17. If the PC's agent changed **any** plugin or Hermes file, export it unchanged (with Git installed):

    ```powershell
    Expand-Archive -LiteralPath $Zip -DestinationPath "$T\fresh" -Force
    git diff --no-index "$T\fresh\hermes64" $PLUGIN > "$R\hermes64-local-changes.patch"
    (Get-Item "$R\hermes64-local-changes.patch").Length
    ```

    `0` means no changes. Without Git, ask the agent to write every change as one unified diff file into `$R`.
18. Fill a copy of [receipts/WINDOWS-RECEIPT-TEMPLATE.md](receipts/WINDOWS-RECEIPT-TEMPLATE.md) as
    `$R\RECEIPT.md` from the files in `$R\outputs`, mark each step PASS / FAIL / SKIPPED with the reason, remove user
    and PC names, and hand the folder over as `docs/receipts/windows/<YYYY-MM-DD>-<machine alias>/`. Do not edit
    `WINDOWS.md` or "Tested by the owner"; maintainers update them from the receipt.

## If something fails

Send: the step number, the whole output file, the `.maker\runs\*\*.process.json` file a message names, the
checklist output (step 6) and, for a crashing game, `Get-Content $env:APPDATA\Hermes64\<game>\logs\godot.log
-Tail 60`. Turning the runner back off: `[Environment]::SetEnvironmentVariable('HERMES64_WINDOWS_RUNNER', $null,
'User')`, then restart Hermes.
