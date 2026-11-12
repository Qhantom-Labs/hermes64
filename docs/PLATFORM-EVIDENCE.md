# Platform evidence: what each platform claim rests on

**Answer. Linux: two real runs on Debian 13/bwrap 0.12.0: run 1 failed (fixed), run 2 authoring built, played and exported games with two remaining failures (fixed in this candidate, awaiting run 3). Windows 11: one real run: runner/exports pass, bundled demo failed on Blender 4.5 (fixed in this candidate), game not played by a human. Not verified.**

"Played" in the Linux receipt means bot playtests, not a human seeing/hearing a game. Windows exports came from the diagnostic Python-builder project, not the failed default-builder demo. Candidate repairs have local Mac execution/simulation evidence only; they are not native platform acceptance.

## Exact receipt custody

The three received `RECEIPT.md` bodies are copied byte-for-byte in the source repository. Windows `<user>` / `<pc>` placeholders are retained; `box` in the second Linux receipt is the supplied machine/account alias, not a personal name. Raw `outputs/` attachments were read for diagnosis but are **not shipped or committed**. These exact raw bodies are repository-only so their alias paths do not enter the install package.

| Run | Source commit | Raw receipt in the source repository |
|---|---|---|
| Debian 13 run 1 | `6af4ba26` | [LINUX-RECEIPT-2026-11-12-debian13-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run1.md) |
| Debian 13 run 2 | `acbcb657` | [LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md) |
| Windows 11 run 1 | `6af4ba26` | [WINDOWS-RECEIPT-2026-11-12-win11-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/WINDOWS-RECEIPT-2026-11-12-win11-run1.md) |

Source links identify the intended public-branch custody location, not a claim that this local candidate has been published.

## Findings and their limits

| Finding | Established evidence | Candidate change / remaining gate |
|---|---|---|
| Linux run 1: every official child failed namespace creation | Same bwrap argv worked without the outer NPROC limit. Old readiness bypassed the official limit shim. | LINUXFIX moved NPROC inside bwrap and exercised real `Runner.run`; run 2 confirms official children start. Exact original exhausted kernel counter remains unknown. |
| Linux run 2 B5 / C7a | Actual readiness child exited 0. Inside NPROC 514 (baseline 2 + 512); host soft/hard ceiling remained 63991. | No task-limit change here. Bounded fork exhaustion was skipped on the shared machine; enforcement under exhaustion remains unmeasured. |
| Linux run 2 C7: 11/12 | Only `extra=['PWD']`; `env -i bwrap ... env` independently prints PWD for bwrap's working directory. Other confinement/timeout checks passed. | Allow only bwrap-created PWD in the sheet; provider/Hermes/sentinel variables remain forbidden. C7 must reach 12/12 with `--no-fork` on run 3. |
| Linux run 2 D8/D9/D11 | Demo and new games built and passed bots. Web/Windows exports succeeded; macOS refused as designed. ffmpeg 7.1.5 now found. | Rerun B5, C7, D8–D11 on this exact candidate. No human web picture/audio or Hermes integration was exercised. |
| Linux run 2 D10 | All stages through playtest done; capture Godot exited 1: `X11 Display is not available`, then Wayland failed. Report never ran. | Private Xvfb + software Compatibility/OpenGL3 inside existing sandbox; actual tiny PNG probe before use. Missing/failed route gives both visual gates `not_run`, exact reason and CREATE-REPORT.md, not a pass. Native route awaits run 3. |
| Linux D11 first attempt | All tool results printed, then `NameError: name 'EOF' is not defined`; clean repeat succeeded. | Tester heredoc typo, not a plugin defect. No code repair for this. |
| Windows C5 | Fresh clone files changed to CRLF (1,137; retry 650); GitHub ZIP passed every manifest hash. | Existing root `* -text` rule was **omitted from the package/publish tree**. Ship `.gitattributes`; keep hashes strict, explain CRLF damage. Test fresh default clone and ZIP again. |
| Windows C6/D10 | READY claimed Blender OK without a version. Default auto picked 4.5.11 LTS; material `node_tree` was None at `_nt_clear`. | Enable nodes only when absent; existing 5.x tree untouched. Prefer 5.2.1 during automatic non-Mac discovery; show version and warning for all other versions/unknown. Real 4.5 run pending. |
| Windows D9/D12 | Six runner checks pass; detached/breakaway survivors absent. Diagnostic Python-builder project passed bots/web/Windows export and Windows headless boot. | No claim about unexercised memory-cap exhaustion, console flash, picture/sound/save or default Blender builder. Job Object still has no OS network/write confinement. |
| Windows chat / human steps | Configured model returned HTTP 404; C7/D11/D13 chat rebuild skipped. E14–E16 and console flash not observed. | Require a working configured chat model; mark visual/audio steps human-only. No inference/config repair is implied. |

## Platform status

- **macOS:** existing development-Mac acceptance remains; candidate sandbox/output and Blender-asset preservation checks are reported in repository-only `docs/PLATFORMS2-RESULT.md`.
- **Linux / Windows:** **Not verified.** A partial real receipt does not accept this candidate. Run the PLATFORMS-2 addenda in [Linux sheet](LINUX-TEST-SHEET.md) and [Windows sheet](WINDOWS-TEST-SHEET.md).
- **Tested by the owner: Not yet.** The executors were agents (Grok Bot/Prometheus), not owner acceptance. Per-command owner approval on the PC is not a human game playtest.

Earlier prose-only Windows reports and the older edited first-run Linux receipt are historical. The three exact bodies above and their raw outputs, not guesses about those older reports, establish these findings. No network, install, push, catalog/platform-pin change or real-machine rerun was performed by this candidate lane.
