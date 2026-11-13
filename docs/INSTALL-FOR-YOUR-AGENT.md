# Install message for your own Hermes agent

Use a supplied release ZIP when you cannot reach GitHub (the public route is `hermes plugins install Qhantom-Labs/hermes64 --enable`) or you want an exact candidate. **This is installation guidance, not permission to publish, change credentials, disable guards, restart shared services or fetch extra software.** Give the agent the ZIP, its SHA-256 from a separate trusted release message, and the absolute Hermes home/profile you actually use. No credential is needed in the message.

**Where the Hermes home is.** macOS and Linux: `~/.hermes`. Windows: `%LOCALAPPDATA%\hermes` (Hermes 0.18.2 and
newer). `HERMES_HOME` overrides the default on every system, and a profile has its own folder under
`profiles\<name>`. `hermes config path` prints the config file inside the home in
use; plugins go in its `plugins` folder.

The archive must contain one top-level `hermes64/` directory with `plugin.yaml` and `PACKAGE-MANIFEST.json`. Verify before replacing an existing copy. Backups belong **outside** `plugins/`, otherwise Hermes can discover the old copy too. Do not overwrite an in-use plugin; close the relevant session or arrange a safe refresh first.

## Mac: one paste to your agent

Replace the three uppercase placeholders before sending this block:

```text
Install the Hermes64 ZIP at ZIP_ABSOLUTE_PATH into my active Hermes home HERMES_HOME_ABSOLUTE_PATH. The independently supplied expected SHA-256 is EXPECTED_SHA256.

Do not download another package, use a wildcard ZIP, touch other profiles, change model/provider settings, install dependencies without approval, or restart a shared backend. Do not replace an in-use plugin. First confirm my chosen home, the exact ZIP hash with shasum -a 256, and the archive layout (one hermes64/ wrapper, no traversal, duplicate members or symlinks). Create a fresh staging directory under that home's cache/scratch, extract with ditto -x -k "$ZIP" "$STAGE", confirm "$STAGE/hermes64/plugin.yaml", and run python3 -B "$STAGE/hermes64/tools/check_install.py". Only after PASS, move the old plugins/hermes64 to a unique backup under the home's plugin-backups, move the checked staged hermes64 into plugins/hermes64, and rerun its tools/check_install.py. If the hash/layout/check fails, stop and retain the old plugin. Keep the backup outside plugins. Run hermes plugins enable hermes64 and hermes plugins list --enabled in my chosen HERMES_HOME only with my dependency/security consent, then tell me to restart the relevant Hermes surface and start a NEW chat. Do not hand-edit the enabled list to bypass admission.

After the new chat, run /hermes64 setup. Quote the actual "This is Hermes64 ... running from ..." line, including its source commit; confirm it matches the package, not an older copy. Report any missing Godot/numpy/Pillow separately. A file-copy PASS is not a loaded-plugin PASS. Do not fetch Godot; show /hermes64 setup --fetch for my review, and let me type /hermes64 setup --fetch --yes if I approve it.
```

### Mac recipe (zsh/bash)

This shell block checks/extracts/backups only. It does not enable or install dependencies. `EXPECTED_SHA256` must be the hash for **this exact ZIP**, not an older release.

