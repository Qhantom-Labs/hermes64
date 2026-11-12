# Platform parity: macOS, Windows and Linux

**Linux: three real Debian 13/bwrap 0.12.0 runs; run 3 reached C7 12/12 and private-Xvfb rendering, but D10 capture classification and subsequent D11 calls failed. Candidate repairs await a fourth run. Windows 11: one real run; runner/diagnostic exports pass, default Blender 4.5 demo failed, native rerun and human play pending. Linux and Windows: Not verified. Tested by the owner: Not yet.** Linux play means bots. macOS retains its development-Mac acceptance.

Receipt custody and exact limitations: [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). Rerun sheets: [Linux](LINUX-TEST-SHEET.md), [Windows](WINDOWS-TEST-SHEET.md).

## Implementation versus real evidence

| Feature | Windows path | Linux path | macOS path | Real receipt / remaining gap |
|---|---|---|---|---|
| Install / load | clone or checksum-checked ZIP; old-host adapter | owner/repo or ZIP; catalog may exclude Linux | repository / ZIP | Windows old host enabled plugin, model 404 blocked chat. Linux Hermes absent. No invented install commit flag. |
| `check_install` | strict hashes, CRLF/long-path help | same hash checker | same | Windows clone failed, ZIP passed; prior repair includes byte-preserving `.gitattributes`. Default native clone rerun pending. |
| Doctor/setup | Job Object row; Blender version/warning | real Runner confinement readiness plus tiny private-Xvfb PNG | existing rows unchanged | Linux run 3 B5 passes both probes; a tiny pass does not guarantee a later capture. |
| Discovery | overrides; Program Files/winget/scoop/portable | official Godot names, system/user folders; snap/flatpak refused | Homebrew, Applications, PATH | Prior candidate prefers measured Blender 5.2.1 automatically off Mac; explicit choice wins. |
| Create/edit/assets/bots | opt-in Job Object | bwrap default; explicit weaker fallback | sandbox-exec | Linux run 3 demo/new/bots work, D10 produces report/PNGs but mislabels capture. Windows Python-builder diagnostic is not default 4.5 acceptance. |
| Materials | conditional 4.x nodes compatibility repair | same | existing 5.2.1 path | Real Mac 5.2.1 asset bytes retained by prior lane; real 4.5 builder rerun pending. |
| Rendered style/N64 | interactive desktop | private Xvfb + Compatibility/OpenGL3 software GL | existing Aqua path | Run 3 real capture marker/18 PNG names/style pass; D10 false failure fixed by protocol/image checks. Native new verdict still pending; receipt contains no PNG bytes/N64 verdict. |
| Capture verdict | existing Windows behavior | exit + marker + room coverage + expected PNGs/CRC/decode/nonblank primary frames; narrow benign stderr list | existing behavior unchanged | Script/parse/load/crash/signal errors, unknown ERROR, nonzero exit, missing marker/image fail. Style/N64 thresholds unchanged. |
| Automated audio/runtime | existing behavior | Dummy Godot driver; explicit private tmpfs XDG/Pulse runtime; no host sound-device bind | existing behavior unchanged | Run 3 audio fallback created a Pulse runtime link; prevention is a candidate pending native run 4. Manual Play keeps normal audio. |
| Runtime-link cleanup | no exemption | pre-audit and post-run unlink only exact Pulse config-runtime link to same project's controlled tmp/pulse-* | general symlink refusal unchanged | Older affected games repair on next audited call with a note. Arbitrary/outside/source/assets/export links still fail. |
| Export windows | native headless smoke | cross-export | cross-export | Windows diagnostic boot pass; Linux run 3 rendered-game calls fail at path audit, while never-rendered control exports. Rerun after capture required. |
| Export web | same exporter | same exporter | same + Studio loopback | Linux run 3 control exports; human browser picture/audio absent. |
| Export macos | explicit target refusal | same refusal | local signed app | Never-rendered Linux control records correct refusal; rendered game previously failed earlier path guard. |
| Native Linux export | n/a | unsupported, no template pin | n/a | No new target/pin. |
| Studio | checked-path shelf, confirmed launch | common backend | existing descriptor shelf | Native PC/Linux human Studio steps pending. |
| Audio import | sanitized ffmpeg child | parent PATH/common folders, scrubbed child | Homebrew/PATH | Linux ffmpeg 7.1.5 found; full native audio import not exercised. |
| Godot fetch | pinned archive, explicit consent | refused without separate Linux SHA-512 pin | pinned universal archive | No downloads, fetch/catalog/pin changes in this lane. |
| Runner | suspended Job assignment, tree cleanup, 64 processes/8 GB; no OS network/write confinement | namespaces, no network, hidden home, read-only system, project-only host writes plus private tmpfs; safe outer limits/inner NPROC | existing policy/process cleanup | Windows 6/6; Linux C7 **12/12**. Fork/memory exhaustion not exercised. |
| Children outside Runner | sanitized probes/preview/ffmpeg | same, capture remains inside Runner | existing behavior | Sanitization is not OS confinement; see child-environment audit. |
| Runtime/save | GL Compatibility, APPDATA custom folder | web output, no native target | existing custom folder | Headless/bot success is not human picture/audio/save acceptance. |

## Safety and preservation

- Relative/NTFS/traversal/reparse/hardlink protections remain. No symlink is accepted into normal project traversal; a narrow benign runtime link is unlinked first, never followed or used as an excuse to skip audit.
- Linux fails closed without bwrap unless the owner explicitly chooses the weaker unconfined mode. READY requires the confined real child. The unconfined fallback has no private tmpfs and earns no matching runtime-isolation claim.
- Inner NPROC is unchanged (namespace tasks + 512, inherited ceilings clamped). Runs 2/3 show 514 inside and host 63991 unchanged. PID teardown bounds lifetime, not fork count.
- C7 allows bwrap's generated PWD and the new explicit runtime constants. No ambient PULSE/XDG/provider/Hermes/sentinel value is inherited. Xvfb adds only its own private DISPLAY/software-GL flag.
- No change to runtime/godot resources, Mac sandbox/environment/argv outputs, pins/catalog yaml or exporter-parity verdict. The character parity verdict was already STALE; no oracle receipt is refreshed here.

## Local tests, not native acceptance

`tests.test_platforms3` uses exact received stderr, real decoded fixture PNGs, fatal/missing/corrupt/blank controls, create report/frame continuity, Dummy argv, runtime constants and real local stand-in process/timeout cleanup. It drives render-link → subsequent playtest/export dispatch and existing-game repair through the real project guards, with platform engines/actions simulated explicitly.

Required prior suites remain in the local selection: platforms2/linuxfix/Linux platform, reviewfix environment/hints, schema/public text, package/registration/catalog/hub, create report/camera classes, related runner/audit/portability suites. Completed counts, Mac 21-output byte identity, 15 replay results, extracted-ZIP checks and scratch-home validator details belong in source-only `docs/PLATFORMS3-RESULT.md`, not in a native platform claim.

## Not verified

Exact candidate on real Windows/Linux; Linux verdict/Dummy/runtime-link prevention/repair after actual Xvfb, fork-cap exhaustion and Hermes integration; Windows default 4.5 builder/clone rerun; human console flash, graphics/audio/save, Studio/browser play. **Tested by the owner: Not yet.**
