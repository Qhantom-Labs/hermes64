# One-step Godot setup

Type **`/hermes64 setup --fetch`** in Hermes. It shows what would be downloaded, from where, the SHA-512 pins, the
size caps, the MIT licence note and the cache folder, and downloads nothing. To approve, type
`/hermes64 setup --fetch --yes` yourself (add `--templates` to also get the official export templates). No download
happens when the plugin is installed or imported, when you ask it to make a game, or when you run the plain
`/hermes64 setup` checklist.

From a terminal in the plugin folder:

- macOS: `python3 tools/hermes64_setup.py --fetch [--templates]`
- Windows PowerShell: `py tools/hermes64_setup.py --fetch [--templates]`
- Linux: `python3 tools/hermes64_setup.py --fetch` is **refused** in this release (no Linux pin; see below)

The terminal asks `Download and verify these files? [y/N]`; Enter or `n` cancels. Add `--yes` only to approve
without a prompt. In automation, `--json` returns the result; progress and disclosure go to stderr.
`--fetch-plan` prints every pin without connecting.

**Consent stays with you.** The agent's existing `hermes64_doctor` tool includes the setup checklist and the official editor/export-template plan automatically as `setup.download_plan`. It has no fetch or consent argument, and no separate `hermes64_setup` tool is registered. It only reports the plan and the command you have to type. The agent cannot download Godot.
Under cron or a gateway with no one typing, the result is `confirmation_required`; nothing waits on input.

## What is downloaded (official upstream files only)

Every file comes from `https://github.com/godotengine/godot-builds/releases/download/4.6.2-stable/`, the official
Godot release, and is pinned by the SHA-512 published in that release's `SHA512-SUMS.txt`. Nothing is self-hosted,
mirrored or repackaged.

| File | When | Size | Cap |
|---|---|---|---|
| `Godot_v4.6.2-stable_macos.universal.zip` | macOS, always | not measured here | 536,870,912 bytes |
| `Godot_v4.6.2-stable_win64.exe.zip` | Windows, always | not measured here | 536,870,912 bytes |
| `Godot_v4.6.2-stable_export_templates.tpz` | only with `--templates` | about 1.25 GB | 1,468,006,400 bytes (1.4 GiB) |
| `Godot_v4.6.2-stable_linux.x86_64.zip`, `..._linux.arm64.zip` | Linux | **refused**: no official SHA-512 for them is pinned in `tools/fetch-manifest.json`, and none is guessed | 536,870,912 bytes once pinned |

From the `.tpz`, setup keeps exactly `web_nothreads_release.zip`, `macos.zip` and `windows_release_x86_64.exe`
(read member by name, never by extracting archive paths), checks each against the sha256 pinned in
`adventure_maker/export.py`, checks `templates/version.txt` reads `4.6.2.stable`, then **deletes the `.tpz`**.
Godot is MIT licensed; its licence and notices ship in `licenses/godot-4.6.2/`. No Blender, Python packages or ffmpeg
are downloaded by this command.

**These URLs come from the official release's checksum list but have not been fetched by this lane.** A 404 fails
closed. HTTP Content-Length is shown during transfer when the server sends it.

## Where it goes

Never into the plugin folder and never into Applications/Program Files:

- macOS: `~/Library/Caches/hermes64/godot/4.6.2/darwin/Godot.app/Contents/MacOS/Godot`;
  templates: `~/Library/Caches/hermes64/templates/4.6.2.stable/`
- Windows: `%LOCALAPPDATA%\hermes64\godot\4.6.2\windows\Godot_v4.6.2-stable_win64.exe`;
  templates: `%LOCALAPPDATA%\hermes64\templates\4.6.2.stable\` (fallback when LOCALAPPDATA is absent: the user's
  `AppData\Local\hermes64`). The console exe from the zip is not substituted for the standard exe.
- Linux (after a maintainer adds the pin): `~/.cache/hermes64/godot/4.6.2/linux-x86_64/` (or `linux-arm64`;
  `$XDG_CACHE_HOME` when set). The code path is in place (verify, unpack, mark only the verified file
  executable, run `--version` once); until the pin exists every Linux fetch is refused before any connection.
  Installing Godot by hand and adding the pin: [LINUX.md](LINUX.md).

The Godot finder used by setup, doctor, play and export checks the integrity-checked cache before its ordinary
defaults. **An explicit `godot_path` always wins**; setup warns about a stale one and never changes your settings.
The exporter uses Godot's own export_templates folder first and the fetched templates second, and only when their
bytes match the pinned sha256. A cache receipt records the editor's archive pin, version and file hashes; a changed
or partial cache is not reused. Remove a version's cache folder to uninstall. No registry or system-wide changes.

The finder that reads this cache is `platforms.godot_candidates` (`docs/GODOTFETCH-WINDOWS-FINDER.patch` is
already applied). The fetch does not enable the Windows child runner, change the Linux runner or weaken any
sandbox gate.

## Verification, Gatekeeper and failures

- HTTPS only, normal TLS certificate checks, proxies disabled. A pinned file's own URL must be exactly an asset
  under the official `godot-builds` 4.6.2-stable release; redirects may go only to `github.com`,
  `objects.githubusercontent.com` or `release-assets.githubusercontent.com` on port 443. No userinfo, no other host,
  no HTTPS-to-HTTP downgrade, at most five redirects.
- Each transfer has a 600-second budget, a five-second socket inactivity timeout and its byte cap. This restarts
  cleanly; it does not Range-resume.
- A truncated transfer, 404, interruption or wrong SHA-512 deletes the partial file. A mismatch never reaches
  unpacking, quarantine removal or execution.
- Archives are checked before anything is read out: no traversal, absolute or drive paths, backslashes,
  symlinks/devices or duplicate names; at most 4,096 entries. Editor zip: 536,870,912 bytes per member, 1 GiB total.
  `.tpz`: 600 MiB per member. Work happens in a temporary folder in your cache; failed attempts are cleaned up.
- macOS: after verification and safe extraction, setup runs `/usr/bin/xattr -r -d com.apple.quarantine` **only on
  the newly verified Godot.app**. It does not disable Gatekeeper or change signing policy. Real Gatekeeper behaviour
  on a fresh Mac is not verified.
- The only downloaded-engine execution during setup is `<verified executable> --version` (15 s timeout, no shell,
  no project), which must report `4.6.2.stable`. Setup never opens the editor or a game.

If a run is killed so abruptly that Python cannot clean up, a `.fetch-*` folder can remain in the cache; the next
attempt uses a new one. Do not run two setup fetches at once.
