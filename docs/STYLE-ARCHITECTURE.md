# STYLE-CORE: source contracts and integration handoff

## Status and ownership

Implemented the **new-file, source-only portion of migration steps 1–3**. Operational owner: Hermes Main. Executed model header: `gpt-6-astra`, provider `openai-codex`; assignment label “Astra, ultra” is not an independent attestation of the reasoning setting.

No existing runtime, service, pack, bindings, KITS or character file was edited by this lane. The current legacy readers remain in use. These modules are **not yet connected to asset building, the runtime or aggregate promotion**. A resolved profile reports `data_valid_runtime_pending`; requesting runtime readiness rejects with `UNSUPPORTED_CAPABILITY`. This is not yet a “consistent by construction” game-build claim.

The intended product is a project-independent small N64-era 3D adventure toolkit. Style is data, not a required polar theme. This slice admits a bounded catalog of proposed presets; additional looks within those domains are data changes, while new algorithms require reviewed capability extensions. Neither Thaw nor any other demo is the core.

## 1. Baseline receipt: observed, not an approved freeze

`contracts/project/baseline.py` is read-only toward its input tree. It records ownership, raw file hashes, both KITS manifests, both binding authorities, character inventory and each `games/*/.maker/current.json` source/compiled pair. It hashes referenced GLBs, textures and explicit sound files without running generators or importing character-lane code. It performs a second pass over recorded files to flag changes during observation. The output is an observation, **not an atomic snapshot or an owner-approved baseline**.

`contracts/project/baseline-receipt.json` is the original immutable receipt. Do not overwrite it to hide another lane's changes. Its receipt hash is `6a0754235269cfc5d11bc5f89e7cbc4c154d3e98b98391867b142f1c957bb530`.

Observed in that receipt:

- 374 unique files, 1,042 reference occurrences: 902 pinned matches, 130 pinned mismatches, 10 existing but unpinned. No missing referenced files were reported. Reference occurrences are not unique asset counts.
- KITS build-key comparison: 101 root entries have an explicit `source_sha256` matching the library record, 12 have different revisions without that explanation, and 8 exist only in the root manifest. A recorded source transformation does **not** make an obsolete library file hash pass.
- Root `bindings.json`: 22 non-placeholder character rows. `kits/bindings.json`: 22 placeholder rows. `assets_v3.runtime_snapshot` still reads the latter; this lane did not switch authority. The char-integration adapter is a separate, owner-controlled path.
- At observation time the character manifest contained 29 rows, including one restricted row and nine reported actor totals above the profile's 700-triangle total ceiling. This is an inventory observation, not independent rig validation. The character owner subsequently changed the manifest; do not interpret the initial count as current release contents.
- Both observed current pointers matched their compiled source. The Thaw starter differed from its current source; Last Light's did not. Migration must use the verified pointer, not reset to `source/spec.json`.

The later readback in `contracts/project/evidence/final-02/verification.json` correctly reports baseline drift, including `characters/manifest.json`, `packs/polar_pod/view.json`, `runtime/godot/actors/test.gd`, and `tools/import_characters.py`. `contracts/project/evidence/03-baseline-drift.json` preserves the earlier drift check. This was expected concurrent-owner activity, not repaired by STYLE-CORE. Main must obtain a fresh, explicitly approved handoff and resolve the mismatch categories before shared integration. **Step 1's accepted/frozen-baseline gate remains open.**

Commands from the repository root:

```sh
PYTHONPATH=. python3 -B contracts/project/baseline.py snapshot --root . --output contracts/project/NEW-RECEIPT.json
python3 -B contracts/project/baseline.py verify --root . --receipt contracts/project/baseline-receipt.json
```

`snapshot --output` uses exclusive creation; `verify` exits 1 for changed or missing recorded targets. Receipt-integrity failure is also an error. Verification covers exact recorded targets, not a whole-tree additions audit; newly created files require a new owner observation. An unchanged receipt never overrides its recorded mismatches. These internal receipts/logs include legacy provenance and are **not a public release allowlist**.

## 2. Style API and encoding

`adventure_maker/style_profile.py` is Python 3.9 stdlib only. It imports no Blender, Godot, generator, character, external schema validator or network client.

