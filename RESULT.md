# ASSEMBLY result — local integration acceptance

Owner: Hermes Main. Bounded executor: Astra / Prometheus. Local prototype only; not release/catalog or human-quality acceptance.

## Executed environment and source pin

- Python: `3.9.6 (default, Oct 19 2026, 19:18:13) `; verifier executable `/Applications/Xcode.app/Contents/Developer/usr/bin/python3`.
- Existing Blender 5.2.1 LTS and Godot 4.6.2; windowed Mobile/Metal renderer. No install, download, export template, network/public operation or live Hermes activation.
- The receipts below are historical implementation evidence from commit `89b383de9ed3bf83d1fe4b83fc16c06764afa1cc`, not current-package acceptance. Current-package receipts are `docs/FINALINT4-RESULT.md` (rc7) and `docs/FINALINT5-RESULT.md` (rc8, to be produced by the integrator); these are repository-only release records. The catalog PR pins the public repository's own full commit SHA. No future pin or rc8 result is asserted here.
- 130 source files match the verifier's captured SHA-256 values; no changed source silently credited to an earlier run.

## Reproduce and exact command receipts

From this repository:
```sh
sh tools/verify_all.sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.e2e --showcase
PYTHONDONTWRITEBYTECODE=1 python3 -B -m tools.provenance_audit
```
The showcase command was run once and refuses existing projects. The audit is one-time evidence and refuses overwriting its receipt. Verifier reruns allocate fresh output/screenshot directories. The shell defaults to system `/usr/bin/python3`; `HERMES64_PYTHON` may explicitly choose another already-installed interpreter. Child discovery is aligned with that interpreter.
Full exact argv, exit status, timing and unabridged outputs: `evidence/verify-20261108T004605354230Z/commands.json`, `*.stdout.txt`, `*.stderr.txt`; engine argv/results: `evidence/verify-20261108T004605354230Z/runtime/commands.json`. Child Blender argv/stdout/validation and Godot reports are also retained under each project `.maker/runs/`.

Measured outputs:
```text
story: Ran 98 tests in 11.170s; OK; exit=0
plugin: Ran 86 tests in 17.589s; OK; exit=0
audio: Ran 69 tests in 398.517s; OK; exit=0
UNIT SUMMARY passed=36 failed=0
SAVE SUMMARY passed=13 failed=0
PRESENTATION SUMMARY passed=22 failed=0
THEME SUMMARY passed=7 failed=0
WIRE SUMMARY passed=7 failed=0
```

**253 Python unittests passed** (story 98, plugin 86, audio 69); **85 Godot assertions passed** across five native suites. No native-suite stderr in the final run.

| Stage | Exit | Measured seconds |
|---|---:|---:|
| story | 0 | 11.334 |
| plugin | 0 | 17.776 |
| runtime | 0 | 2.354 |
| e2e | 0 | 47.773 |
| audio | 0 | 398.803 |

## Real facade execution

Full 30-call payload/result log: `evidence/verify-20261108T004605354230Z/e2e/calls.json`. Summary: `evidence/verify-20261108T004605354230Z/e2e/summary.json`.
Separately created `games/last_light` and `games/thaw` through the same facade: `evidence/e2e-20261108T003730019528Z/calls.json` and `summary.json`. Thaw's current pointer includes the three accepted edits; source/game revisions were not hand-authored.

```text
last_light scaffold scaffolded_unvalidated
last_light compile compiled
last_light compile compiled
last_light check proved
last_light build_assets passed
last_light build_assets passed
last_light replay passed
last_light open captured
thaw scaffold scaffolded_unvalidated
thaw compile compiled
thaw compile compiled
thaw check proved
thaw build_assets passed
thaw build_assets passed
thaw replay passed
thaw open captured
thaw edit edited
thaw check proved
thaw replay passed
thaw edit edited
thaw check proved
thaw replay passed
thaw edit edited
thaw check proved
thaw replay passed
thaw compile compiled
thaw benchmark passed
thaw compile compiled
thaw check proved
thaw replay passed
sheet evidence/screens/capture-20261108T004636869459Z/contact-sheet.png: 1928x1930 from 10 images
{"status": "passed", "calls": 30, "evidence": "evidence/verify-20261108T004605354230Z/e2e", "contact_sheet": "evidence/screens/capture-20261108T004636869459Z/contact-sheet.png"}
```

