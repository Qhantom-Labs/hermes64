# Hermes64 Windows receipt (template)

Copy this file to `docs/receipts/windows/<YYYY-MM-DD>-<machine alias>/RECEIPT.md` and fill it from the files the
[Windows test sheet](../WINDOWS-TEST-SHEET.md) wrote to `$R\outputs\`; put those files next to it in `outputs\`.
Write what happened, not what was expected. No user names, PC names, tokens, `.env` or `config.yaml` content
(replace them with `<user>` / `<pc>`). A maintainer, not the tester, updates `WINDOWS.md`, `PLATFORM-PARITY.md`
and `PLATFORM-EVIDENCE.md` from it.

## Run

| Field | Value |
|---|---|
| Date (UTC) | |
| Tester (person or agent role) and who approved each command | |
| Machine alias (not the PC name) | |
| Windows edition, version and build (`winver` / step A1) | |
| CPU architecture | |
| Graphics adapter and driver (step A1) | |
| PowerShell version | |
| Python used (`py -0p` / path), numpy, Pillow | |
| Hermes version (`hermes --version`) and Hermes home folder (`hermes config path`) | |
| Plugin commit (zip SHA-256 and `PACKAGE-MANIFEST.json` source commit, or `git rev-parse HEAD`) | |
| `HERMES64_WINDOWS_RUNNER` value (step B) | |
| Godot version and how it was installed (setup --fetch / by hand) | |
| Export templates present (web, windows) | |
| Blender (optional): version and path, or "absent" | |
| ffmpeg (optional): version or "absent" | |

## Steps

| Step | Result (PASS / FAIL / SKIPPED) | Output file | Notes (exact error line on FAIL) |
|---|---|---|---|
| A1 machine facts | | `a1-machine.txt` | |
| A2 versions | | `a2-versions.txt` | |
| B3 runner opt-in set | | `b3-runner.txt` | |
| C4 package hash and unzip | | `c4-unzip.txt` | |
| C5 check_install | | `c5-check-install.txt` | |
| C6 Windows checklist | | `c6-checklist.txt` | |
| C7 enable in Hermes, `/hermes64 setup` line | | `c7-setup.txt` | |
| D8 Godot fetch plan / fetch (owner typed) | | `d8-fetch.txt` | |
| D9 runner checks (tree kill, no window flash, env) | | `d9-runner.txt` | |
| D10 bundled example (demo) | | `d10-demo.txt` | |
| D11 `/hermes64 new` | | `d11-new.txt` | |
| D12 playtest and exports (web, windows; macOS refusal) | | `d12-export.txt` | |
| D13 Blender discovery (if installed) | | `d13-blender.txt` | |
| E14 play the Windows export | | screenshot | |
| E15 web build in a browser | | screenshot | |
| E16 Studio: PLAY WINDOWS BUILD | | screenshot | |

## Summary

- Windows authoring on this PC: **works / works with these failures / does not work** (pick one, then list).
- Local changes made to the plugin or to Hermes (attach the patch files; "none" if none):
- Anything not run, and why:
