# Local export and sharing

`hermes64_export(project, targets)` accepts `web`, `macos`, `windows` (one or more unique targets). It builds an exact current **proved** game and returns paths to the report, share folder and ZIP. It never uploads, publishes, downloads or installs templates. Building is not recipient acceptance.

Build hosts use their existing platform runner: macOS Seatbelt, Linux bubblewrap, or Windows Job Object. macOS retains development-Mac acceptance; supplied Linux/Windows runs are partial evidence, **not verified** platform status. The `macos` target requires a Mac for local ad-hoc signing. Targets:

| Target | Contents / limits |
|---|---|
| web | HTML + JS + WASM + PCK, official no-threads release template, WebGL2. Serve through localhost HTTP; not file://. No PWA/service worker, CDN or single-file-HTML claim. |
| macos | Universal app + ZIP, locally ad-hoc signed, not Developer ID signed/notarized. A bounded native headless boot is required before success. Recipient Gatekeeper and Intel hardware remain unverified. |
| windows | x86_64 executable + PCK + ZIP. Unsigned. **UNVERIFIED execution on this Mac**, always labeled in README/report. |

**STORY 1.3 (puzzle) games (MERGE5).** A 1.3 build lives behind the module data pointer (`hermes64_module_check`
with `adopt=true`; the 1.0-1.2 compile path does not accept 1.3 sources). When that pointer holds a 1.3 game,
`hermes64_export` and `hermes64_build_assets` use it (source/build re-checked, else `export_source`); otherwise the
ordinary current build, unchanged. The release carries the lowered STORY 1.2 build the runtime plays as `game.json`,
`puzzle.json` (the compiled puzzles bound to both build hashes, the proved safe-checkpoint set and the pack's look
data; the runtime refuses a sidecar bound to another build) and the eleven puzzle cue rows in `audio.json` (shipped
catalog WAVs, hash-checked media): the data the puzzle bot plays (`adventure_maker/puzzle_runtime.py`, shared with
`tools/puzzle_play.py`). Only a **proved** 1.3 build exports (no conditional preview path for puzzles); the report
adds `story_version: 1.3.0` and `build_pointer`, `closure.json` adds `puzzle_game_hash`. `hermes64_open` and
`hermes64_playtest` still use the current 1.0-1.2 build; the puzzle bot is `python3 -B -m tools.puzzle_play`.
Test: `tests/test_merge5_export_puzzle.py` (staging, refusal, and a real web + macOS export of puzzle_hall).

Every target has README, Hermes64 MIT license, official Godot MIT `LICENSE.txt` and full Godot `COPYRIGHT.txt` third-party notice inventory. The web page links to the notices. The aggregate `share/` and `share.zip` include every selected target and sorted `FILES.json` manifests (relative name, byte count, SHA256). ZIP entry ordering, timestamps and permission modes are fixed. This is **not** a claim that Godot exports are byte-identical across fresh engine imports/signatures/machines. The report includes unpacked payload and compressed sizes. `FILES.json` omits itself; aggregate size is a payload inventory, not filesystem allocation size.

## Template admission

The separately owner-approved official archive and published SHA512-SUMS file must already exist. The explicit maintainer helper checks both the hard-pinned archive SHA512 and exact `templates/version.txt` **before any install**, then writes only:

- `version.txt`
- `macos.zip`
- `web_nothreads_release.zip`
- `windows_release_x86_64.exe`
- `windows_release_x86_64_console.exe`

Destination: `~/Library/Application Support/Godot/export_templates/4.6.2.stable/`. No debug, threaded-web, Android, iOS or Linux templates are extracted. Export rechecks each selected template's SHA256 and version. The helper is **not a public tool** and must not run without separate installation authority.

```sh
/usr/bin/python3 -B tools/ship_templates.py --archive /absolute/path/Godot_v4.6.2-stable_export_templates.tpz --sums /absolute/path/SHA512-SUMS.txt --receipt evidence/ship/templates-install.json
```

Godot on macOS ignores TMPDIR for some editor writes. The exporter copies the **intact signed installed Godot.app** into the project and enables official self-contained editor mode with sibling `_sc_`; selected verified templates are copied into that local editor cache. Bare Mach-O copies fail macOS signature checks. The existing child sandbox remains project-write-only and no-network. Expect several hundred MB of local editor/runtime staging per project plus export artifacts.

## Privacy and portability

Release staging is an allowlist, not a recursive copy of the source repository:

1. Recheck story proof; reject source/binding policy flags (`internal_only`, `restricted`, `public_release=false`), private references, cameo identifiers and home/external paths.
2. Admit only runtime source and the release entry. Exclude test controls, evidence, source exports, original manifests, private character folders and generators.
3. Require each bound media file, verify its hash and trusted containment. Character GLBs must belong to the frozen public manifest **or satisfy the project-local policy below**. Bound internal-only data is rejected rather than silently removed.
4. Copy the referenced closure to content-addressed `res://media/` paths; rewrite bindings, environment, theme and audio paths. Keep original media bytes for the runtime's GLTFDocument/Image/WAV readers.
5. Use a release-only resource-relative boot and game-specific `user://` save location. Export uses Godot compatibility renderer for web portability, not changed authored visuals/story/cast.
6. Scan staged files and final payloads/nested ZIPs, reject symlinks/hardlinks/special files and private/home references. No absolute host-home paths are allowed. This literal/structured scanner is not a general secret classifier and does not certify arbitrary user-authored content's legal clearance.