| API | Contract |
|---|---|
| `resolve_profile(root, path, parents=None, require_runtime=False)` | Load confined JSON, validate authored sections, resolve base → child, validate each intermediate effective profile, snapshot resources and return `ResolvedStyle`. `parents` maps `(id, version)` to a root-relative profile path; absent entries use `<id>/profile.json`. |
| `ResolvedStyle.profile`, `.canonical_bytes` | Fully resolved 14-section data and authoritative canonical bytes. Dicts are caller-owned working copies, not immutable authorization objects. |
| `.parents`, `.resources`, `.resource_bytes` | Base-first authored revision pins; sorted resource records; exact captured resource bytes keyed by `profile-id@version/resource-id`. Consumers must use snapshots rather than reopen unchecked paths. |
| `.closure_sha256`, `.lock_bytes`, `.status` | Content closure and canonical closure receipt. No timestamp, cwd or absolute project path enters the hash. Status remains `data_valid_runtime_pending`. |
| `parse_json`, `canonical_bytes`, `digest` | Duplicate-key, nesting/size and nonfinite rejection; sorted-key compact UTF-8 JSON; SHA-256. Array order and numeric representation are preserved. No implicit Unicode or numeric normalization. |
| `validate_schema` | Bounded evaluator of the bundled contract's used subset, not a general Draft 2020-12 implementation or metaschema certification. Anchored identifiers are full matches, including rejection of trailing newlines; bool is not numeric zero. |
| `effective_bounds(core, profile, variation)` | Intersection of numeric/integer/enum/boolean domains. Empty intersections, type mismatches or defaults outside the intersection reject. |
| `constrain(value, bounds, clamp_explicit=False)` | Reject by default. Numeric clamping requires an explicit request **and** an effective `clamp_explicit` policy; receipt contains requested/effective values, clamped flag and bounds. Enum/boolean/type errors never clamp. |
| `palette_contains`, `require_palette` | Exact source-texel RGB8 membership; optional named allowed set. Material-factor or vertex conversion tolerances must be explicit and no larger than the profile allows. Lit framebuffer pixels are not tested as exact source colors. |
| `legacy_pack_projection(root, pack_id)` | Read `packs/<id>/pack.json` and `view.json` without mutation. Map partial palette/material/light/kit/exterior/UI/audio/validator fields while retaining the separate authorities and raw file hashes. Return `legacy_projection_incomplete`; never pass it off as a full profile or load a different kit pack. |

The authored schema is copied from the architecture lane to `contracts/style/1.0.0.json`. `contracts/style/capabilities-1.0.0.json` is a frozen **validation-domain catalog**, with the observed manifest digest and seven selected KITS parameter schemas. It contains proposed character/UI/audio/validator capability IDs; it is deliberately labelled `contract_only_runtime_unbound`. Matching a catalog ID is not proof that the corresponding profile ABI exists. No caller-provided flag can turn `require_runtime=True` into a pass in this slice.

### Inheritance and closure rules

- A base supplies every section. A derived section replaces that whole section; there is no recursive dictionary merge, list concatenation or implicit deletion syntax.
- Every parent reference pins the canonical **authored** parent hash, ID and version. Cycles, duplicate identities, wrong pins and more than 16 ancestry nodes reject. Invalid parent semantics cannot be concealed by replacing the bad section in a child.
- Each profile lives in its own directory. The directory contains only its profile JSON and declared resources (plus necessary resource subdirectories). Hidden or unlisted files/directories, symlinks, case-colliding paths, executable mode bits, nonregular files, URLs, absolute paths and dot/traversal components reject. Reads use no-follow directory/file descriptors and compare file identity/size/mtime during reading.
- Resource IDs are scoped to their owning profile. The closure retains **all ancestor resources**, even if the child replaces sections or has an empty resource list. Resource hashes cover actual bytes. The closure also pins authored ancestry, the resolved document, schema, catalog and resolver implementation.
- Limits: 1 MiB JSON, 8 MiB per resource, 32 MiB resource closure, 128 declared resources per authored profile. Parsing never imports or executes data.
- Admitted encodings are intentionally narrow: bounded non-interlaced 8-bit PNG (RGB/RGBA/indexed, no metadata chunks), simple PCM WAV, self-contained GLB envelopes. Texture/atlas/font/LUT resources currently use PNG; animation resources use GLB. TTF/OTF, external GLB URIs, extensions/extras, arbitrary sidecars and other encodings reject rather than guess. Embedded GLB bytes are included in its hash, but this envelope check is **not** full accessor/mesh/rig/texture/pose validation. Those remain step 4/5 consumers.
- Semantic checks include finite numbers, ordered ranges/defaults, integer rules, cross-field colors/roles/moods, selected generators and parameter names, generator core domains, presets/fallback cycles, nonzero light directions, fog/camera/depth order, palette/light/triangle ceilings, character palette/actor budget bounds, audio gains and required error-level metrics.
- No imported-resource palette or rendered-appearance acceptance is implied. `require_palette` is available now; all generated/imported payload paths still need the step 4 build gate.

