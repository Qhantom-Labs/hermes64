# Platform evidence: what each platform claim rests on

**Answer.** Linux: first real run (Debian 13, bwrap 0.12.0, 2026-11-12) FAILED: sandbox_unavailable on every child; fix in this release candidate is untested on a real Linux machine; not verified.

[The recorded receipt](receipts/LINUX-RECEIPT-2026-11-12-debian13.md) is Grok Bot's run of plugin `6af4ba26`
on a Debian 13 VM. It records a false READY checklist, then failed C7 and D8–D11 children with
`bwrap: Creating new namespace failed: Resource temporarily unavailable`. No game compiled or exported. Its diagnostic
isolated pre-bwrap NPROC as the trigger: the same argv worked without that limit. The precise exhausted kernel
counter was not measured. The candidate moves NPROC inside the sandbox and makes the real runner execute the
readiness child. **A second real Linux run is required**; Mac simulation is not that evidence.

The supplied receipt contains quoted lines and output-file references, not the referenced raw output attachments.
Those files are not reproduced or invented here. Missing Hermes (`hermes: command not found`) was the tester VM's
prerequisite, not a plugin regression; the Hermes integration step was skipped.

| Platform | Status for this release | Basis |
|---|---|---|
| macOS | **Verified** on the development Mac | Repository test/package receipts (`docs/*-RESULT.md`, repository only); candidate preservation checks are in LINUXFIX-RESULT |
| Windows 11 | **Built and simulated, not verified** | Mac simulation; owner-relayed summaries for older packages, no receipt |
| Linux | **First real run failed; candidate fix awaiting second run; not verified** | [Debian receipt](receipts/LINUX-RECEIPT-2026-11-12-debian13.md); candidate simulation tests on Mac only |

A receipt is necessary, not sufficient, for a verified claim: the relevant paths must actually pass for the exact
candidate. A failed run does not establish acceptance. "Tested by the owner" stays "Not yet." here: the Linux
executor was an agent, and no successful owner-run candidate receipt exists.

## Claim by claim

"Relayed summary" below means the owner's 2026-11-10 Windows notes in the maintainers' decision log, not raw
output. The older Windows package was `cd15b620`; its local compatibility fix was never received.

| Claim | Recorded evidence | What this release may say |
|---|---|---|
| Windows plugin load, `check_install` 4962/4962, checklist READY, discovery, `/hermes64 new` and two bot playtests | Relayed summary 1, Windows 11 25H2, Hermes 0.18.2, older package `cd15b620` after an unreceived local fix | Not verified for this release |
| Windows Blender failure | Relayed summary 1, no error text; older package defaulted to Blender | Cause unknown; current auto builder falls back to Python when Blender is absent |
| Windows export/boot and older examples at 59–60 FPS | Relayed summary 1 | Not verified for this release |
| Mac-exported Windows game audio, dodge, push/pull, F5/F9, Chrome web play | Relayed summary 2; found a save defect later fixed, not retested on PC | Older exported-game evidence only; save fix not verified on PC |
| Windows Job Object opt-in, tree kill, process/memory caps, suspended assignment | No native receipt; inferred opt-in is not evidence | Simulated only |
| WIN3 script, Windows fetch and Studio | No native receipt | Not run on Windows |
| Linux prerequisites | Debian receipt A1/A3/B4: bwrap, Python/numpy/Pillow, official Godot archives/templates; A2 lacked Hermes | Recorded prerequisites only; no successful authoring |
| Linux checklist READY | Receipt B5/F14, but every official child then failed | **False positive in the old probe**, not acceptance; fixed readiness path awaits retest |
| Linux confinement, timeout, fork cap | Receipt C7: sandbox_unavailable; fork exhaustion skipped on shared VM | Not verified; second C7 required |
| Linux demo/new/create flow/playtest/web/windows export | Receipt D8–D11: sandbox_unavailable or no current build | Failed; candidate awaits D8/D9/D10 and downstream retest |
| Linux macOS-export refusal | Receipt D11 returned the specified export_target refusal | Refusal recorded only; no authoring or export acceptance |
| Linux web picture/sound, Hermes integration | D12/E13 skipped: no browser/build, no Hermes | Not run |
| Linux unconfined fallback | F14 exercised opt-in/disclosure; timeout/setsid check failed | Not a sandbox guarantee or verified fallback acceptance |
| macOS authoring/tests/package | Existing repository receipts | Verified on development Mac; not cross-platform evidence |

## Corrections and receipt custody

- Historical PLATFORMS-RESULT describes the state before this first Linux receipt; its "never run" lines are historical,
  not current claims. README, LINUX.md and this table now record the failed first run rather than "never run".
- PLATFORM-PARITY separates implementation from native evidence and links here; no Windows claim is upgraded.
- Linux task limits still exist. Namespace teardown is **not** claimed to be a process-count cap. The bounded fork
  probe must observe positive fork headroom and EAGAIN below its safety bound on an approved dedicated Linux VM.
- Use the second-run addendum in [LINUX-TEST-SHEET.md](LINUX-TEST-SHEET.md). Keep both receipts, with exact SHAs.
- New receipts normally go in `docs/receipts/<platform>/<YYYY-MM-DD>-<machine alias>/`, with sanitized raw outputs.
  The supplied first-run receipt is retained at the direct path linked above. Do not add names, hostnames, tokens,
  environment/config contents, or success claims for skipped steps.