```sh
ZIP='ZIP_ABSOLUTE_PATH'
EXPECTED_SHA256='EXPECTED_SHA256'
HH='HERMES_HOME_ABSOLUTE_PATH'
(
  set -eu
  case "$ZIP:$HH" in /*:/*) ;; *) printf '%s\n' 'Use absolute ZIP and Hermes-home paths'; exit 1;; esac
  [ "${#EXPECTED_SHA256}" -eq 64 ] || exit 1
  case "$EXPECTED_SHA256" in *[!0-9a-fA-F]*) exit 1;; esac
  ACTUAL=$(/usr/bin/shasum -a 256 "$ZIP")
  ACTUAL=${ACTUAL%% *}
  [ "$ACTUAL" = "$EXPECTED_SHA256" ] || { printf '%s\n' 'SHA-256 mismatch; stopped'; exit 1; }
  mkdir -p "$HH/cache/scratch" "$HH/plugin-backups" "$HH/plugins"
  STAGE=$(mktemp -d "$HH/cache/scratch/hermes64-install.XXXXXX")
  python3 -B -c 'import pathlib,stat,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); rows=z.infolist(); names=[x.filename for x in rows]; assert len(names)==len(dict.fromkeys(names)); assert all(x.filename.startswith("hermes64/") and ".." not in pathlib.PurePosixPath(x.filename).parts and "\\" not in x.filename and not stat.S_ISLNK(x.external_attr >> 16) for x in rows); assert "hermes64/plugin.yaml" in names and "hermes64/PACKAGE-MANIFEST.json" in names' "$ZIP"
  /usr/bin/ditto -x -k "$ZIP" "$STAGE"
  [ -f "$STAGE/hermes64/plugin.yaml" ] || exit 1
  python3 -B "$STAGE/hermes64/tools/check_install.py"
  if [ -e "$HH/plugins/hermes64" ]; then
    BACKUP=$(mktemp -d "$HH/plugin-backups/hermes64.XXXXXX")
    mv "$HH/plugins/hermes64" "$BACKUP/hermes64"
    printf 'Backup: %s\n' "$BACKUP/hermes64"
  fi
  mv "$STAGE/hermes64" "$HH/plugins/hermes64"
  python3 -B "$HH/plugins/hermes64/tools/check_install.py"
  printf '%s\n' 'Files checked. Enable with consent, restart Hermes, then start a NEW chat.'
)
```

Then, in that same chosen home/profile:

```sh
HERMES_HOME="$HH" hermes plugins enable hermes64
HERMES_HOME="$HH" hermes plugins list --enabled
```

The `HH` value must still be the chosen absolute home. Enable may prepare shared dependencies; it was **not executed** in this no-install docs lane. If it fails, retain the error and backup. Do not treat a successful copy as activation.

## Windows: one paste to your agent (UNVERIFIED on Windows)

Replace the same three placeholders before sending. PowerShell 5.1 syntax is intended; no native PowerShell parser/runtime was available here.

```text
Install the exact Hermes64 ZIP at ZIP_ABSOLUTE_PATH into HERMES_HOME_ABSOLUTE_PATH, using the independently supplied SHA-256 EXPECTED_SHA256. Use PowerShell Get-FileHash -Algorithm SHA256 and compare the exact hash first. Inspect the ZIP entries for one hermes64/ wrapper, no traversal, duplicate names or symlinks. Expand-Archive -LiteralPath the ZIP into a fresh staging directory under that home's cache\scratch, confirm hermes64\plugin.yaml and PACKAGE-MANIFEST.json, and run py -B on its tools\check_install.py; stop on any nonzero $LASTEXITCODE. Only after PASS, move the old plugins\hermes64 into a unique plugin-backups directory outside plugins, move the staged folder into plugins\hermes64 and rerun check_install.py. Enable with hermes plugins enable hermes64 and verify hermes plugins list --enabled in the chosen HERMES_HOME only after my dependency/security consent. Do not touch other profiles, credentials, model/provider settings or shared services. Do not install dependencies without my approval or bypass a failed enable by editing config.

After normal enable, have me restart the relevant Hermes surface and start a NEW chat. Run /hermes64 setup there and quote its actual "This is Hermes64 ... running from ..." line. Report missing requirements and the exact package commit. Windows child execution also needs my explicit HERMES64_WINDOWS_RUNNER=job opt-in; explain that Job Objects do NOT provide network or write confinement. Do not silently set it. Do not fetch Godot: show the plan and let me approve the human-typed fetch separately. This Windows recipe is not native-PC acceptance.
```

### PowerShell recipe (UNVERIFIED)