### Shipped data

`profiles/n64_base/profile.json` is neutral generic low-poly data. `profiles/examples/polar_pod/profile.json` and `profiles/examples/warm_desert/profile.json` are explicitly labelled examples derived from the architecture lane. They inherit rendering defaults and replace aesthetic sections. Descriptions are generic; selected-generator material-role aliases were completed and the children re-pinned to the edited base. `contracts/style/example-provenance.json` records source hashes and derivation changes. `derive_examples.py` is an exclusive-create reproduction helper, not a runtime importer.

The profiles contain no copied cast, private references, absolute home paths or borrowed demo story. All three resolve deterministically to 14 sections. They are **data examples only**, with no rendered proof or aesthetic approval.

## 3. Project API and ownership

`contracts/project/1.0.0.json` defines the strict manifest. `contracts/project/bindings-1.0.0.json` defines logical maps, not arbitrary file imports.

| API | Contract |
|---|---|
| `load_project(root)` | Read and validate `project.json` and its explicit, confined relative paths. Never infer a project from cwd or search the plugin's packs for missing content. |
| `Project.assemble()` | Merge story, explicit ordered room files, cast and bindings; validate the existing logical story contract; return spec, bindings, ownership receipt and deterministic content hash. This is source assembly, not a build/promotion transaction. |
| `assemble_content(story, rooms, cast, bindings)` | Pure in-memory merge. Story cannot also own `rooms`, `characters` or `bindings`, even if values are identical or empty. Duplicate room/character IDs and repeated manifest paths reject. Authored text and IDs are not rewritten. |
| `split_legacy_spec(spec)` | Pure migration preview: move rooms and characters to their owners, retain all other logical fields, return empty explicit binding maps. No inferred visual identity and no disk writes. |
| `read_legacy_current(root)` | Resolve `.maker/current.json`, validate compiled integrity and source equivalence, report stale-starter differences. A missing, corrupt or escaping pointer never falls back to starter. |
| `Project.resolve_style()` | Resolve project-relative profile/parent paths and enforce selected ID/version. |
| `make_style_lock(resolved, toolchain=None)` | Return a deterministic record. No write, approval or auto-adoption occurs. |
| `Project.verify_style(toolchain=None, require_runtime=False)` | Recompute closure and exact expected lock, compare it with the stored record and manifest lock digest. Tampering or profile/resource/toolchain drift rejects. No automatic re-pin. |
| `migrate_manifest(manifest, target_version='1.0.0')` | Same-version validated copy only. Any unsupported source/target version returns `MIGRATION_REQUIRED`. |

Field ownership: `story/spec.json` owns all existing story fields except `rooms` and `characters`; each listed room file owns one complete room; cast owns the complete logical `characters` array; bindings own `assets`, `cast`, `audio`, `icons` maps. The binding values currently select a profile prop recipe, character family, audio cue or icon collection. They are not external paths. Broader exact-asset/rig/clip imports require the versioned step 5 contract. `Project.assemble()` checks declared binding targets but does not assert that empty maps supply a playable runtime.

