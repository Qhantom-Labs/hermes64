# Package contents: what a user install needs

Hermes installs a plugin by cloning its repository; there is no include/exclude manifest. This development repository also carries lane evidence, receipts and tests; its size is not the size of an installed package. These rules select the user-facing files for a release branch, catalog tree or archive. **Nothing is deleted from the repository**: evidence, provenance and private review material stay tracked here and are only left out of the package.

The rules live in one place, `tools/package.py`:

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.package             # totals
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.package --list      # every shipped file
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.package --scan      # privacy scan of what would ship (exit 1 on a blocking hit)
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.package --out /abs/new/dir   # scan, then copy into a NEW folder
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B -m tools.package --out /abs/new/dir --zip /abs/new.zip   # ... plus a deterministic zip
```

It reads `git ls-files --cached --others --exclude-standard` (what a commit would carry), keeps a path when it matches an include rule and no exclude rule, and never writes outside `--out`. `--out` runs the privacy scan first and writes nothing if it blocks; it also writes `PACKAGE-MANIFEST.json` (every shipped file's size and sha256, the source commit and whether the tree was clean), which `tools/check_install.py` checks an installed copy against. The MERGE4 release candidate `../transfer/rc1/` was made this way (`docs/MERGE4-LOG.md` section 9).

## Include

| Rule | Why users need it |
|---|---|
| `plugin.yaml`, `__init__.py`, `LICENSE`, `README.md`, `PLAY.md`, `RESULT.md`, `licenses/*` | Manifest, entrypoint, licences, quick start, the acceptance limits README links to |
| `.gitattributes` | Preserve every manifest-hashed byte on clone (`* -text`), even with Windows core.autocrlf=true; the package/publish tree must include this file. |
| `bindings.json`, `characters/*` | Public bundled cast and its staging code (runtime character bindings); since MERGE3 also `characters/combat/` (combat manifest, 4 enemy and 4 prop GLBs) |
| `adventure_maker/*`, `adventure_modules/*`, `story/*`, `refpack/*` | Tool code, story compiler/checker, module contracts, reference-pack drafting |
| `runtime/*` | Godot runtime layer, including `runtime/godot/tests/playthrough.gd` used by `hermes64_replay` |
| `kits/*`, `packs/*`, `profiles/*` | Kit library and GLBs, theme packs, style profiles |
| `audio/*` | Audio catalog, WAVs, recipes and synthesis data used by `hermes64_audio` and packs |
| `contracts/*` | JSON schemas read at runtime (project, style, gameplay) |
| `examples/*` | Bundled examples used by `hermes64_demo` and module docs |
| `premises/*` | Neutral data-only story files and prompt text; user stories can also live in the games folder |
| `skills/*` | The 11 bundled skills, registered in `__init__.py`; discovery behavior depends on the host |
| `docs/*` | User and integration docs (story spec, packs, playtest, export, badge, token diet; since rc9 the platform guides `LINUX.md`, `WINDOWS.md`, `PLATFORM-EVIDENCE.md`, `LINUX-RUNNER-DESIGN.md`, both test sheets and the receipt templates in `docs/receipts/`) |
| `catalog/*` | The generated asset catalog (`catalog.json`, thumbnails) and `names.json`, the one file the hub reads display names from |
| `hub/*` | The bundled Hub registry: `index.json`, preview PNGs and the offline browse page `hub/site/` (`hermes64_hub` reads the index and rebuilds each seed archive from the shipped files) |
| `cameo/*` | **Opt-in, not in the default package** (`OPTIONAL_CAMEO`; `python3 -B -m tools.package --out DIR --with-cameo` adds it). MERGE4 recorded an owner decision that it ships; for this release that decision is open, so the default leaves it out (FINALINT). The optional cameo pack: the model `cameo_visor_01.glb`, its notice `LICENSE-CAMEO.md`, manifest and README; delete the folder to remove it |
| `rigs/*` | The rig kit (merged at MERGE4): `rigs/<id>/rig.json`, `clips.json`, `clips.glb` and the mannequins. The in-process validator (`adventure_maker/rigkit`) and the hub's `compat.rig` check read them; without them every hub install failed from a package (found by `tests/test_merge4_cameo.py`) |
| `desktop/plugin.js`, `dashboard/manifest.json`, `dashboard/plugin_api.py` | Hermes64 Studio (merged at MERGE4): the Desktop half (one generated ES module) and the backend routes it calls; without them a package install has no Studio tab |
| `tools/style_bible.py` | Recipe screening uses the existing derived bible consumer; generator CLI and skill ship under `adventure_maker/*` and `skills/*` |
| `tools/room_clearance.py`, `tools/medievalkit_rooms.py`, `tools/westernkit_rooms.py`, `tools/cyberkit_rooms.py`, `tools/dungeonkit_rooms.py`, `tools/place_maker.py`, `tools/place_measure.py`, `tools/style_ref_measure.py`, `tools/mood_pack.py`, `place_approvals/README.md` | PLACEMAKER: place archetypes become room plans (`adventure_maker/place.py`) through the kit room compilers and the clearance check; the `place_maker` CLI adds the render loop, measurement and the (empty) approval store |
| `tools/medievalkit_rooms.py`, `tools/westernkit_rooms.py`, `tools/mood_pack.py` | ORCH create flow (`adventure_maker/create_flow.py`): the kit room compilers that compile its room skeletons, and the mood pack derive/install it calls; stdlib plus the shipped `kits/core` modules |
| `studio/plugin/glue.js`, `studio/prototype/js/*`, `studio/prototype/studio.css`, `studio/tools/sync_shared.py` | The readable sources `desktop/plugin.js` is generated from and the stdlib generator: `python3 -B studio/tools/sync_shared.py` rebuilds it (CAT-FIX F10). Harness, mock backend, covers and screenshots stay in the repository |
| `tools/__init__.py`, `tools/pngtool.py`, `tools/import_characters.py` | The only `tools/` modules imported at runtime (playtest contact sheet, character staging) |
| `tools/roomlook.py` | MERGE4: imported by `characters/integration.capture_games` (reached through the shipped `tools/import_characters.py`); without it `hermes plugins validate` on the package read `tools.roomlook` as a private Hermes core import (the `git archive` of the repository was clean because the file is there) |
| `tools/check_install.py` | MERGE4: checks an installed copy against the `PACKAGE-MANIFEST.json` that `--out` writes (every file's size and sha256, the source commit) and prints PASS or FAIL; stdlib, read-only; run on macOS here, written for Windows and Linux too (both test sheets run it) |
| `tools/hermes64_setup.py` | One-step setup checklist; only a user-typed `--fetch` plus confirmation downloads the official Godot editor (and, with `--templates`, the official export templates) into a per-user cache. Plain checklist downloads nothing; see `docs/SETUP-FETCH.md` |
| `tools/fetch-manifest.json` | Pinned download plan (official godot-builds 4.6.2-stable URLs and their published SHA-512), printed by `--fetch-plan`. CAT-FIX F4 removed the self-hosted stub bundle and its builder |
| `tools/bin/MANIFEST.json` | ZEROSETUP: pinned (empty) manifest for the optional `tools/bin/<platform>/ffmpeg` lookup; no binary ships |

## Exclude

| Rule | Why it stays repository-only |
|---|---|
| `docs/receipts/*-2026-11-12-*.md` | Raw platform receipt bodies remain byte-for-byte in the source repository, including alias-only paths; no raw outputs ship. Public platform guides summarize them and link to source custody. |
| `evidence/*` | Lane and verification evidence (803 tracked files, ~47 MB) |
| `premises/teknium-vs-tyrants/*` | Showcase story stays outside the plugin, in the user's games-folder premises directory |
| `docs/sources/*` | Original lane receipts copied at assembly (hashed in `PROVENANCE.json`) |
| `docs/controls-evidence/*`, `docs/n64fidelity/*` | Audit images and evidence |
| `docs/cover/*` | The cover lane's critiques (rounds 1-7) and demo-round finals (27 files, 5.1 MB). `hermes64_cover` renders each project's own covers at run time; nothing reads these files (added at MERGE3) |
| `docs/*-LOG.md`, `docs/PRIVACY-SCAN.md`, `docs/ASSEMBLY-EVIDENCE.json` | Merge logs and audit reports |
| `audio/tests/*`, `audio/evidence/*`, `audio/expansion/verification/*`, `audio/RESULT.md`, `audio/expansion/RESULT.md` | Audio tests, evidence and lane results |
| `contracts/*/evidence/*`, `contracts/project/baseline.py`, `contracts/project/baseline-receipt.json`, `contracts/project/seal_starter.py`, `contracts/project/verify_source.py`, `contracts/style/derive_examples.py`, `contracts/style/example-provenance.json` | Contract evidence and developer scripts |
| `adventure_modules/acceptance.py`, `adventure_modules/verify.py`, `adventure_modules/examples.py`, `adventure_modules/export_contracts.py` | Developer acceptance/export scripts (not imported by the tools) |
| `hub/archives/*`, `hub/drafts/*` | Materialised seed archives (`python3 -B -m tools.hub archives`, git-ignored; installs rebuild them from shipped files and check the sha256) and a public registry's pull-request drop folder |
| `*/__pycache__/*`, `*.pyc`, `.DS_Store`, `*/.DS_Store` | Build and OS litter |
| `docs/*-RESULT.md`, `docs/PUBLIC-SURFACE.md` | Lane result receipts and the public-surface inspection receipt (MERGE4: they carry build-machine paths; the rules below already said `*-RESULT.md` stays out, but `docs/*` shipped them) |
| `docs/studio/CRITIQUE-*`, `docs/studio/*.jpg`, `docs/studio/desktop/*`, `docs/studio/final/*`, `docs/studio/pattern/*` | The Studio lanes' critiques and screenshots (about 18 MB; `docs/studio/DESKTOP-INSTALL.md` still ships) |
| `docs/*kit/*`, `docs/merge6/*`, `docs/*-HUB-ENTRIES.md`, `docs/MERGE*-CYBER-NOTES.md` | MERGE6: genre QA/reference/capture/verification directories and merge/hub handoffs remain repository-only, including raw logs with build-machine paths. Public top-level kit guides and generated catalog/hub previews still ship. Runtime single-kit archives use manifests, GLBs and textures, never source-only build sidecars. |
| `docs/*-MODEL.md`, `docs/*-VERIFICATION.json` | RC3: runtime-lane receipts (cam, feel2, livefix, move model headers and verification ledgers, plus the RC3 integrator's model header) remain repository-only; they carry build-machine paths. The user-facing docs of those lanes still ship. |
| `characters/internal/*` | Internal and restricted characters (git-ignored as well; MERGE4 adds the package rule so a force-added file still cannot ship) |
| `docs/measurements/*`, `docs/MESHY*-INGEST.md`, `docs/INTEG6-TIMEOUT.md`, `docs/tiers/*` | FINALINT: measurement receipts of the private character conversions (they carry private model hashes), the conversion notes and an integration timeout note (private folder names), and raw agent-run transcripts (build-machine user name) stay in the repository. Found by the release verification kit's privacy gate; no runtime code reads them |
| `docs/demobuild/*`, `docs/gaps2/*`, `docs/tfix/*` | FINALINT4: the demo-build, GAPS2 and TFIX proof/measurement harnesses (and TFIX's `measured.json` receipt) are developer-only; shipped, TFIX's scripts failed the WIN3 packaged text-IO gate (`tests/test_win3.py`: implicit-encoding `read_text()`). The first two folders import repository tools (`tools.controls_replay`) that never ship, which the catalog validator (`hermes plugins validate`, rule 9) listed as private Hermes core imports. `tools/mood_demo.py` (the amood demo driver) left the include list too: `place_maker` now takes `add_extras_to_base` from `tools/mood_pack.py` |
| `kits/library/*.glb.json` | Source-only kit build reports, which can contain absolute build paths. Runtime kit packing uses the core/side manifests and hash-pinned GLBs/textures; authoring catalog generation may inspect the real sidecar validation, while a project's own cache reports are separate. |
| Not included (WIN2): `tools/windows_gate.py` | The Windows portability gate is a source-text scan of the runtime code: its result is the same on any OS, so it runs in the repository (and CI) before a package is cut, together with `tests/test_windows_gate.py`, which cannot ship anyway (`tests/` is repository-only). The first Windows test sheet told users to run `py -B -m tools.windows_gate` on the unpacked package, where it does not exist (the owner's PC run: `No module named tools.windows_gate`); the sheet v2 drops that step. Rule: a `tools/` module ships only when the runtime imports it or the user runs it on the installed copy (`check_install.py`); `tests/test_package.py` checks every `tools` command in the Windows test sheet ships |
| Not included at all: `tests/`, `tests_story/`, `tests_refpack/`, `tests_cover/`, `goldens/`, `games/`, `projects/`, other `tools/*` (including the catalog/hub generators `tools/catalog.py`, `tools/hub.py`, `tools/hub_site.py`, `tools/thumbs.py`), `PROVENANCE.json`, `*-CHECKPOINT.md`, `*-BLOCKED.md`, `*-RESULT.md` | Tests, golden images, showcase/sample projects, developer tools, provenance and lane process records |

## DOCS2 rc8 rules (applied to `tools/package.py` at FINALINT5)

DOCS2 proposed these rules and changed documentation only; FINALINT5 applied them to the filter for rc8. The root guide, changelog, security note and `.gitignore` now ship; submission drafts, DOCS2 receipts, lane handoffs and the merge ledger do not.

| Rule | Purpose |
|---|---|
| INCLUDE `QUICKSTART.md`, `CHANGELOG.md`, `SECURITY.md`, `.gitignore` | Ship the root onboarding/release/security/source-tree guidance. `README.md` already ships. |
| EXCLUDE `docs/submission/*`, `docs/docs2/*`, `docs/PUBLIC-READINESS.md` | Submission drafts and local audit/verification records are developer-only. |
| EXCLUDE `docs/*-HUNKS.md`, `docs/MERGE-HANDOFF.md`, `docs/MERGE-LEDGER.md` | Keep developer handoff/private conversion provenance out of the public package. This also excludes `docs/DOCS2-HUNKS.md`. |
| `tools/scifikit_rooms.py` | STYLEGEN-1: the SCIFIKIT room compiler that compiles the `scifi` create patterns (`adventure_maker/create_patterns.json`) a derived setting pack (`adventure_maker/create_setting.py`) builds on; stdlib plus the shipped socket manifest |
| `tools/ancientkit_rooms.py` | STYLEGEN-2: the ANCIENTKIT room compiler that compiles the `ancient` create patterns (court, approach, shrine from the calibrated ANCIENTKIT demo) the jungle, ancient and desert setting rows (`adventure_maker/create_setting.json`) build on; stdlib plus the shipped socket manifest |
| EXCLUDE `docs/STYLEGEN*`, `docs/stylegen*/*` | STYLEGEN lanes (post-submission): plans, evidence, receipts and stdlib measurement scripts are developer-only. |
| EXCLUDE `docs/STYLEENGINE*` | STYLEENGINE lane (post-submission): the plan and result docs are developer-only. |
| Existing EXCLUDE `docs/*-RESULT.md` | Already keeps `docs/DOCS2-RESULT.md` out; do not ship it as user documentation. |

The rc8 archive's contents, links and manifest are checked in `docs/FINALINT5-RESULT.md` (repository only).

## rc9 platform files (PLATFORMS)

No rule changed. Shipped through the existing rules: `adventure_maker/linux_sandbox.py` (the Linux bubblewrap runner)
and the docs above. Repository-only through the existing rules: `docs/PLATFORMS-RESULT.md` (`docs/*-RESULT.md`),
`tests/test_linux_platform.py` and `tests/test_windows_lane_fixes.py` (`tests/*`), and `tools/windows_gate.py`.

## Privacy scan (MERGE4)

`tools.package.scan` reads every byte that would ship (nested zips to depth 4):

- **Blocking:** a shipped path under `evidence/`, `docs/sources/`, `characters/internal/`, `tests/`, `goldens/`, `games/` or `projects/`; a real home-directory path (`/Users/<name>/`, `/home/<name>/`, `C:\Users\`); the name of one of the private reference folders kept outside the repository (the `PRIVATE_REFS` pattern in `tools/package.py`; not spelled out here, since this doc ships). Allowed as not anyone's home: `you`, `me`, `user`, `username`, `name`, `example`, `runner` (the official CI user inside Godot's templates) and `web_user` (Emscripten's virtual home).
- **Report-only:** the cameo's id and name, the publisher name, and the owner and project names the release audit tracks (the `REPORT_TERMS` pattern in `tools/package.py`; not spelled out here, since this doc ships). The optional cameo is absent by default; its identifiers can remain in code/docs and are counted, not blocked.

Blocking rows name the file, kind and line, never the matched text.

MERGE4 (`--scan` on the final tree, see `docs/MERGE4-RESULT.md`): 0 blocking. Before the MERGE4 rules the same scan would have blocked 127 files (the kit sidecars and four receipts with absolute paths).

## Historical development measurements (not the current package)

| | Files | Bytes |
|---|---:|---:|
| Repository (tracked + new, not ignored) | 2,415 | 82,162,230 |
| Package | 1,049 | 26,745,086 |

MERGE3 (polish + cover merged, before the combat-art import; `python3 -B -m tools.package`): repository 2,489 files / 88,360,528 bytes; package 1,075 files / 27,047,626 bytes. Without the new `docs/cover/*` rule the package would be 1,102 files / 32,349,713 bytes. The cover code, runtime scene, contracts and skill (`adventure_maker/cover_*.py`, `project_cover.py`, `runtime/godot/cover/`, `contracts/cover/`, `skills/hermes64-cover/`, `docs/COVER.md`) ship through the existing rules; `tests_cover/` and `tools/cover_demo.py` do not.

MERGE3 after the combat-art import (same command, before the acceptance tooling): repository 2,505 files / 89,735,488 bytes; package 1,087 files / 28,396,962 bytes (+12 files / +1,349,336 bytes: `characters/combat/` and the 16 combatant GLBs that gained six clips). No package rule changed for it.

Checks run on a package materialized with `--out`:

- `tests/plugin_isolation_probe.py <package> <projects>` in isolated Python (`-I`): 27 tools register; scaffold, `hermes64_module_check` (conditional), `hermes64_audio` list and the full `hermes64_demo` Last Light run (Blender build, playtest, web export) pass. Output: `{"tools": 24, "module_status": "conditional", "top_level_story_imported": false}`.
- `/hermes64 new` from the package: PLAYABLE (headless) badge; `hermes64_doctor`, `hermes64_packs`, `hermes64_kits`, `hermes64_audio` search, `hermes64_replay` (passed) and `hermes64_modules` all work against it.
- Hermes `plugin_guard` scan of the package (`tools.plugin_guard.scan_plugin`): verdict `safe`, 0 high or critical, 13 medium: 6 hex byte literals (MIDI writer, export privacy regex, JPEG magic bytes), 3 subprocess calls (the sandboxed engine runner, the static preview and the reference-pack Blender call), two music WAVs (1,058,444 bytes each) over the 1 MiB single-file note, and 1,049 files / ~26.7 MB over the soft structural limits (400 files / 10 MB) because the audio WAVs (226 files, 14.4 MB), kit GLBs (174 files, 3.4 MB) and cast GLBs (28 files, 2.8 MB) are runtime data.

## Not done here

No release branch, archive, catalog pin or install was produced; that remains an owner decision. `git archive` users could mirror these rules with `.gitattributes` `export-ignore`, but `tools/package.py` is the single source of truth to avoid drift.
