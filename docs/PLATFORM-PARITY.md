# Platform parity: macOS, Windows and Linux

**Linux: experimental, receipts attached. Five real Debian 13/bwrap 0.12.0 runs, with Xvfb present. Run 5 (`55cdfc10`) passed authoring, bot playtest, web+Windows export and project-character export; B5 passed and C7 was 12/12 (`--no-fork`). Windows 11: experimental, receipts attached. Two real runs on Windows 11 Home, Blender 4.5.11, Hermes 0.18.2 and runner `job`. Run 2 (`72eb6565`) passed default-builder authoring, git-clone/ZIP/installed-folder check_install (C5 x3), C6 with Blender WARN and D12 web+Windows export; run 1 supplied the runner probes. Tested by the owner: Not yet. Executors were Grok Bot/Prometheus, not owner playtests.**

Exact receipts and progression: [PLATFORM-EVIDENCE.md](PLATFORM-EVIDENCE.md). Test sheets: [Linux](LINUX-TEST-SHEET.md), [Windows](WINDOWS-TEST-SHEET.md).

| Capability | Linux native evidence | Windows native evidence | Boundary |
|---|---|---|---|
| Install/check_install | Prior recorded checks; Hermes not installed by instruction | Run 2 default git clone, ZIP and installed folder C5 x3 passed | Exact recorded commits, no latest-head admission claim |
| Doctor/runner | Run 5 B5 READY, bwrap 0.12.0; C7 12/12 | Run 2 C6 passed with Blender WARN; run 1 D9 6/6 | Linux fork cap not exercised; Windows job has no OS network/write confinement |
| Authoring/assets | Run 5 D10 all stages done, generated character | Run 2 D10 default auto builder Blender 4.5.11 passed | Compatibility warning/retry preserved, no silent Python override |
| Render/style/N64 | Private Xvfb, 18 run + 18 copied nonblank decoded PNGs, style/N64 passed | Headless bots, no rendered screenshot acceptance | Bot/rendered results are not human aesthetic/audio acceptance |
| Pulse/runtime repair | Run 4 old exact link repaired; escaping link refused; runs 4/5 no new links | Existing behavior | No general symlink exemption |
| Bot playtest | Run 5 project and stock games PLAYABLE | Run 2 D12 PLAYABLE | Not real desktop play |
| Export web+Windows | Run 5 generated-character and stock games passed | Run 2 D12 passed, Windows headless boot passed | Browser/recipient game play pending |
| Project-character export | Run 5 disclosure in reports/closure and CHARACTER-PROVENANCE.json | No separate native project-character acceptance | user-generated, not part of the public manifest; local export only |
| Unknown import refusal | Run 5 release_private; no share written | Local fixture coverage only | Message now lists internal visibility and missing owner-rights metadata; admission unchanged |
| Private/cameo/rename/waiver-only refusal | NOT RUN natively | No new native claim | Maintainer fixtures, not private files; rig waiver is not rights |
| Export macOS | Explicit non-Mac refusal | Explicit non-Mac refusal | Mac signing still needs Mac; no native Linux export target |
| Long stories, style engine (needs design, previews), derived settings, creator64 characters | Not run natively (merged after run 5); previews take the private Xvfb route | Not run natively (merged after run 2) | Mac evidence only; builder scripts are macOS-only by design (recipe .json elsewhere); creator64 needs numpy + Pillow, no Blender |
| Human game/browser/Studio/audio/save | Not covered | E14–E16 and console flash not covered | Tested by the owner: Not yet |

## Preservation and safety

macOS retains development-Mac acceptance. Local acceptance measures the same 21-output Mac sandbox/environment/argv oracle and 15 legacy replays as PLATFORMS-4, with results in source-only `PLATFORMS5-RESULT.md`. PLATFORMS-5's sole production change is refusal-message wording: it does not change the denial predicate or Hub, and it changes no runtime resources, thresholds, pins/catalog yaml, public manifest or sandbox policy. The long-story, style-engine and creator lines merged afterwards (source-only `MERGEPREP-RESULT.md`).

Linux keeps private namespaces/no network/read-only system/home hidden/project-only host writes plus private tmpfs; without working bwrap, children fail closed unless an owner explicitly selects the weaker unconfined mode. That mode earns no sandboxed READY. Windows Job Object limits lifetime/resources but does not confine network/writes. Existing path/NTFS/reparse/hardlink protection remains.

Run-5 internal `release/export_presets.cfg` and `release/.godot/editor/project_metadata.cfg` contain absolute scratch paths; neither ships. Do not publish diagnostic outputs or machine-path build receipts. Dated receipt bodies stay source-only and byte-identical; templates ship as before.

## Remaining evidence boundaries

- Linux: fork-count cap not exercised (`--no-fork`); AppArmor-restricted userns hosts and hosts without Xvfb not covered natively. Missing-Xvfb clean failure is documented/tested locally, not a real no-Xvfb run. Real desktop play/audio/save and Linux Hermes integration remain open.
- Linux native private cast/cameo/renamed-private/waiver-only refusal controls were NOT RUN. Maintainer fixture tests are separate; never use real private files or invent an owner waiver.
- Windows: human E14 game, E15 Edge/Chrome web play, D9 console flash and E16 Studio if available remain open. Chat steps were blocked by a model prerequisite. D9 passed on run 1 only, not run 2 or the latest commit.
- Supplied receipts describe recorded commits, not execution of this exact local head. No new real-machine run occurred here. Agent execution/per-command approval is not owner play acceptance. **Tested by the owner: Not yet.**