`style.lock` contains a canonical-encoding ID, selected profile, closure receipt/hash, toolchain record, inner record digest, `approval: null` and `runtime_ready: false`. `project.json` pins the digest of the entire lock record, including its inner digest. The default toolchain pins this source slice and the existing story Python files plus Python version. Its `plugin.version: 1.0.0` is this **slice contract version**, not an invented released plugin version; `scope` is `style_core_source_slice`. Engine/renderer/generator/character-runtime versions are explicitly `not_bound`. A future bound toolchain must add exact implementation/engine pins and migrate deliberately, not relabel this lock as runtime-ready.

`projects/starter-sketch/` is a two-room **layout skeleton** with an empty cast, empty bindings and a vendored neutral profile. Minimal clock/ending fields only satisfy the old compiler. The whole directory was copied outside the plugin tree and both assembly and lock verification passed. It is not a showcase or a runnable graphics demo. `seal_starter.py` demonstrates creating a new skeleton lock; it refuses existing destinations.

## 4. Exact downstream patch specification: steps 4–6, NOT APPLIED

These are symbol-level patch targets, argument changes and required replacement behavior, not claims of implemented adapters. Re-read the owner-approved versions before applying: the baseline intentionally detects drift. Do not apply a one-line call-site change while the required producer/consumer contract is missing.

### Step 4: asset consumer (room-look handoff required)

1. **`adventure_maker/adapters.py:Components.assets`** currently takes `(game, folder, seed, pack)` and validates the legacy pack before calling `assets_v3.build`. Add a keyword-only project-model input while retaining the old call shape for explicitly legacy projects. For the new path, call `Project.verify_style()` and `Project.assemble()`, then pass the resolved style, project binding map and lock receipt through to the builder. Until a bound-runtime toolchain exists, reject new-style asset builds rather than converting `data_valid_runtime_pending` into success. The legacy path must not silently handle a project whose manifest names a style lock.
2. **`adventure_maker/assets_v3.py:build`**: extend `(c, game_path, folder, seed, pack)` with keyword-only `resolved_style`, `content_bindings`, `style_lock` for the new path. Replace `kits/packs/<kit_pack_id>/pack.json` lookup and pack-ID binding fallback with projections of the verified snapshot. Replace hardcoded request presets with selected profile recipes plus explicit content requests. Every cache key must include `closure_sha256`, exact toolchain digest, generator ID/version, seed, **effective** parameters and encoding. Apply this to both the ordinary key at current line 30 and the room-shell key in `build_shells` at current line 101; changing only palette must cause real rebakes in both paths.
3. **`kits/core/pipeline.py:get_pack`, `resolve`, `build_one`; `kits/core/packs.py:Pack`**: add a data-only projection entry point that consumes the resolved palette/material/role/environment/recipe snapshot. Do not resolve a missing profile field using another installed pack. Preserve old `get_pack(pack_id, path)` only in explicit legacy mode. `build_one` already has `pack_path`; add the missing explicit CLI argument in **`kits/build.py:main`**, and carry it for single and batch jobs to `build_one`. Today the CLI only exposes `--pack`; do not pretend `--pack-path` is already implemented.
4. **`kits/core/schema.py:resolve`**: add keyword-only effective-domain/clamp inputs, validating each parameter layer before merge, then intersect core → profile → permitted variation. Use `effective_bounds`/`constrain` semantics and return/disclose the clamp receipts alongside effective values. Retain `_check_value`'s strict types and core ceilings. Complex generator cross-parameter predicates remain generator-owner validators, not guessed style code.
5. **`assets_v3.build_shells`**: on the locked-style path, an absent selected kit or exhausted candidate list is `asset_failed`, not the current `status: legacy` result. Permit fallback only along the profile's validated fallback graph, and record the chosen candidate. Do not let line 138's rejected-every-candidate state pass the aggregate build.
6. **`assets_v3` sidecars and `kits/core/pipeline.py:validate_file`**: pin closure, generator/source hash, seed, effective parameters, output hash, source-palette checks and independent structural/budget validation on every generated/imported GLB and texture. Preserve current `glb_validate` checks; do not replace them with the new envelope validator. Color membership applies to texels/material factors/vertex sources, not illuminated screenshots. Add `tests/test_profile_assets.py`: palette-only rebake, no stale env/binding fallback, off-palette byte, out-of-range value, disclosed clamp and exhausted-shell failure.

