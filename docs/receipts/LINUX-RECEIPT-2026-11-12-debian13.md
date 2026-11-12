# Hermes64 Linux receipt

The source receipt is copied below without changing its recorded results. Referenced raw output attachments were
not supplied with this handoff and are not present here. Personal paths are represented as `/home/<user>`; `box`
is the tester's machine alias, not a hostname. Candidate fixes and pending retest are documented separately.


## Run

| Field | Value |
|---|---|
| Date (UTC) | 2026-11-12T14:54:20Z start (A1); finished 2026-11-12T14:57:31Z |
| Tester (person or agent role, no personal names needed) | Grok Bot (Linux test-sheet executor on the box) |
| Machine alias (not the host name) | box (shared Debian 13 VM) |
| Physical / VM / container / WSL 2 | VM (A1: not-a-container, not-WSL) |
| Distribution and version (`/etc/os-release`) | Debian GNU/Linux 13 (trixie); VERSION_ID=13; DEBIAN_VERSION_FULL=13.7 |
| Kernel and architecture (`uname -srm`) | Linux 6.12.113+ x86_64 |
| `kernel.unprivileged_userns_clone` | `sysctl -n` printed `absent` (`sysctl: command not found`). `/proc/sys/kernel/unprivileged_userns_clone` also absent. |
| `user.max_user_namespaces` | `sysctl -n` printed `absent` (`sysctl: command not found`). `/proc/sys/user/max_user_namespaces` = 63991. `unshare --user --map-root-user` succeeded. |
| `kernel.apparmor_restrict_unprivileged_userns` | `sysctl -n` printed `absent` (`sysctl: command not found`). `/proc/sys/kernel/apparmor_restrict_unprivileged_userns` also absent. `/sys/kernel/security/apparmor` absent. |
| AppArmor profile for bwrap added? (yes / no / not needed) | no / not needed (no AppArmor filesystem; dmesg had no bwrap denial). No sudo AppArmor profile was applied. |
| bubblewrap version | bubblewrap 0.12.0 (`/usr/bin/bwrap`) |
| Python version, numpy, Pillow (`$PY`) | 3.13.5, numpy 2.5.4, Pillow 13.0.0 (venv at `$T/venv`) |
| Hermes version (`hermes --version`) | not installed: `hermes: command not found` |
| Plugin commit (`git rev-parse HEAD`, or the zip's SHA-256 and `PACKAGE-MANIFEST.json` source commit) | `6af4ba269892d42fb37dd5d5152dbfcccf05f27d` (git checkout of `post-submission/platforms`; `b4-commit.txt`) |
| Godot version (`--headless --version`) and archive checksum result | `4.6.2.stable.official.71f334935`. Both official archives: `OK`. Official URLs: `https://github.com/godotengine/godot-builds/releases/download/4.6.2-stable/Godot_v4.6.2-stable_linux.x86_64.zip`, `.../Godot_v4.6.2-stable_export_templates.tpz`, `.../SHA512-SUMS.txt` (release tag `https://github.com/godotengine/godot-builds/releases/tag/4.6.2-stable`). |
| Export templates present (web, windows) | yes: `version.txt` (contents `4.6.2.stable`), `web_nothreads_release.zip`, `windows_release_x86_64.exe` in `~/.local/share/godot/export_templates/4.6.2.stable` |
| Blender (optional): version or "absent" | absent |
| ffmpeg (optional): version or "absent" | Host has `ffmpeg version 7.1.5-0+deb13u1`. The Linux checklist still printed `absent   ffmpeg (optional: FLAC/M4A/Opus/AIFF audio import)`. |

## Steps

| Step | Result (PASS / FAIL / SKIPPED) | Output file | Notes (exact error line on FAIL) |
|---|---|---|---|
| A1 machine facts | PASS | `a1-machine.txt` | Distribution, kernel, and three sysctl lines are present. All three sysctl keys printed `absent` because `sysctl` is not installed; `/proc` values are in `a1-proc-notes.txt` (not part of the sheet block). Memory at A1: 16002 MiB total, 4471 MiB available. No OOM later. |
| A2 versions | FAIL | `a2-versions.txt` | bwrap 0.12.0, Python 3.13.5, numpy 2.5.4, Pillow 13.0.0, and git 2.47.3 are OK. The `hermes --version` line is `hermes: command not found`. Continued the rest of the sheet. Did not `sudo apt install` (bwrap, git, python3, venv, unzip already worked). |
| A3 Godot + templates checksums | PASS | `a3-sha512.txt` | `Godot_v4.6.2-stable_export_templates.tpz: OK` and `Godot_v4.6.2-stable_linux.x86_64.zip: OK`. Version string `4.6.2.stable.official.71f334935`. Three template files listed by `ls -l`. |
| B4 check_install | PASS | `b4-check-install.txt` | `PASS  hermes64 1.0.0-rc at /home/<user>/h64-test/plugin/hermes64: 5968/5968 files verified (sha256), cameo not in package, source f7939a8f9896 (clean tree)`. This git tree did include a package manifest (unlike the sheet's typical "missing" case). WARN lines are only extra `.git/` files from the clone. |
| B5 Linux checklist (runner line copied whole) | PASS | `b5-checklist.txt` | No `SIMULATED` line. Runner line: `OK       Child runner (bwrap): Linux bubblewrap sandbox: no network, writes confined to the project folder, home folder hidden, process tree killed at the end of each run.` Godot OK at the step-3 binary. numpy OK. Last line: `RESULT  READY to make games`. This probe does not use the rlimit shim; later official children failed anyway (see C7 / Summary). |
| C7 probes: `RESULT` line copied whole | FAIL | `c7-probe.txt` | Ran with `--no-fork` because this machine is shared with other agents (mandatory deviation; expect 12/12, not 13/13). First line: `ISOLATION bwrap | Linux bubblewrap sandbox: no network, writes confined to the project folder, home folder hidden, process tree killed at the end of each run.` Last line: `RESULT FAIL (4/12 checks passed)`. Children failed with `FAULT:sandbox_unavailable`. Exact timeout line: `FAIL timeout kills setsid child   FAULT:sandbox_unavailable after 2.0s; leftovers=[]`. Full Fault text from a follow-up diagnostic (`c7-diag-sandbox-unavailable.txt`, not a sheet step): `The Linux bubblewrap sandbox could not start this child: bwrap: Creating new namespace failed: Resource temporarily unavailable`. No `.process.json` files were produced. |
| C7 `INFO fork count` | SKIPPED | `c7-probe.txt` | `--no-fork` was added; there is no `INFO fork count` line. |
| D8 bundled example (demo) | FAIL | `d8-demo.txt` | `HERMES64 DEMO FAILED: {"code": "demo_compile", "message": "{\"ok\": false, \"error\": {\"code\": \"sandbox_unavailable\", \"message\": \"The Linux bubblewrap sandbox could not start this child: bwrap: Creating new namespace failed: Resource temporarily unavailable\"}}"}` |
| D9 `/hermes64 new` path | FAIL | `d9-new.txt` | `"ok": false`, `"created": true`, `"assets_built": false`, no `play_command`. Error: `"code": "new_compile"`, `"message": "Compile failed: The Linux bubblewrap sandbox could not start this child: bwrap: Creating new namespace failed: Resource temporarily unavailable. The half-made project stays at /home/<user>/h64-test/games/fox1; inspect it, or pass --name to start fresh."` |
| D10 create flow | FAIL | `d10-create.txt` | Stages `project`/`brief`/`gaps`/`style`/`mood` done; `assets` failed before `playtest`. `CREATE-REPORT.md` was not created. Exact stage line: `create: create_assets: Fault: The Linux bubblewrap sandbox could not start this child: bwrap: Creating new namespace failed: Resource temporarily unavailable Next: read the traceback with --debug; resume runs this stage again` |
| D11 playtest, web, windows, macOS refusal | FAIL | `d11-export.txt` | Playtest, web, and windows failed because D9 never built: `No current build; compile a source spec first`. macOS refusal was as specified: `ok=False {"code": "export_target", "message": "The macos target needs a Mac (local ad-hoc signing with codesign); export web and windows here, or export macos on a Mac. Nothing was exported."}` No share path was produced. |
| D12 web build in a browser | SKIPPED | (none) | No browser/desktop on this computer. Web export did not succeed, so there was no share path to serve or play. Did not claim picture or sound. |
| E13 inside Hermes: setup row and `/hermes64 new` | SKIPPED | (none) | Hermes is not installed on this computer, and installing it was not approved. Did not install Hermes. |
| F14 fail closed / unconfined / bwrap wins | PASS | `f14-off.txt`, `f14-unconfined.txt`, `f14-bwrap-wins.txt` | (1) `f14-off.txt`: `ISOLATION off`, names bubblewrap as not installed (the `--unconfined-sim` stub) plus the opt-in, and `RESULT runner off: no child was started`. (2) `f14-unconfined.txt`: `ISOLATION unconfined` with `no OS-enforced network or write confinement; process-group kill and rlimits only`; network/write probes skipped; env and rlimits passed; setsid line failed as the sheet says may happen (`FAIL timeout kills setsid child   1 after 2.0s; leftovers=[]`); probe `RESULT FAIL (2/3 checks passed)`. (3) `f14-bwrap-wins.txt` still shows `OK       Child runner (bwrap): Linux bubblewrap sandbox: no network, writes confined to the project folder, home folder hidden, process tree killed at the end of each run.` and `RESULT  READY to make games` (working bwrap wins over the opt-in). F14 commands already included `--no-fork`. |
| F15 userns off (optional, sudo) | SKIPPED | (none) | Not run. Optional sudo `sysctl -w user.max_user_namespaces=0` can break other sandboxed programs on this shared machine. |

## Summary

- Linux authoring on this machine: **does not work**. The doctor checklist printed `RESULT  READY to make games` with `Child runner (bwrap)` OK, and a direct `bwrap` (and the plugin probe, which does not use the rlimit shim) can start a user namespace. Every official child started through the plugin runner still failed with `sandbox_unavailable`: `bwrap: Creating new namespace failed: Resource temporarily unavailable`. That blocked the C7 confined probes and the D8–D11 demo / new / create_flow / playtest / web / windows export path. No game was compiled or exported. Diagnostic only (not a sheet step; plugin code was not changed): `c7-diag-shim-vs-direct.txt` shows the same bwrap argv succeeding without the shim, and succeeding with the shim when `RLIMIT_NPROC` is omitted, but failing with the official shim limits (`RLIMIT_NPROC` was `user_process_count() + 512`, 680 at that moment; this uid already had 168 processes). The host `nproc` ceiling was 63991. This is reported as observed, not as a patch.

- Anything the tester changed on the machine (packages, AppArmor profile, sysctl) and whether it was undone: No packages were installed (`sudo apt` was not run). No AppArmor profile was added. No sysctl was changed. Official Godot 4.6.2 and the three listed export-template files were installed under `~/.local/bin` and `~/.local/share/godot/export_templates/4.6.2.stable` as the sheet directs. A Python venv with numpy and Pillow was created at `$T/venv`. All other work stayed under `$T`. The plugin git checkout was not modified, committed, or pushed. The Nous catalog PR was not touched.

- Anything not run, and why:
  - A2 `hermes --version`: Hermes is not installed (recorded as the A2 FAIL line; the rest of A2 continued).
  - C7 fork-storm probe: `--no-fork` on this shared machine.
  - D12 visual/audio play of a web build: no browser/desktop, and no web export was produced.
  - E13 inside Hermes: Hermes is not installed; install was not approved.
  - F15 optional sudo userns cap: skipped so other sandboxed programs are not broken.
  - No Windows/Linux "verified" or "Tested by the owner" docs were edited.