Official templates contain non-user path strings. Generated web virtual HOME is relocated to `/data/web_user`; macOS/Windows Rust diagnostic roots are relocated to `/build/runner/.cargo/` or `/data/runner/.cargo/`. These narrowly defined equal-length substitutions preserve WASM/PE/Mach-O layout; native Mac output is ad-hoc re-signed, and notices identify the modifications. Arbitrary private paths are **not** sanitized into acceptance. OpenXR `/input/home/click` is not a home-root path and is not altered. Windows execution after diagnostic relocation remains unverified.

## Project characters: local export is not Hub publication

The frozen manifest protects the plugin's redistributable stock cast; it is not a cap on a user's own creations. Local exports also admit:

- **Generated here:** a bound `source=generated` cast row linked to the saved recipe, project character manifest, passing `hermes64-character-build/1.0.0` character-gate receipt and exact original GLB hash. Supported generator IDs are `python`, `blender` and Creator64's `creator`. Recipe hashing follows the relevant writer. Hash-linked locomotion and validated player/enemy derivatives retain admission. Missing review renders remain disclosed as `not_run`, not invented as passes.
- **Owner rights declared:** an owner-authored `assets/PROVENANCE.json` row for the bound source, format `hermes64-provenance/1`, with `source=converted`, exact `file`/`sha256`, `rights_declared=true`, nonempty `owner_approved`, `licence_required=true`, known output and original licences, `gates.ok=true`, and `converted_from={name,sha256,licence}`. `name` is the original basename, not a machine path. Attribution licences need `credit`. Record through `adventure_maker.provenance.record(project_root, row)` after actual gates pass; the exporter does not invent ownership or approval. A community cast/catalog row defaults to internal/NOASSERTION: the owner must explicitly correct those declarations too, not just add another permissive row.

`LicenseRef-Private`, unknown licences, explicit private/internal/restricted flags, cameo content and private references remain refused, even with generated or owner-declared metadata. Denial records in the trusted bundled catalog and project catalog/provenance follow hashes through renamed files, originals, locomotion, waivers and final role derivatives. A rig-quality waiver from `character_waiver` only admits named quality failures; it is **not** evidence of rights. When present its cast/block match is checked, and the original source must separately qualify above. Do not ask an agent to supply an owner's approval itself.

Each non-manifest admission appears as `project_characters` in the closure/export report and as `CHARACTER-PROVENANCE.json` inside the release and beside each target. It says **user-generated** or **user-owned, not part of the public manifest**, with original/final hashes, recipe/generator or rights basis, and skipped checks. Raw receipts and absolute machine paths are not copied. Existing public-manifest/placeholder-only exports gain no disclosure file or report field.

This is a **local-export** exception only. `hermes64_hub` does not call it; its existing source/index, licence and owner-waiver acknowledgement rules are unchanged. Local export does not add a character to the public manifest, publish anything, or confer Hub eligibility.

## Browser acceptance

```sh
/usr/bin/python3 -B -m tools.ship_web_smoke /absolute/path/to/share/web evidence/ship/my-web-smoke
```

The stdlib harness serves only the chosen target on 127.0.0.1, launches installed Google Chrome headless using a new short scratch profile, records CDP console events/errors, sends real E/Enter key input, checks the receiving game's first action, and writes `first-interaction.png` plus `report.json`. A page console error fails the smoke (including a missing favicon). Chrome uses SwiftShader; this is rendered interaction evidence, not GPU performance acceptance.

macOS Chrome needs `MAC_CHROMIUM_TMPDIR` and `CFFIXED_USER_HOME`, not just TMPDIR. Its inner Seatbelt sandbox cannot initialize nested inside another; `--no-sandbox` disables that **inner** layer only, while the harness enforces an outer sandbox permitting writes only in its fresh scratch directory/output and connections only to loopback/local Unix IPC. It never launches the personal browser profile. Browser/server are stopped after the probe. Browser stderr is retained separately from page console errors. This developer smoke is not a public tool or background server.

## License references

- [Godot compliance guidance](https://docs.godotengine.org/en/4.6/about/complying_with_licenses.html): provide the engine copyright/license and third-party notices. Existing game assets still require their own rights clearance.
- Exact bundled sources: [4.6.2 LICENSE.txt](https://raw.githubusercontent.com/godotengine/godot/4.6.2-stable/LICENSE.txt), [4.6.2 COPYRIGHT.txt](https://raw.githubusercontent.com/godotengine/godot/4.6.2-stable/COPYRIGHT.txt). Both are hash-pinned in the exporter.
- [Godot web export](https://docs.godotengine.org/en/4.6/tutorials/export/exporting_for_web.html), [self-contained mode](https://docs.godotengine.org/en/4.6/tutorials/io/data_paths.html#self-contained-mode).

No commercial signing identity, notarization request, external upload, marketplace submission or recipient certification is performed.