### Step 5: character consumer (characters AND char-integration handoffs required)

1. **`tools/import_characters.py:build_bindings(fallbacks, records)`** currently indexes hardcoded `ROLES`/`COATS` using `authored_variant`. Change the new project path to accept `(project_cast_bindings, records, resolved_style)` and select exact pinned asset identity by stable story character ID, not current narrative role. Move demo-specific tables to project/legacy fixtures; do not rename/rewrite imported owner snapshots. Add a versioned binding shape for exact asset digest, family/body/rig, clip IDs, attachment slots and rights flags; the current family-only map is insufficient for import acceptance.
2. **`characters/integration.py:stage_runtime(runtime, root=ROOT)`** currently reads root `bindings.json`. Add the explicit validated project binding snapshot as input; verify/copy only its closure. Keep its owner adapter/`CharacterComponents.prepare_runtime` intact until Main chooses the shared facade seam. Do not silently switch `assets_v3.runtime_snapshot` from kit placeholders to root cast as a “fix.”
3. **`runtime/godot/actors/assets.gd:character`, `character.gd:configure/play_clip` and `view/assets.gd:character`**: resolve stable character identity from the compiled binding snapshot; reject wrong hashes or unsupported rigs/clips. Placeholder fallback is only an explicitly admitted legacy/optional policy, never proof of fidelity. The story role edit must not swap the person's body/rig or erase identity.
4. Enforce profile skin/costume palette, admitted proportions, clip/attachment domains and body/attachment/total budgets. The observed importer currently allows props up to 200 triangles (`inspect_glb`) whereas this profile schema caps attachments at 150 and total actors at 700. **Resolve that versioned contract conflict with the owners; do not raise the style ceiling to hide it.** Keep restricted records/bytes out of distributable closures, including indirect dependencies. Add `tests/test_profile_characters.py` plus real owner pose/animation/budget proof.

### Step 6: one compiled runtime style (room-look + char-integration handoffs required)

1. **`assets_v3.runtime_snapshot(c, game, folder)` and `Components.prepare_runtime`**: pass the same verified style/binding/lock snapshot used by the build, and emit one versioned `runtime/style.json` plus closure-bound resource/binding/audio manifests. Remove new-style `packs/<id>/view.json` / kit-pack lookup, implicit `kits/bindings.json`, ambient `env_root` and cached overrides selected only by legacy `pack_sha256`. Keep explicitly labelled legacy handling separate. Copy resources into the runtime snapshot using relative paths and content hashes, never store developer-home paths in portable output.
2. **`runtime/godot/view/presenter.gd:boot`**: before `build_screen`, read and verify the supplied compiled style and exact lock/resource digests. On the new-style path remove line 56's `style_pack/default` discovery and lines 58–59's default-pack fallback. Missing/mismatching data returns a failed boot. Do not merely assign new JSON to `theme` while the old consumers still read their own defaults.
3. **`look/pack.gd:load_pack/color/rig/ui`; `look/rig.gd:profile/apply`; `presenter.gd:apply_room_look`**: consume the compiled style. Replace arbitrary `presentation.look` dictionary overwrite with a validated mood ID and only declared `variation.room_numeric` values. Map palette tokens explicitly; `ambient/key/fill/rim`, directions, fog near/far/density and grade come from the selected mood. Reject unknown mood/field; remove implicit interior-profile fallback for the locked path. Shader registration defaults remain boot plumbing, not style authority.
4. **`presenter.gd:build_screen`, `view/room.gd:build`, `look/n64_mat.gd`, world/post shaders and `project.godot`**: use compiled render resolution/filter/upscale, camera bounds and material response. Replace literal `Vector2i(320, 240)` at presenter line 104 and size-dependent UI/capture assumptions together. Validate camera/occlusion and material roles before applying. Current global-uniform and shader defaults must match the supported compiled ABI; unsupported filter/material modes remain rejected until implemented/proved.
5. **`look/ui.gd:apply_theme/_ready/_process`**: replace hardcoded W/H/CPS, skin colors and item-specific bitmap defaults with validated UI/profile/content projections. Pin font/icon resources, enforce permitted source colors and test contrast. Keep primitive rendering code generic.
6. **`view/audio.gd:boot/trigger`**: use each compiled cue's explicit gain/loop policy, not hardcoded `-21` / `-15`; require every pinned WAV/hash and profile channel/rate/duration/peak/seam domain. A missing audio manifest or a hash failure is not silent success. Dummy headless loading still cannot prove audible output.
7. Add runtime profile tests and real captures covering identical story/ABI under two contrasting styles, actual internal resolution, all room/camera IDs, source resource/palette mutations and visible character integration. Do not set the catalog's runtime-ready state until those consumers and receipts exist. Aggregate promotion, lock-bound saves and user approval remain **step 7+**, not an implied result of these patches.