```powershell
$Zip = 'ZIP_ABSOLUTE_PATH'
$ExpectedSha256 = 'EXPECTED_SHA256'
$HermesHome = 'HERMES_HOME_ABSOLUTE_PATH'
$ErrorActionPreference = 'Stop'
if (-not [IO.Path]::IsPathRooted($Zip) -or -not [IO.Path]::IsPathRooted($HermesHome)) { throw 'Use absolute paths' }
if ($ExpectedSha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Supply the exact SHA-256' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $Zip).Hash -ne $ExpectedSha256) { throw 'SHA-256 mismatch' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$Archive = [IO.Compression.ZipFile]::OpenRead($Zip)
try {
    $Names = @($Archive.Entries | ForEach-Object { $_.FullName })
    if (($Names | Select-Object -Unique).Count -ne $Names.Count) { throw 'Duplicate ZIP members' }
    foreach ($Entry in $Archive.Entries) {
        $Name = $Entry.FullName
        if (-not $Name.StartsWith('hermes64/') -or $Name.Contains('\') -or ($Name.Split('/') -contains '..') -or (($Entry.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Unsafe ZIP layout' }
    }
    if ($Names -notcontains 'hermes64/plugin.yaml' -or $Names -notcontains 'hermes64/PACKAGE-MANIFEST.json') { throw 'Not a packaged Hermes64 ZIP' }
} finally { $Archive.Dispose() }
$Scratch = Join-Path $HermesHome 'cache\scratch'
$Backups = Join-Path $HermesHome 'plugin-backups'
$Plugins = Join-Path $HermesHome 'plugins'
New-Item -ItemType Directory -Force -Path $Scratch, $Backups, $Plugins | Out-Null
$Stage = Join-Path $Scratch ('hermes64-install-' + [guid]::NewGuid().ToString('N'))
Expand-Archive -LiteralPath $Zip -DestinationPath $Stage
$Candidate = Join-Path $Stage 'hermes64'
if (-not (Test-Path -LiteralPath (Join-Path $Candidate 'plugin.yaml'))) { throw 'Missing plugin.yaml' }
& py -B (Join-Path $Candidate 'tools\check_install.py')
if ($LASTEXITCODE -ne 0) { throw 'Staged package check failed' }
$Target = Join-Path $Plugins 'hermes64'
if (Test-Path -LiteralPath $Target) {
    $Backup = Join-Path $Backups ('hermes64-' + [guid]::NewGuid().ToString('N'))
    Move-Item -LiteralPath $Target -Destination $Backup
    Write-Output "Backup: $Backup"
}
Move-Item -LiteralPath $Candidate -Destination $Target
& py -B (Join-Path $Target 'tools\check_install.py')
if ($LASTEXITCODE -ne 0) { throw 'Installed-copy check failed; keep the backup' }
Write-Output 'Files checked. Enable with consent, restart Hermes, then start a NEW chat.'
```

Then, in the same PowerShell window, only with normal enable/dependency consent:

```powershell
$env:HERMES_HOME = $HermesHome
hermes plugins enable hermes64
if ($LASTEXITCODE -ne 0) { throw 'Enable failed; do not claim activation' }
hermes plugins list --enabled
```

Then, for making games on Windows, the owner opts in to the Job Object runner (current user, then restart Hermes):
`[Environment]::SetEnvironmentVariable('HERMES64_WINDOWS_RUNNER', 'job', 'User')`. If builds stop on NumPy, set the
plugin setting `python_path` to a `python.exe` whose own site-packages have numpy (for example a virtual
environment's `Scripts\python.exe`). [WINDOWS.md](WINDOWS.md) has the rest.

## Linux (UNVERIFIED on Linux)

The public route works the same way on Linux: `hermes plugins install Qhantom-Labs/hermes64 --enable` (use this
`owner/repo` form). For a zip, the Mac recipe above applies with two changes: `sha256sum` instead of
`/usr/bin/shasum -a 256`, and `python3 -m zipfile -e "$ZIP" "$STAGE"` instead of `ditto -x -k` (the package needs no
file modes). Making games needs a working bubblewrap (`bwrap`) and Godot 4.6.2 installed by hand; check both with
`python3 -B -m adventure_maker.doctor --linux-checklist` in the plugin folder. [LINUX.md](LINUX.md) has the details,
including the Ubuntu 24.04 AppArmor step and the explicit `HERMES64_LINUX_RUNNER=unconfined` opt-in.

## What was actually checked

The Mac extraction/check/backup block was exercised against a **scratch home**, not the owner's active install, using the rc7 ZIP. Its source is `807b472dcce4d1a63f7163afde602c614198a7fe`; its SHA-256 is `ac185329f2d381100fd8216cf3c1bc1c19f8330ec2452e71e80045b8e4b12ad0`. **Do not reuse that hash for rc8.** The package's `check_install.py` checked 5,964 files.

No enable/dependency installation, live-session reload, fresh-model first game or actual Godot download was performed in this docs lane. The PowerShell block has not run on Windows, and the Linux variant has not run on Linux. The running build-identification line must come from the recipient's new chat, not from copying this document.
