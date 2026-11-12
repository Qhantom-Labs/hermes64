# Platform evidence: what each platform claim rests on

**Answer.** There is **no receipt file for any Windows or Linux run** of Hermes64. A receipt here means a file with
the OS build, the Hermes version, the plugin commit (SHA) and the raw command output. The only Windows evidence is
two prose summaries of runs on the owner's PC on 2026-11-10, relayed by the owner and recorded in the maintainers'
decision log (outside this repository). Both describe **older packages** (the windows-lane package `cd15b620` and
games exported on a Mac), not this release. Linux has never been run. So:

| Platform | Status for this release | Basis |
|---|---|---|
| macOS | **Verified** on the development Mac | Test-suite and package receipts in the repository (`docs/*-RESULT.md`, repository only) |
| Windows 11 | **Built and simulated, not verified** | Simulation tests on the Mac; owner-relayed summaries for older packages, no receipt |
| Linux | **Authoring implemented behind bubblewrap, not verified** | Simulation tests on the Mac only ([LINUX.md](LINUX.md)) |

Rule from now on: a platform claim says "verified" only when a receipt following
[receipts/WINDOWS-RECEIPT-TEMPLATE.md](receipts/WINDOWS-RECEIPT-TEMPLATE.md) or
[receipts/LINUX-RECEIPT-TEMPLATE.md](receipts/LINUX-RECEIPT-TEMPLATE.md) exists under `docs/receipts/`. Every
"Tested by the owner" field stays "Not yet." until then.

## Claim by claim

"Relayed summary" = the 2026-11-10 entries in the maintainers' decision log: a few lines of prose per run, no raw
output, no transcript, no checksums of what ran. The package named for report 1 is `cd15b620` (windows-lane), per the
earlier version of [PLATFORM-PARITY.md](PLATFORM-PARITY.md).

| # | Claim (where it was made) | Evidence that exists | Receipt? | What this release may say |
|---|---|---|---|---|
| 1 | Plugin loads and runs in Hermes on Windows (PLATFORM-PARITY "yes") | Relayed summary 1: Windows 11 25H2, Hermes 0.18.2, package `cd15b620`; needed a local compatibility fix whose diff was never received | no receipt | Not verified for this release; older package reported working after an unreceived local fix |
| 2 | `check_install` passed 4962/4962 on Windows (PLATFORM-PARITY) | Relayed summary 1 (number only) | no receipt | Not verified for this release |
| 3 | Windows checklist READY (PLATFORM-PARITY) | Relayed summary 1 | no receipt | Not verified for this release |
| 4 | Godot and Python found on Windows (PLATFORM-PARITY) | Relayed summary 1 ("games were built") | no receipt | Not verified for this release |
| 5 | Blender failed on Windows, cause unknown (PLATFORM-PARITY) | Relayed summary 1: "Blender failed, python builder used". The tested package defaulted to `builder=blender` (`git show cd15b620:adventure_maker/builders.py`: `DEFAULT_BUILDER = 'blender'`), so a PC without Blender would fail that way. Not proven: no error text was sent | no receipt | Cause unknown; current default `builder=auto` falls back to the Python builder when Blender is not found |
| 6 | `/hermes64 new` made a game and 2 bot playtests passed on Windows (PLATFORM-PARITY) | Relayed summary 1 | no receipt | Not verified for this release |
| 7 | Windows export and its boot check passed; 3 example games booted at 59-60 FPS (PLATFORM-PARITY) | Relayed summary 1 | no receipt | Not verified for this release |
| 8 | Exported games on Windows: audio, dodge, push/pull, F5/F9 saves, web build in Chrome (PLATFORM-PARITY) | Relayed summary 2 (exported builds made on a Mac, `play-win`); it also found the shared-save defect later fixed by SAVEFIX, which was not re-run on Windows | no receipt | Not verified for this release; save fix not re-run on Windows |
| 9 | A Mac-exported Windows game runs on the PC | Owner statement, 2026-11-10 | no receipt | Exported-game evidence only, older build |
| 10 | `HERMES64_WINDOWS_RUNNER=job` was set on the PC (PLATFORM-PARITY "inferred") | None; inferred because children ran | no receipt | Unknown |
| 11 | Job Object behaviour on a real PC (tree kill, memory cap) | None | no receipt | Simulated only |
| 12 | WIN3 PC check script and sheet v3 | WIN3 result: script **unrun** on Windows | no receipt | Never run |
| 13 | Godot fetch on Windows (`setup --fetch`) | Loopback-fixture tests only; no official download anywhere | no receipt | Never run on Windows |
| 14 | Studio (Desktop tab) on Windows | None | no receipt | Never run |
| 15 | Anything on Linux | None | no receipt | Implemented here, simulation only |
| 16 | macOS authoring, tests, packaging | Repository receipts (`docs/FINALINT*-RESULT.md`, `docs/INTEGB-VERIFICATION.json`, repository only) | yes (Mac) | Verified on the development Mac |

## Contradictions found and how they were resolved

| Document | Said | Now says |
|---|---|---|
| `docs/PLATFORM-PARITY.md` | "Verified on real Windows: **yes**" in 9 rows, from the relayed summaries | "relayed, older package, no receipt"; the column is renamed and every row points here |
| `docs/WINDOWS-TEST-SHEET.md` (v2) | Opened with "v1 worked most of the way on your PC" and assumed the old `play-win` folder | Replaced by sheet v4, which assumes nothing passed and records receipts |
| `docs/WINDOWS.md` | "built, untested on Windows"; "Tested by the owner: Not yet." | Unchanged in substance (it matched the evidence) |
| `README.md`, `docs/AUTHORING-SCOPE.md`, `docs/DISCLOSURE.md`, `docs/ZEROSETUP-INVENTORY.md`, `skills/hermes64/SKILL.md` | Windows "not established/unverified"; "Linux authoring is unsupported" | Windows: "targeted, not verified" (same meaning); Linux: "implemented behind bubblewrap, not verified" |

No claim was upgraded. Where two documents disagreed, the one with less evidence behind it was taken.

## Where receipts go

`docs/receipts/<platform>/<YYYY-MM-DD>-<short machine alias>/` with `RECEIPT.md` filled from the template and the raw
outputs next to it (no usernames, no hostnames, no tokens). A maintainer updates this table, `PLATFORM-PARITY.md`
and the "Tested by the owner" lines only from such a folder.