| Game | Rooms | Initial proof witnesses | Engine steps | New Blender builds | Repeat cache hits |
|---|---:|---:|---:|---:|---:|
| last_light | 4 | 2 | 29 | 3 | 3 |
| thaw | 6 | 22 | 108 | 3 | 3 |

Same spec compile outputs compared equal; real repeat builds produced zero builds with cache hits. This is cache reuse, not a claim of cross-version/platform Blender byte determinism. Proof replay checks all claimed endings/collection witnesses and real disk save/load; visual room coverage uses deliberate initial-state teleporting, not physical traversal proof.

## Measured benchmark — three explicit sequential edits

| Edit | Changed room | Unchanged rooms byte-identical | Valid / identity | Solvable | Save migration | Godot replay + migrated load | Asset validation | Result |
|---|---|---:|---|---|---|---|---|---|
| E1 workstation bay_hatch → north, position 2 | workstation | 5 | pass / True | proved | migrated | passed / loaded | passed | PASS |
| E2 Neri → authored saboteur role | workstation | 5 | pass / True | proved | migrated | passed / loaded | passed | PASS |
| E3 Shared Glow ending | conversation_pit | 5 | pass / True | proved | migrated | passed / loaded | passed | PASS |

3/3 fully verified for **this stated list**, with the live revision pointer unchanged by the benchmark. The save fixture is mid-dialogue, with found cat and sphere identities retained. Exact expected changed-room equality is required. Asset validation covers measured GLB budgets/integrity/encoding and source builder checks; it is not perceptual style approval or rig/animation acceptance. Historical transport doubles remain separately labeled negative/unit fixtures and supply no real-integration pass evidence.

## Screenshots and measured geometry

Contact sheet: `evidence/screens/capture-20261108T004636869459Z/contact-sheet.png`. Each room also has a full-window PNG in the same game directory. Images were viewed; [ASSEMBLY-CRITIQUE.md](docs/ASSEMBLY-CRITIQUE.md) records visible strengths and defects.

| Room | Conservative scene triangles | World capture |
|---|---:|---|
| last_light/boathouse | 1150 | `evidence/screens/capture-20261108T004636869459Z/last_light/boathouse-world.png` |
| last_light/fog_street | 1862 | `evidence/screens/capture-20261108T004636869459Z/last_light/fog_street-world.png` |
| last_light/keepers_cottage | 1180 | `evidence/screens/capture-20261108T004636869459Z/last_light/keepers_cottage-world.png` |
| last_light/lamp_room | 1082 | `evidence/screens/capture-20261108T004636869459Z/last_light/lamp_room-world.png` |
| thaw/conversation_pit | 2280 | `evidence/screens/capture-20261108T004636869459Z/thaw/conversation_pit-world.png` |
| thaw/curved_corridor | 1934 | `evidence/screens/capture-20261108T004636869459Z/thaw/curved_corridor-world.png` |
| thaw/dome_shelter | 2182 | `evidence/screens/capture-20261108T004636869459Z/thaw/dome_shelter-world.png` |
| thaw/pod_bay | 3870 | `evidence/screens/capture-20261108T004636869459Z/thaw/pod_bay-world.png` |
| thaw/snow_field | 2378 | `evidence/screens/capture-20261108T004636869459Z/thaw/snow_field-world.png` |
| thaw/workstation | 2318 | `evidence/screens/capture-20261108T004636869459Z/thaw/workstation-world.png` |

