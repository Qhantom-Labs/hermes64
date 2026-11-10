# Merged-generator parity re-run

**Default promotion remains BLOCKED. Blender is the default; Python/auto remain explicit opt-ins. No art or golden approval.**

Fresh run: `python3 -B -m tools.parity_noblender --out evidence/merge/parity-matrix --samples 3 --render`.
The command returned 1 because strict parity is incomplete. It did not crash. Both worker processes returned 0.
All 276 unique rows and current source pins were read back and all numeric comparisons independently recomputed. Sources include the merged fidelity generators, assembly and textures.

- Strict parity: **249/276**; Python valid: **272/276**; Blender valid: **272/276**.
- Earlier no-Blender lane: 249/276 strict passes. Net delta **+0**, changed case verdicts **0**. Equal pass totals do not imply identical rendered assets.
- Fixed Godot subset: **12/12** pairs pass existing 0.1 pixel threshold / 0.02 frame-fraction gate; not all-case visual parity.
- Thresholds were not widened: bounds/UV/normal mean 1e-5, colour mean 1/255; topology, histograms, material metadata and embedded texture hashes exact.
- Receipt and sources: `evidence/merge/noblender-parity/`, `evidence/merge/parity-matrix/`; aggregate: `evidence/merge/parity-summary.json`.

## Fresh per-generator table

Each pack is `Python valid / strict parity / cases`.

| Generator | polar_pod | forest_village | Differing fields |
| --- | --- | --- | --- |
| arch.bridge | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.ceiling_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.column | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| arch.corridor | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.door | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.floor_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.house | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.pier | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.railing | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.roof | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.room_shell | 3 / 0 / 3 | 3 / 0 / 3 | colour_histogram, colour_mean, normal_mean, roles, triangles, vertices |
| arch.stairs | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.tower | 3 / 1 / 3 | 3 / 3 / 3 | colour_histogram, normal_mean, vertices |
| arch.wall_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.window | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.bed | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.bench | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.chair | 3 / 2 / 3 | 3 / 2 / 3 | normal_mean |
| furn.console | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.container | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.hearth | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.lamp | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.pod | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| furn.rug | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.shelf | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.table | 3 / 1 / 3 | 3 / 3 / 3 | normal_mean |
| fx.particles | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.bush | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.grass_tuft | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.rock | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| nature.tree | 3 / 3 / 3 | 3 / 2 / 3 | normal_mean |
| prop.book | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.device | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.key | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.sign | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.tool | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.vessel | 3 / 2 / 3 | 3 / 2 / 3 | normal_mean |
| sky.backdrop | 3 / 3 / 3 | 3 / 3 / 3 | none |
| soft.blanket | 3 / 3 / 3 | 3 / 3 / 3 | none |
| soft.pillow | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.patch | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.vista | 2 / 3 / 3 | 2 / 3 / 3 | none |
| terrain.water | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.yard | 2 / 3 / 3 | 2 / 3 / 3 | none |
| vehicle.boat | 3 / 3 / 3 | 3 / 3 / 3 | none |
| vehicle.craft | 3 / 3 / 3 | 3 / 3 / 3 | none |

## Quantified differences

The prior diagnosis remains consistent with this run: room-shell hole tessellation/topology differs; the tower has a glow vertex split; smooth-shape normal means miss the strict limit. Both builders fail the same four extreme terrain origin/extent samples. These are gate failures, not grounds to change thresholds.

Failure-field occurrences (cases may contribute more than one): `{"colour_histogram": 8, "colour_mean": 4, "normal_mean": 25, "roles": 4, "triangles": 8, "vertices": 6}`.

