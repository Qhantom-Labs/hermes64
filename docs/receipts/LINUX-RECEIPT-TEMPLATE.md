# Hermes64 Linux receipt (template)

Copy this file to `docs/receipts/linux/<YYYY-MM-DD>-<machine alias>/RECEIPT.md` and fill it from the files the
[Linux test sheet](../LINUX-TEST-SHEET.md) wrote to `$R/outputs/`; put those files next to it in `outputs/`.
Write what happened, not what was expected. No user names, host names, tokens, `.env` or `config.yaml` content.
A maintainer, not the tester, updates `LINUX.md`, `PLATFORM-PARITY.md` and `PLATFORM-EVIDENCE.md` from it.

## Run

| Field | Value |
|---|---|
| Date (UTC) | |
| Tester (person or agent role, no personal names needed) | |
| Machine alias (not the host name) | |
| Physical / VM / container / WSL 2 | |
| Distribution and version (`/etc/os-release`) | |
| Kernel and architecture (`uname -srm`) | |
| `kernel.unprivileged_userns_clone` | |
| `user.max_user_namespaces` | |
| `kernel.apparmor_restrict_unprivileged_userns` | |
| AppArmor profile for bwrap added? (yes / no / not needed) | |
| bubblewrap version | |
| Python version, numpy, Pillow (`$PY`) | |
| Hermes version (`hermes --version`) | |
| Plugin commit (`git rev-parse HEAD`, or the zip's SHA-256 and `PACKAGE-MANIFEST.json` source commit) | |
| Godot version (`--headless --version`) and archive checksum result | |
| Export templates present (web, windows) | |
| Blender (optional): version or "absent" | |
| ffmpeg (optional): version or "absent" | |

## Steps

| Step | Result (PASS / FAIL / SKIPPED) | Output file | Notes (exact error line on FAIL) |
|---|---|---|---|
| A1 machine facts | | `a1-machine.txt` | |
| A2 versions | | `a2-versions.txt` | |
| A3 Godot + templates checksums | | `a3-sha512.txt` | |
| B4 check_install | | `b4-check-install.txt` | |
| B5 Linux checklist (runner line copied whole) | | `b5-checklist.txt` | |
| C7 probes: `RESULT` line copied whole | | `c7-probe.txt` | |
| C7 `INFO fork count` | | `c7-probe.txt` | |
| D8 bundled example (demo) | | `d8-demo.txt` | |
| D9 `/hermes64 new` path | | `d9-new.txt` | |
| D10 create flow | | `d10-create.txt` | |
| D11 playtest, web, windows, macOS refusal | | `d11-export.txt` | |
| D12 web build in a browser | | screenshot | |
| E13 inside Hermes: setup row and `/hermes64 new` | | screenshot or copied reply | |
| F14 fail closed / unconfined / bwrap wins | | `f14-*.txt` | |
| F15 userns off (optional, sudo) | | `f15-userns-off.txt` | |

## Summary

- Linux authoring on this machine: **works / works with these failures / does not work** (pick one, then list).
- Anything the tester changed on the machine (packages, AppArmor profile, sysctl) and whether it was undone:
- Anything not run, and why:
