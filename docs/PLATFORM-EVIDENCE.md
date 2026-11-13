# Platform evidence: what each platform claim rests on

**Answer. Linux: experimental, receipts attached. Five real Debian 13/bwrap 0.12.0 runs, with Xvfb present. Run 5 (`55cdfc10`) passed authoring, bot playtest, web+Windows export and project-character export; B5 passed and C7 was 12/12 (`--no-fork`). Windows 11: experimental, receipts attached. Two real runs on Windows 11 Home, Blender 4.5.11, Hermes 0.18.2 and runner `job`. Run 2 (`72eb6565`) passed default-builder authoring, git-clone/ZIP/installed-folder check_install (C5 x3), C6 with Blender WARN and D12 web+Windows export; run 1 supplied the runner probes. Tested by the owner: Not yet. Executors were Grok Bot/Prometheus, not owner playtests.**

Bot playtests, automated rendered evidence, headless boot, recipient play and human play are separate claims. macOS retains development-Mac acceptance; local preservation results belong in source-only `PLATFORMS5-RESULT.md`.

## Exact receipt custody

Seven received `RECEIPT.md` bodies (five Linux, two Windows) remain byte-for-byte in source custody. The run-4 body was already present and matches the supplied body. Run-5 and Windows run-2 bodies were reviewed in full: no real person's name or real host name found. Supplied `<user>` / `<host>` redactions and machine/account aliases (`box`, `win11-rtx4070tis`) remain unchanged. No `outputs/` files are copied. `tools/package.py` excludes these dated receipt bodies consistently with earlier receipts; templates still ship.

The immutable receipts retain their original historical wording, including negative acceptance labels and check_install output; that text is not rewritten into a new platform claim. Source custody links below identify intended branch locations, **not publication of this local candidate**.

| Run | Recorded checkout | Source-only receipt |
|---|---|---|
| Debian 13 run 1 | `6af4ba26` | [LINUX-RECEIPT-2026-11-12-debian13-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run1.md) |
| Debian 13 run 2 | `acbcb657` | [LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run2-linuxfix.md) |
| Debian 13 run 3 | `72eb6565` | [LINUX-RECEIPT-2026-11-12-debian13-run3.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run3.md) |
| Debian 13 run 4 | `35a12561` | [LINUX-RECEIPT-2026-11-12-debian13-run4.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run4.md) |
| Debian 13 run 5 | `55cdfc10` | [LINUX-RECEIPT-2026-11-12-debian13-run5.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/LINUX-RECEIPT-2026-11-12-debian13-run5.md) |
| Windows 11 run 1 | `6af4ba26` | [WINDOWS-RECEIPT-2026-11-12-win11-run1.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/WINDOWS-RECEIPT-2026-11-12-win11-run1.md) |
| Windows 11 run 2 | `72eb6565` | [WINDOWS-RECEIPT-2026-11-12-win11-run2.md](https://github.com/Qhantom-Labs/hermes64/blob/post-submission/platforms/docs/receipts/WINDOWS-RECEIPT-2026-11-12-win11-run2.md) |

## Linux progression

1. Run 1 failed official children with outer NPROC before namespace setup.
2. Run 2 confirmed the limits repair but exposed PWD/capture reporting.
3. Run 3 passed C7 12/12 and rendered work, but benign device stderr misclassified capture and a Pulse runtime link poisoned later calls.
4. Run 4 (`35a12561`, package source `6a0ee0cf`) passed D10 capture/style/N64/report, private runtime/Pulse prevention and exact old-game repair; outside-root links still refused. D11 passed stock exports but failed generated-character exports with `release_private`.
5. Run 5 (`55cdfc10`) passed B5, C7 12/12, D10 with 18 decoded nonblank run and copied PNGs, style/N64 passes, bots and D11 web+Windows exports on that same generated-character game. Reports/closure and target-side `CHARACTER-PROVENANCE.json` say **user-generated, not part of the public manifest**. Stock control passed without a new disclosure. Unknown imported GLB refused with creator/provenance guidance; native private/cameo/rename/waiver-only controls were not run. macOS target correctly refused. No surviving runtime links.

Run 5 reports two internal build inputs holding absolute scratch paths: `release/export_presets.cfg` and `release/.godot/editor/project_metadata.cfg`. Neither ships in share/ or ZIPs. Do not confuse internal staging with distributed files. Recorded decoding is supplied executor evidence, not a fresh independent pixel audit. Missing AppArmor restriction sysctls do not prove AppArmor disabled.

## Windows progression

Run 1 supplied six runner probes and diagnostic Python-builder playtest/export/headless boot. Default Blender and clone line endings failed. Run 2 passed C5 x3 (default clone with autocrlf, ZIP, installed folder), C6 with Blender WARN, D10 default auto builder using Blender 4.5.11, and D12 bots/web+Windows exports. The material-node crash did not recur; one topology-rejected room shell used the designed next-candidate retry. Job Objects bound resources/lifetime, **not OS network or write confinement**. No rendered Windows screenshot or human play acceptance was supplied.

## Local message-only follow-up

An unknown community import has internal visibility and no owner-rights declaration. The refusal now names both metadata blockers and separately instructs the owner to correct community visibility only when legitimately releasable and record explicit rights/licence provenance in `assets/PROVENANCE.json`. Refused characters are unchanged; private/restricted/cameo and unknown provenance stay refused, rig waivers are quality-only and Hub policy is untouched.

## Remaining evidence boundaries

- Linux: fork-count cap not exercised (`--no-fork`); AppArmor-restricted userns hosts and hosts without Xvfb not covered natively. Missing-Xvfb clean failure is documented/tested locally, not a real no-Xvfb run. Real desktop play/audio/save and Linux Hermes integration remain open.
- Linux native private cast/cameo/renamed-private/waiver-only refusal controls were NOT RUN. Maintainer fixture tests are separate; never use real private files or invent an owner waiver.
- Windows: human E14 game, E15 Edge/Chrome web play, D9 console flash and E16 Studio if available remain open. Chat steps were blocked by a model prerequisite. D9 passed on run 1 only, not run 2 or the latest commit.
- Supplied receipts describe recorded commits, not execution of this exact local head. No new real-machine run occurred here. Agent execution/per-command approval is not owner play acceptance. **Tested by the owner: Not yet.**