| Generator with differences | Max triangles Δ | Max vertices Δ (node) | Max normal mean Δ | Max colour mean Δ |
| --- | ---: | ---: | ---: | ---: |
| arch.column | 0 | 0 | 1.45463525e-05 | 4.4408921e-16 |
| arch.room_shell | 2 | 6 | 0.0173229369 | 0.00723529412 |
| arch.tower | 0 | 4 | 0.00185376923 | 6.66133815e-16 |
| furn.chair | 0 | 0 | 1.57023585e-05 | 6.66133815e-16 |
| furn.pod | 0 | 0 | 3.72582407e-05 | 9.99200722e-16 |
| furn.table | 0 | 0 | 1.60585176e-05 | 9.99200722e-16 |
| nature.rock | 0 | 0 | 3.65796414e-05 | 3.33066907e-16 |
| nature.tree | 0 | 0 | 1.21183693e-05 | 8.8817842e-16 |
| prop.vessel | 0 | 0 | 1.8868934e-05 | 3.33066907e-16 |

Source-validation failures:
- `terrain.vista__polar_pod__2`: `{"blender": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}, "python": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}}`
- `terrain.vista__forest_village__2`: `{"blender": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}, "python": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}}`
- `terrain.yard__polar_pod__2`: `{"blender": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}, "python": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}}`
- `terrain.yard__forest_village__2`: `{"blender": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}, "python": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}}`

## Fresh rendered subset

| Pair | Different pixels / frame | Fraction | Pass |
| --- | ---: | ---: | --- |
| arch.room_shell__polar_pod__0 | 0 / 76800 | 0.000000 | True |
| arch.room_shell__forest_village__0 | 0 / 76800 | 0.000000 | True |
| arch.tower__polar_pod__0 | 0 / 76800 | 0.000000 | True |
| arch.tower__forest_village__0 | 0 / 76800 | 0.000000 | True |
| furn.table__polar_pod__0 | 22 / 76800 | 0.000286 | True |
| furn.table__forest_village__0 | 0 / 76800 | 0.000000 | True |
| fx.particles__polar_pod__0 | 0 / 76800 | 0.000000 | True |
| fx.particles__forest_village__0 | 0 / 76800 | 0.000000 | True |
| nature.tree__polar_pod__0 | 0 / 76800 | 0.000000 | True |
| nature.tree__forest_village__0 | 0 / 76800 | 0.000000 | True |
| prop.book__polar_pod__0 | 0 / 76800 | 0.000000 | True |
| prop.book__forest_village__0 | 0 / 76800 | 0.000000 | True |

Historical sweeps, controls and reference-decoder results below are from the lane handoff, **not rerun by this matrix**. Fresh merged refpack suites and complete verifier receipts are recorded in MERGE-LOG. Other OS/GPU, arbitrary parameters, all-case visual equality and human taste remain unverified.

---

## Prior lane report (retained historical evidence)

# No-Blender parity receipt

**Default promotion: BLOCKED. `builder` remains `blender`; `python` / `auto` are explicit opt-ins.**

This report is generated from retained evidence by `tools/noblender_report.py`. Export success, source validation, exact/threshold parity and sampled render similarity are separate results. None is art approval.

## Matrix and thresholds

- 46 static generators × 2 packs × 3 samples = **276 paired cases**. Frozen characters are excluded by the existing registry.
- Sample 0: pack default, seed 0; sample 1: pack default, seed 1001; sample 2: deterministic schema/rule sampler (base 1234, index 0), seed 1002. A separate sweep covers three random parameter samples per generator/pack.
- Strict metadata/numeric parity: **249/276**. Python source + structural validation: **272/276**; Blender source + structural validation: **272/276**.
- Triangle and vertex counts, per-role triangle counts, vertex-colour histograms, node names/hierarchy/extras, asset extras, extension names and embedded PNG SHA-256: exact. Material floats are canonicalized to six decimals to compare serialized float32 representations.
- Bounds: 1e-5 metre; UV range: 1e-5; colour mean: 1/255 (one stored colour byte); normal mean: 1e-5. These limits were fixed before the first matrix, not widened to pass. Nonfinite comparisons fail.
- Source/job pins: `evidence/noblender/parity-04/sources.json`, `evidence/noblender/parity-04/jobs.json`; durable rows/report and both worker process/log receipts in the same directory.

