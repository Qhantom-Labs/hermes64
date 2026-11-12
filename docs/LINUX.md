# Hermes64 on Linux

**Status: authoring is implemented behind bubblewrap and is not verified on Linux.** Everything below was built and
checked on a Mac by simulation (`tests/test_linux_platform.py`: fake bubblewrap, fake file systems, the real run loop
with a local stand-in child). No Linux computer has run it yet. The first real run follows
[LINUX-TEST-SHEET.md](LINUX-TEST-SHEET.md); its receipt goes under `docs/receipts/` and only then can this page say
more. Evidence rules: [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md).

## What you need

| Item | Version | Notes |
|---|---|---|
| Hermes Agent | `>=0.18.2` (manifest floor) | Install by repository, see below |
| Python | 3.9+ (3.11+ recommended) | `numpy>=2.0,<3` required for builds; `Pillow>=11.3,<14` for JPEG references |
| bubblewrap (`bwrap`) | 0.4 or newer | The child sandbox; without it, making games is off (see "The child sandbox") |
| Godot | **4.6.2** standard build, `x86_64` or `arm64` | Installed by hand on Linux (see "Install Godot by hand") |
| Blender | optional | `builder=auto` uses the Python builder when Blender is absent |
| ffmpeg | optional | Only for importing your own FLAC/M4A/Opus/AIFF audio |
| git | any | `hermes plugins install` clones the repository |

Install the system pieces with your package manager, for example Debian/Ubuntu:
`sudo apt install bubblewrap git python3 python3-venv`; Fedora: `sudo dnf install bubblewrap git python3`;
Arch: `sudo pacman -S bubblewrap git python`.

## Install the plugin

```sh
hermes plugins install Qhantom-Labs/hermes64 --enable
```

Use the `owner/repo` form on Linux. An install by the bare catalog name (`hermes plugins install hermes64`) follows
the Hermes catalog entry's platform list, which is set in the catalog, not in this repository, and may not include
Linux while Linux is unverified; Hermes refuses such an install with "unavailable on linux". Approve numpy and Pillow
when Hermes asks;
if it says dependency install was skipped, run `hermes plugins enable hermes64` in a terminal. Restart Hermes and
start a **new** chat.

Release zip instead: your Hermes home is `~/.hermes` unless `HERMES_HOME` is set (`hermes config path` prints the
config file inside it). Move any older `plugins/hermes64` out of `plugins/` first, then:

```sh
ZIP=/home/you/Downloads/hermes64-XXXX.zip      # the file you downloaded
sha256sum "$ZIP"                               # must equal the published SHA-256
mkdir -p ~/.hermes/plugins
python3 -m zipfile -e "$ZIP" ~/.hermes/plugins
python3 -B ~/.hermes/plugins/hermes64/tools/check_install.py
hermes plugins enable hermes64
```

The checklist, run from the plugin folder (it prints `READY` or what to fix, one line each):

```sh
cd ~/.hermes/plugins/hermes64 && python3 -B -m adventure_maker.doctor --linux-checklist
```

In a chat, `/hermes64 setup` shows the same items, including a **Child runner** row.

## The child sandbox (bubblewrap)

On macOS every Godot, Blender and Python child runs under `sandbox-exec`. On Linux the same rule is enforced with
bubblewrap: each child gets its own user, mount, PID, IPC, UTS and network namespaces. Inside, there is no network
(only an isolated loopback), the system folders are read-only, your home folder is not visible, and the game project
is the only writable folder. The child and everything it starts are killed when the run ends, times out (180 s at
most) or prints more than 1 MiB. Limits: 16 GiB address space, 4,096 open files, no core files, a process cap.
Design and exact flags: [LINUX-RUNNER-DESIGN.md](LINUX-RUNNER-DESIGN.md).

Hermes64 checks once per session that bubblewrap really works (a tiny sandboxed probe: write inside allowed, write to
`/usr` denied, a host file hidden, a network connect refused). If anything fails, **every child is refused** with
`sandbox_unavailable` and a sentence that says what is missing:

| Message names | Fix |
|---|---|
| bubblewrap not installed | `sudo apt install bubblewrap` (or your distribution's package) |
| Ubuntu AppArmor (`kernel.apparmor_restrict_unprivileged_userns=1`, Ubuntu 23.10/24.04) | the AppArmor profile below |
| `kernel.unprivileged_userns_clone=0` | `sudo sysctl -w kernel.unprivileged_userns_clone=1` (persist it in `/etc/sysctl.d/`) |
| `user.max_user_namespaces=0` | `sudo sysctl -w user.max_user_namespaces=15000` (persist it in `/etc/sysctl.d/`) |
| a container | run Hermes on the host, or allow user namespaces in the container |
| WSL 1 | WSL 2 (`wsl --set-version <distro> 2`) |
| the probe saw the network or wrote outside | nothing to toggle: report it; Hermes64 will not use that sandbox |

### Ubuntu 24.04

Ubuntu blocks unprivileged user namespaces unless the program has an AppArmor profile that allows them. Give
`/usr/bin/bwrap` one: save this as `/etc/apparmor.d/bwrap` (with `sudo`), then run
`sudo apparmor_parser -r /etc/apparmor.d/bwrap`.

```text
abi <abi/4.0>,
include <tunables/global>

profile bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,

  include if exists <local/bwrap>
}
```

This lets bubblewrap (and so any program run through it) create user namespaces again; the rest of Ubuntu's
restriction stays. The system-wide alternative, `sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`,
switches the restriction off for every program. Either choice is yours; restart Hermes afterwards.

### Unconfined opt-in (weaker, explicit)

If bubblewrap cannot work on your computer, you can knowingly turn on the unconfined runner:

```sh
export HERMES64_LINUX_RUNNER=unconfined     # in the environment Hermes starts with, then restart Hermes
```

Children then run **without bubblewrap: no OS-enforced network or write confinement; process-group kill and rlimits
only.** A child that starts its own session can outlive the run. Doctor, `/hermes64 setup`, the `/hermes64 new` reply
and every run result say so. When bubblewrap works, it is used even if the variable is set. Only the exact value
`unconfined` counts.

## Install Godot by hand

`/hermes64 setup --fetch` is **refused on Linux** in this release: the plugin downloads only files whose official
SHA-512 is pinned in `tools/fetch-manifest.json`, and no Linux archive is pinned yet (see "Adding the Linux pin").
Install Godot 4.6.2 yourself:

```sh
cd ~/Downloads
# From https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable download
#   Godot_v4.6.2-stable_linux.x86_64.zip   (or Godot_v4.6.2-stable_linux.arm64.zip on ARM)
#   SHA512-SUMS.txt
sha512sum --check --ignore-missing SHA512-SUMS.txt     # must print: Godot_v4.6.2-stable_linux.x86_64.zip: OK
python3 -m zipfile -e Godot_v4.6.2-stable_linux.x86_64.zip ~/.local/bin
chmod +x ~/.local/bin/Godot_v4.6.2-stable_linux.x86_64
~/.local/bin/Godot_v4.6.2-stable_linux.x86_64 --headless --version   # 4.6.2.stable.official.<hash>
```

Hermes64 finds the official file name by itself in `/usr/local/bin`, `/usr/bin`, `/opt/godot`, `/opt`,
`~/.local/bin`, `~/bin`, `~/Applications`, `~/Godot` and `~/Downloads`; otherwise set the plugin setting
`godot_path`, or `HERMES64_GODOT`, to the file. A distribution's `godot` package is tried after the official name and
must still be 4.6.2 (exports check the version).

**snap and flatpak** Godot or Blender builds are not used: they start through their own sandbox launcher, which is
not expected to work inside bubblewrap and would not see your project folder. Discovery skips them and says so; an
explicit path to one is refused. Use the official builds.

Python: point `python_path` (or `HERMES64_PYTHON`) at a real interpreter that has numpy in its own site-packages,
such as a virtual environment's `bin/python3`. Do not point it at a pyenv or asdf **shim**: shims are shell scripts
that need your home folder, which the sandbox hides. Children run Python with `-I`, so user-site packages do not
count (the same as on macOS).

## What works, and what does not

| Feature | Linux status |
|---|---|
| `/hermes64 new`, the create flow, edit, check, replay, build assets, bot playtest | implemented (inside bubblewrap), not verified |
| Export `web` | implemented, not verified; play it in a browser from a local server |
| Export `windows` | implemented (the same cross-export a Mac does), not verified |
| Export `macos` | refused with one sentence: the macOS target needs a Mac (codesign) |
| Native Linux export | **not supported yet**: no Linux export template is pinned or kept |
| Screenshots, measured style audit | skipped: authoring is headless (no display inside the sandbox) and reported as skipped |
| Studio (Desktop tab) shelf and web play | same code as macOS; not run on Linux |
| Godot fetch (`setup --fetch`) | refused until a Linux SHA-512 pin exists |

Web exports need a browser and a local server on 127.0.0.1 (Studio Play does this, or
`python3 -m http.server --bind 127.0.0.1 8000 --directory <export folder>/web`). Godot needs no network at run time.
Export templates: put the official `4.6.2.stable` templates in `~/.local/share/godot/export_templates/4.6.2.stable/`
(or `HERMES64_TEMPLATES`); each template file is checked against its pinned hash before use, and the export uses a
hash-checked copy inside the project, because the sandbox hides your home folder.

Same as on macOS: some character, preview and audio helpers run outside the central runner (they are not sandboxed
on either system; [PLATFORM-PARITY.md](PLATFORM-PARITY.md)).

Skills: Hermes shows a skill only on the systems its `platforms` field names. The core `hermes64` skill and the
create, places, generators, hub and audio skills are shown on Linux; `hermes64-author`, `-characters`, `-cover`,
`-gameplay-modules` and `-playtest-and-ship` still declare macOS only (they contain macOS or repository-only
commands), so Hermes does not offer them on Linux. The tools they describe still work.

## Adding the Linux pin (maintainers)

The Linux fetch code is in place (`adventure_maker/godot_fetch.py`: `LINUX`, cache `~/.cache/hermes64/godot/4.6.2/
linux-<arch>/`, mark-executable, `--version` only). It stays refused until `tools/fetch-manifest.json` has the rows
below. Never type a hash from memory or from a third-party site:

1. Download `SHA512-SUMS.txt` from the official release
   (`https://github.com/godotengine/godot-builds/releases/download/4.6.2-stable/SHA512-SUMS.txt`) and the archive.
2. `sha512sum Godot_v4.6.2-stable_linux.x86_64.zip` must equal that file's line for the archive; cross-check the line
   against a second official copy (the release page on godotengine.org).
3. Add the artifact, shaped like `godot-4.6.2-windows-editor`:
   - `godot-4.6.2-linux-x86_64-editor`: archive `Godot_v4.6.2-stable_linux.x86_64.zip`, url
     `https://github.com/godotengine/godot-builds/releases/download/4.6.2-stable/Godot_v4.6.2-stable_linux.x86_64.zip`
   - `godot-4.6.2-linux-arm64-editor`: archive `Godot_v4.6.2-stable_linux.arm64.zip`, same pattern.
4. Run the tests (`tests/test_linux_platform.py` expects no Linux row today and must be updated in the same change)
   and record a receipt of the first real fetch.

## Tested by the owner

Not yet.
