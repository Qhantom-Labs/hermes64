# Platform evidence: what each platform claim rests on

**Answer. Linux: three real Debian 13/bwrap 0.12.0 runs. Run 3 reached C7 12/12 and actual private-Xvfb PNG capture, but D10 reported the wrong verdict and D11 failed after rendered runs left a PulseAudio runtime link. Candidate repairs await a fourth Linux run. Windows 11: one real run; runner/diagnostic exports pass, default Blender 4.5 demo failed, native candidate rerun and human play pending. Linux and Windows: Not verified. Tested by the owner: Not yet.**

Bot playtests, rendered evidence and human play are different claims. Windows exports came from the diagnostic Python-builder project, not the failed default-builder demo. This lane's local simulations do not accept a native platform.

## Exact receipt custody

Four received `RECEIPT.md` bodies are copied byte-for-byte in the source repository. Supplied `<user>` / `<pc>` / `<host>` redactions and `box` account/machine alias are retained, including `/home/box` paths. No real personal/host name was found in run 3. Raw `outputs/` were read for diagnosis but are **not shipped or committed**. These exact bodies are source-only.

| Run | Source commit | Source-only receipt |
|---|---|---|
| Debian 13 run 1 | `6af4ba26` | [LINUX-RECEIPT-2026-11-12-debian13-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run1.md) |
| Debian 13 run 2 | `acbcb657` | [LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md) |
| Debian 13 run 3 | `72eb656589692194b9e62db2329000bd410b9b90` | [LINUX-RECEIPT-2026-11-12-debian13-run3.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run3.md) |
| Windows 11 run 1 | `6af4ba26` | [WINDOWS-RECEIPT-2026-11-12-win11-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/WINDOWS-RECEIPT-2026-11-12-win11-run1.md) |

Links identify the intended branch custody location, not a claim that this local candidate was published.

## Findings and limits

| Finding | Established evidence | Candidate change / remaining gate |
|---|---|---|
| Linux run 1: official children failed | Same bwrap argv worked without outer NPROC. | NPROC moved inside bwrap; real Runner readiness retained. Runs 2/3 start official children; exact original exhausted kernel counter is unknown. |
| Linux run 2 C7: 11/12 | Only bwrap-generated `PWD` was extra. | Sheet changed; run 3 now **12/12**, including confinement and timeout cleanup. |
| Linux run 3 B5/C7 | Real Runner readiness and tiny private-Xvfb PNG pass; inner NPROC 514, host ceiling 63991 unchanged; host-after lists 154 processes. | No task-budget change. Fork exhaustion skipped with `--no-fork`; it remains unmeasured. Probe diff adds only PWD, not a relaxation of confinement. |
| Linux run 3 D8/D9 | Demo bots/web export pass. D9 real Xvfb audit returns WARN 88/100; both rooms are WARN, not aesthetic approval. | Preserve dark-value warnings, 744-triangle inhabitant versus 700 budget, and room_b accent overuse 54% versus 15%. No style thresholds changed. |
| Linux run 3 D10 | Exit 0, `CAPTURE status=passed rooms=2 missing=0`, 18 PNG names, own style gate passes both rooms; CREATE reports exist but say failed and no frames. | **Established root cause:** Service.open rejected every stderr `ERROR:`, including non-root X socket notice and ALSA ERR_CANT_OPEN followed by exact audio-driver context. Capture now requires protocol/room/file coverage, CRC-valid decoded PNGs and nonblank primary frames. Only narrowly matched diagnostics are retained as `benign_stderr`; unknown errors and real failures stay failures. The supplied diagnostics do not contain the PNG bytes or an N64-gate verdict: no retrospective pixel/N64 pass is invented. |
| Linux run 3 rendered D9/D10 → D11 | Exact PulseAudio client runtime links in `.maker/local/config/pulse/<host>-runtime` point at the same game's `.maker/local/tmp/pulse-*`; every later call on fox1 is refused. | **Established:** runtime link poisons general audit; **strongly supported mechanism:** audio client fallback with project-local config/temp and no XDG runtime. Automated Linux Godot uses Dummy; private tmpfs runtime/PULSE paths; post-run/pre-audit cleanup removes only that exact internal scratch-link shape and records a note. Native prevention/repair still needs run 4. |
| D11 diagnostic on thaw1 | Never-rendered game has no Pulse link; bots/web/Windows export pass, macOS correctly refuses. | The supplied thaw1 is an **unpoisoned control**, not an affected game. Existing-game repair is tested with a locally poisoned fixture. No exporter change beyond no-audio argv. |
| Windows C5/C6/D10 | Clone CRLF damage while ZIP hashes pass; 4.5.11 material has no node tree; old doctor omitted version. | Prior candidate ships byte-preserving attributes, conditional node enabling and version warnings; native default clone/ZIP/builder rerun still pending. Mac 5.2.1 geometry/material-byte evidence remains prior scope only. |
| Windows D9/D12 | Six runner checks; diagnostic project bots/export/headless boot pass. | Job Object has no OS network/write confinement; memory exhaustion and human picture/audio/save/console flash are not accepted. |
| Windows chat / Linux integration | Windows model HTTP 404; Linux Hermes not installed by instruction. | Prerequisite gaps, not permission for configuration or installation. Human Studio/browser/gameplay remain separate. |

## Current platform status

- **macOS:** development-Mac acceptance retained. This lane measures the same 21-output sandbox/environment/argv oracle and 15 accepted legacy replays; completed results belong in source-only `docs/PLATFORMS3-RESULT.md`.
- **Linux / Windows: Not verified.** Linux needs the **fourth Linux run** addendum in [LINUX-TEST-SHEET.md](LINUX-TEST-SHEET.md); Windows keeps its pending [native rerun](WINDOWS-TEST-SHEET.md).
- **Tested by the owner: Not yet.** Agent execution and per-command owner approval are not a human game playtest.

Earlier receipts remain failed/partial historical runs. No network, install, push, catalog/platform-pin change, service restart or real-machine rerun was performed by PLATFORMS-3.