## Per-generator table

Each pack cell is `Python valid / strict parity / cases`. Counts include failures; no resampling.

| Static kit | polar_pod | forest_village | Differing fields |
| --- | --- | --- | --- |
| arch.bridge | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.ceiling_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.column | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| arch.corridor | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.door | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.floor_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.house | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.pier | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.railing | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.roof | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.room_shell | 3 / 0 / 3 | 3 / 0 / 3 | colour_histogram, colour_mean, normal_mean, roles, triangles, vertices |
| arch.stairs | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.tower | 3 / 1 / 3 | 3 / 3 / 3 | colour_histogram, normal_mean, vertices |
| arch.wall_module | 3 / 3 / 3 | 3 / 3 / 3 | none |
| arch.window | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.bed | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.bench | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.chair | 3 / 2 / 3 | 3 / 2 / 3 | normal_mean |
| furn.console | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.container | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.hearth | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.lamp | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.pod | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| furn.rug | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.shelf | 3 / 3 / 3 | 3 / 3 / 3 | none |
| furn.table | 3 / 1 / 3 | 3 / 3 / 3 | normal_mean |
| fx.particles | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.bush | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.grass_tuft | 3 / 3 / 3 | 3 / 3 / 3 | none |
| nature.rock | 3 / 0 / 3 | 3 / 2 / 3 | normal_mean |
| nature.tree | 3 / 3 / 3 | 3 / 2 / 3 | normal_mean |
| prop.book | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.device | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.key | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.sign | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.tool | 3 / 3 / 3 | 3 / 3 / 3 | none |
| prop.vessel | 3 / 2 / 3 | 3 / 2 / 3 | normal_mean |
| sky.backdrop | 3 / 3 / 3 | 3 / 3 / 3 | none |
| soft.blanket | 3 / 3 / 3 | 3 / 3 / 3 | none |
| soft.pillow | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.patch | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.vista | 2 / 3 / 3 | 2 / 3 / 3 | none |
| terrain.water | 3 / 3 / 3 | 3 / 3 / 3 | none |
| terrain.yard | 2 / 3 / 3 | 2 / 3 / 3 | none |
| vehicle.boat | 3 / 3 / 3 | 3 / 3 / 3 | none |
| vehicle.craft | 3 / 3 / 3 | 3 / 3 / 3 | none |

## Investigated differences

- Smooth side normals originally included flat caps; fixed with a regression test. Exporter four-decimal normal normalization was verified against the installed Blender exporter. Residual normal means and the tower glow vertex split still miss the strict tolerance; not hidden by visual similarity.
- Room-shell hole tessellation differs from mathutils. Splitting the unrolled wall at plan cuts changes downstream triangle/vertex counts and bake distributions. The reference is intentionally not rewritten to use the new triangulator just to force equality.
- Numpy self-intersection initially counted boundary contact. The same Python GLBs passed Blender BVH; strict interior crossing/positive coplanar-area tests fixed that false positive while the crossing-tube control still fails correctly.
- Sampled extreme terrain.vista and terrain.yard inputs fail the existing origin/extent gate on both builders. Generator parameters/rules were not changed in this lane.
- Numpy 2.0.2 emitted matmul RuntimeWarnings on this host; logs retain them. The finite-value structural gates and parity nonfinite regression are not disabled.

Failure-field occurrences (one case may contribute several): `{"colour_histogram": 8, "colour_mean": 4, "normal_mean": 25, "roles": 4, "triangles": 8, "vertices": 6}`.

Source-validation failures in the final matrix:

- `terrain.vista__polar_pod__2`: `{"blender": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}, "python": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}}`
- `terrain.vista__forest_village__2`: `{"blender": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}, "python": {"origin_scale": "largest extent 1216.926 m outside [1, 200] for class terrain"}}`
- `terrain.yard__polar_pod__2`: `{"blender": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}, "python": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}}`
- `terrain.yard__forest_village__2`: `{"blender": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}, "python": {"origin_scale": "largest extent 62.547 m outside [1.5, 40] for class shell; footprint centre z -4.749 not at origin (tol 1.268)"}}`

## Godot render subset

**12/12 paired captures pass** the existing golden diff's threshold 0.1 and frame limit 0.02. Same cameras, 320×240, shipped GLTF resolver/N64 shader, UV scroll frozen. No goldens were blessed.
Fixed subset: room shell, tower, table, tree, book and particles in both packs. This tests static asset/material compatibility, not full-room gameplay or every parameter sample.

| Pair | Different pixels / frame | Fraction | Result |
| --- | --- | --- | --- |
| arch.room_shell__polar_pod__0 | 0 / 76800 | 0.000000 | PASS |
| arch.room_shell__forest_village__0 | 1 / 76800 | 0.000013 | PASS |
| arch.tower__polar_pod__0 | 1 / 76800 | 0.000013 | PASS |
| arch.tower__forest_village__0 | 0 / 76800 | 0.000000 | PASS |
| furn.table__polar_pod__0 | 33 / 76800 | 0.000430 | PASS |
| furn.table__forest_village__0 | 0 / 76800 | 0.000000 | PASS |
| fx.particles__polar_pod__0 | 0 / 76800 | 0.000000 | PASS |
| fx.particles__forest_village__0 | 0 / 76800 | 0.000000 | PASS |
| nature.tree__polar_pod__0 | 0 / 76800 | 0.000000 | PASS |
| nature.tree__forest_village__0 | 0 / 76800 | 0.000000 | PASS |
| prop.book__polar_pod__0 | 0 / 76800 | 0.000000 | PASS |
| prop.book__forest_village__0 | 0 / 76800 | 0.000000 | PASS |

## Sweeps and controls

- Original source control suite, now selectable with `--builder python`: **33/33 proven** in `evidence/noblender/kit-reports/controls/noblender-04.json`. Degenerate/crossing-polygon authoring is refused earlier; corresponding controls deliberately triangulate/mutate exported data to prove validator rejection as well.
- Existing structural GLB controls run against a Python-built table: **11/11 flagged**, asserted in `tests/test_noblender.py` (not just against the shipped Blender library).
- Source sweep totals: `{"error": 2, "failed": 14, "passed": 260, "rejected": 0}`; all 276 requested samples retained. Source sweep returns nonzero on any failure.
- Additional structural sweep: **272/276** valid, **2** missing due to failed generation. Full per-file issues: `evidence/noblender/sweep-structure.json`. In particular the structural UV bound can reject an output accepted by the older source-only gates.

## Reference measurement parity

- Fresh Blender PNG oracle: True; fresh Blender JPEG oracle: True. These compare all measurement fields exactly after omitting decoder/version metadata.
- Retained older smoke snapshot: **106 differing fields**, not passed. The current Python and freshly rerun Blender agree, so the retained/current discrepancy is not a decoder parity claim. Historical input/measurement-code provenance is not sufficient here to certify that snapshot unchanged.
- Float32 reciprocal multiplication is required to match Blender byte decoding; `decode-probe.json` documents division differing by one ULP and multiplication matching every channel value in both PNG probes.
- Both real Godot and labelled software draft proof completed with Blender explicitly unavailable: `evidence/noblender/proof-smoke/report.json`. Guard/determinism suite receipts are separate from this numeric comparison.

## Not verified

Default promotion; all-case visual parity; other machines/GPU/OS/Windows; other Blender or Godot versions; new character rigs/animations; all image codecs, ICC/EXIF workflows and 16-bit PNG; unsampled parameter combinations. Full-repository verification is recorded separately in `evidence/noblender/verify-all-*.log` and the linked `evidence/verify-*/` receipts.