## 5. Executed verification

Final source receipt: `contracts/project/evidence/final-02/verification.json`. Python **3.9.6**, all four selected commands exit **0**:

| Suite | Tests | Real elapsed | Raw evidence |
|---|---:|---:|---|
| `python3 -B -m unittest discover -s tests -p 'test_style_profile.py' -v` | 33 | 0.758s | `final-02/style.log` |
| `python3 -B -m unittest discover -s tests -p 'test_project_model.py' -v` | 15 | 0.370s | `final-02/project.log` |
| `python3 -B -m unittest tests.test_packs tests.test_safety tests.test_boundaries -v` | 44 | 6.808s | `final-02/legacy-fast.log` |
| `PYTHONPATH=tests_story:. python3 -B -m unittest test_compiler test_engine test_edits test_saves -v` | 33 | 2.967s | `final-02/story-fast.log` |

**125 tests total.** The style invalid-mutation table contains **30 controls**, in addition to path, resource, ancestry, duplicate-key, nonfinite, malformed-container and clamp tests. Grandparent-resource retention is separately exercised. Existing boundary engine outputs are explicit test doubles, not actual Blender/Godot runs.

Fail-first evidence is retained in `contracts/style/evidence/01-wiring.log` and `contracts/project/evidence/01-wiring.log`: these establish missing wiring, not behavioral RED for every stopped test. The first implementation run exposed the macOS system-temp symlink harness; the harness was confined, not the symlink guard weakened. Later hardening regressions actually reproduced invalid-parent hiding, huge-integer overflow, malformed PNG/GLB exceptions, unknown GLB payload acceptance and trailing-newline ID acceptance (`04-hardening.log`, `05-glb-control.log`, `06-id-control.log`) before the fixes. Baseline-passing preservation checks are not relabelled RED.

The final runner sets a real external scratch directory. It independently copies the skeleton outside the plugin, resolves every declared path, compiles the assembled source and verifies the exact lock. It also re-resolves all three profiles twice and records byte equality. The existing Last Light example's input bytes remain unchanged, and split/reassembled `spec_hash`, `game_hash` and every room `build_hash` match. The recorded logical game hash is `793b10a506e1420172a0306e4f08ae118bd1589fb297babaf3bfe99d5e446b34`.

Reproduce with a fresh evidence label and an existing external scratch directory:

```sh
PYTHONPATH=. python3 -B contracts/project/verify_source.py --label review-01 --scratch "$TMPDIR"
```

The runner never refreshes locks, repairs the baseline or invokes an engine. It records baseline drift separately from source-test results. Its zero exit means only the selected source suites passed, **not** baseline freeze, runtime integration or release acceptance.

## 6. Explicitly not done / remaining gates

- Main-approved immutable integration baseline; 130 recorded reference-hash mismatches and ongoing owner drift still need reconciliation.
- Steps 4–6 consumers, full generator/character capability certification, full binary asset/pose validation and build-time palette enforcement.
- Blender/Godot execution, real captures, audio listening, two-style rendering proof, human aesthetic approval.
- Aggregate build gate/promotion, service/tool/schema wiring, lock-bound saves or cross-version migrations.
- General GLB import, broad font/resource encodings, arbitrary generator parameters, private-demo extraction or repository split.
- `verify_all.sh`, full repository tests, installed-Hermes loading, package/release/privacy/history audit, network, installs, delegation, remote or push operations.

The local commit is limited to STYLE-CORE's new paths; unrelated files/commits remain under their owners. The exact commit hash is supplied in the final handoff. No artifact here authorizes a public release.