All ten rooms are below the 6,000-triangle room ceiling. Real kit geometry, LOOK shaders/UI, pack fog/palette, explicit sRGB8 and exact-hash character markers are used. Both pack ambient/interact WAVs hash-check and load; no listening claim. Headless checks load WAVs but do not start a nonexistent audio device; windowed previews retain playback.

## Provenance, package and size

- `PROVENANCE.json`: 739 copied files, 739 unique destinations, 19,693,779 original bytes, all source hashes and lane CHECKPOINT/RESULT receipts still match. `evidence/provenance-audit.json` has the audit; original receipt copies are under docs/sources. Siblings were read-only.
- KITS 3.1: 43 generators / 113 manifest builds. Original hashes retained through relocated paths and explicit colour transformation; initial 141 GLBs converted, plus a separately derived, recorded glass-orb binding. 22 exact full-parameter character placeholder selectors record empty bones/animations, never presented as human_16/cat_8 rigs.
- Presentation documentation note 1.1.1 leaves wire versions/semantics at 1.0.0/1.1.0. Existing metadata-free fixtures pass. Last Light maps n64_v0 explicitly to forest environmental kits; pack differences live in data, not runtime game-name branches.
- Git-eligible source/data package: **20.19 MiB**, 21,174,673 bytes / 811 files at measurement. Whole working directory including retained local evidence and runtime products, excluding .git: **106.83 MiB**, 112,019,856 bytes. Measured before this report and later receipt documentation; exact measurement in `docs/ASSEMBLY-EVIDENCE.json`.
- `.gitignore` excludes generated caches, logs/evidence, runtime copies, .godot and bytecode. No lane caches/log collections/large evidence trees were copied; three small frozen audio regression receipts are intentionally retained. No absolute home paths found in audited production code. Project-generated local execution receipts naturally contain resolved local paths. No credentials were needed or copied. This is not a catalog security-scan verdict.

## Failed attempts retained, not relabeled

- Initial assembly/real-build suites exposed missing manifests, binding seams, parser/import/API mismatches and historical fixture paths; repaired in assembly copies only.
- An earlier direct audio run timed out at 300 seconds. The full suites later completed; no timeout was called a pass.
- `evidence/verify-20261108T003419737033Z` passed under the background shell’s existing Python 3.14, not the assumed system 3.9. The final wrapper now pins the system interpreter by default and records its actual version.
- Runtime stage02–05 retained failing audio-shutdown warning assertions. Stop/clear cleanup and avoiding playback under headless Dummy audio fixed them; stage06 and the final suite passed without native stderr. Merely delaying test exit did not fix the cause and was removed.
- `evidence/verify-20261108T004357349472Z` correctly exited nonzero on a repeated screenshot-directory collision. Each invocation now allocates an independent fresh capture directory; prior evidence was not overwritten.
- A verbose diagnostic still reports upstream optional glTF packed-buffer byteStride warnings; normal imports render correctly. No claim of an externally certified glTF validator pass is made.

## Explicitly NOT verified / remaining owner gates

- Real Hermes plugin discovery/load, live registration/approvals behavior, released minimum Hermes compatibility version, install security scan, catalog CI/admission and public pin.
- Other computers/OSes, web/Compatibility exports, export templates, packaging/distribution or deployment.
- Actual character-lane assets, bone retargeting, shared rig/deformation/animation tests, costume/coat fidelity and held-frame character animation. All characters remain marked placeholders; manifest-only replacement is documented, not real-character acceptance.
- Listening, subjective audio quality, human movement/camera/UI feel, spatial reachability/collision perfection, narrative staging and final visual/style acceptance. Legal actions are exposed in a menu without proximity gating.
- Arbitrary natural-language generation/edit precision, automatic rebaking of arbitrary project palettes, and all 43 kit parameter sweeps in this assembled run. Main’s prior lane verification is provenance, not a claim that those sweeps were rerun here.
- At that pin: no public repository, push, catalog PR, X demo, Typeform, contact, install or live activation. Optional combat/lab-building backlog remains unstarted. Real character landing and independent review return to Main, not a competing queue.
