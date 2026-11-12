# Platform parity: macOS, Windows and Linux

**Linux: two real runs on Debian 13/bwrap 0.12.0: run 1 failed (fixed), run 2 authoring built, played and exported games with two remaining failures (fixed in this candidate, awaiting run 3). Windows 11: one real run: runner/exports pass, bundled demo failed on Blender 4.5 (fixed in this candidate), game not played by a human. Not verified.** Linux "played" means bots. macOS retains its development-Mac acceptance; nothing here upgrades another platform.

Receipt custody and exact limitations: [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). Rerun sheets: [Linux](LINUX-TEST-SHEET.md), [Windows](WINDOWS-TEST-SHEET.md). Tested by the owner: **Not yet.**

## Implementation versus real evidence

| Feature | Windows path | Linux path | macOS path | Real receipt / remaining gap |
|---|---|---|---|---|
| Install / load | Git clone or checksum-checked ZIP + Expand-Archive/robocopy; old-host adapter | owner/repo install or ZIP; bare catalog name may exclude Linux | repository install / ZIP | Windows 0.18.2 enabled plugin, chat model 404 blocked chat tests. Linux Hermes absent, integration not run. No nonexistent install `--ref` flag. |
| `check_install` | `py tools\check_install.py`; strict hashes, CRLF/long-path diagnostics | `python3 tools/check_install.py` | same | Windows clone failed, ZIP passed. `.gitattributes` was in development source but missing from package; now included with `* -text`. Root `.git/` metadata ignored, nested extras still warn. |
| Doctor/setup | Job Object row; Blender version + visible warning outside 5.2.1 | Real Runner confinement readiness + separate real tiny rendered PNG probe; exact missing-display fix | existing rows unchanged | Windows C6 lacked version check. Linux run 2 B5 real-runner child passed, but D10 exposed missing display; new capture readiness awaits run 3. |
| Discovery | env/settings overrides; Program Files, winget/scoop/Steam/portable Blender | official Godot names, `/usr`, `/opt`, user folders/tarballs; snap/flatpak refused | Homebrew, `/Applications`, PATH | Automatic non-Mac Blender discovery prefers measured 5.2.1, then compatibility candidates. Explicit override wins. Mac order and character-exporter selection unchanged. |
| Create/edit/assets/bots | Opt-in Job Object | bubblewrap default; explicit unconfined fallback | sandbox-exec | Linux run 2 demo/new/bots pass, D10 failed only capture/report. Windows Python-builder diagnostic passes; default 4.5 demo failed, candidate fix needs native rerun. |
| Materials | 4.2–4.5 LTS compatibility repair, 5.x path | same code | 5.2.1 path preserved | Enable `use_nodes` only if tree is None. 5.2.1 verified on Mac; 4.5 LTS fix untested on a real run until the Windows re-run. |
| Rendered style/N64 | interactive desktop | Private Xvfb inside sandbox + Compatibility/OpenGL3 software rendering; no host socket/auth bind | existing Aqua window path | Godot headless uses a dummy renderer, not evidence of visual fidelity. On missing/failed Linux capture probe: both gates not_run with reason, CREATE-REPORT.md still written. No false pass. |
| Export windows | exe+pck+zip, headless boot smoke | cross-export | cross-export | Windows D12 diagnostic project boot passed; Linux run 2 exported. Candidate/default-builder reruns pending; human play absent. |
| Export web | same exporter | same exporter; template copy inside project | same, Studio loopback server | Both real runs exported; no human browser picture/audio tested. |
| Export macos | explicit refusal (codesign needs Mac) | same refusal | signed local app | Both receipts recorded intended refusal. |
| Native Linux export | n/a | not supported (no template pinned) | n/a | No new target or pin added. |
| Studio | checked-path shelf, PLAY WINDOWS BUILD + explicit confirmation | same common backend | descriptor shelf, PLAY MACOS BUILD | Native PC shelf/launch and human E16 not run. |
| Audio import | sanitized ffmpeg child, no console | parent PATH/common folders; scrubbed child | Homebrew/PATH | Linux ffmpeg 7.1.5 found in run 2. Full native audio import not exercised. |
| Godot fetch | pinned Windows archive, explicit consent | refused until Linux pin is separately added | pinned universal archive | PC reused existing engine/templates. No fetch in this lane, no pin/catalog edits. |
| Runner | suspended Job assignment, tree cleanup, 64 processes/8 GB, private folders; **no OS network/write confinement** | namespaces, no network, hidden home, read-only system, project-only host write, outer safe limits then inner NPROC | existing sandbox policy and process-group cleanup | Windows D9 6/6; Linux C7 11/12 only PWD failure. Fork exhaustion/memory exhaustion unmeasured. |
| Children outside Runner | sanitized version/probe/preview/ffmpeg helpers | same; capture itself stays in Runner | existing behavior | Sanitization is not OS confinement; child-environment audit lists sites and intentional exceptions. |
| Runtime/save | GL Compatibility, `%APPDATA%\Hermes64\<id>` | web build; no native Linux target | existing custom user folder | Windows headless boot is not human graphics/audio/save acceptance. |

## Safety and preservation

- Every platform keeps relative-path/NTFS-reserved-name, traversal, symlink/reparse and guarded project rules in `safety.py`.
- Linux still fails closed without working bwrap unless the owner knowingly opts into `HERMES64_LINUX_RUNNER=unconfined` (no OS-enforced network/write confinement). READY requires the real confined runner child, not fallback availability.
- NPROC remains an inner brake (visible namespace tasks + 512, inherited ceilings clamped). PID-namespace teardown is lifetime cleanup, not a task-count cap. Run 2 observed 514 inside / 63991 unchanged outside; bounded fork exhaustion was skipped on the shared machine.
- The C7 allowlist adds only PWD, generated by bwrap 0.12.0. Provider/Hermes variables remain forbidden. Display wrapper adds only its own private DISPLAY and software-GL flag after sanitization.
- No changes to `runtime/godot/**`, Mac sandbox policy/environment/argv, template/fetch pins, catalog yaml, or exporter-parity verdict. Existing parity was already STALE; changing blendio's source fingerprint must not falsely refresh it.

## Local tests, not native acceptance

`tests.test_platforms2` covers Blender tree-None and 5.x no-touch controls; version/discovery/warnings; manifest/CRLF/Git checkout/publish-tree preservation; PWD with secret negative controls; Xvfb route argv, sanitized real stand-in children, real-run capture protocol failures; create/report no-display continuation.

Related suites include `test_linuxfix`, `test_linux_platform`, `test_windows_paths`, `test_windows_lane_fixes`, `test_platform_parity`, `test_reviewfix_childenv`, `test_windows_gate`, package/registration/catalog/hub/schema and affected create/audit/builder suites. Full executed counts and asset/replay/output digest results are in repository-only `docs/PLATFORMS2-RESULT.md`.

## Not verified

This exact candidate on real Windows/Linux; Linux Xvfb/Mesa rendering and fork-cap exhaustion; Windows 4.5 default builder; human console flash, graphics/audio/save and Studio play; Linux Hermes integration. Simulation, Mac output preservation and a successful headless boot do not accept those paths.
