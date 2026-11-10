# NOBLENDER integration handoff to Hermes Main

Owner: Hermes Main. Local lane: `noblender-lane`, base `80d5236`. No push, profile install, default promotion, character rewrite or art approval is authorized by this handoff.

## Merge surfaces (line numbers in this lane)

| File / anchor | Integration change |
| --- | --- |
| `kits/core/pipeline.py:59` (`build_one`) | New trailing `builder` argument, preserving existing `keep_failed`; `:84` resolves auto from `asset.character`; `:87` dispatches static Python; Blender import stays lazy. Existing validation and cleanup preserved. Default textures now live beside the chosen output, avoiding installed-bundle writes. |
| `kits/build.py:29`, `:46`, `:63` | `--builder`, both batch/single dispatches, ordinary Python argv support; early actionable missing-numpy error. |
| `adventure_maker/builders.py:8` | Backend policy, shared command construction and versioned cache identity. Keep `DEFAULT_BUILDER='blender'` until the full gate passes. |
| `adventure_maker/assets_v3.py:4`, `:27`, `:42`, `:89`, `:119` | Import helpers; choose actual executable; both direct and batched room-kit command paths; both cache keys include selected backend. Preserve shell optionality and existing Runner containment. |
| `adventure_maker/runner.py:18` (`locate`) | Missing executable errors name `<tool>_path`; preserve Python venv symlink entrypoint rather than launching its base binary. No sandbox policy weakening. |
| `adventure_maker/tools.py:5` | `builder` added to the existing settings allowlist, not a new registered tool. |
| `plugin.yaml:16–18` | `builder` setting and dependency explanations for `python_path`/`blender_path`; declared tools remain unchanged. |
| `adventure_maker/doctor.py:56` | Read-only `check(components)` entrypoint uses the actual child through Runner; no tool registration yet. |
| `kits/core/meshkit.py` (`tessellate`) | Portable triangulation outside bpy even when standalone mathutils happens to be importable. Blender oracle keeps original tessellator. |
| `kits/validate/checks.py` | Respect explicit sRGB8 marker; fallback topology implementation in `intersections.py`. Do not remove known-bad controls. |
| `kits/core/png.py` | Bound inflate by validated dimensions, reject missing dimensions/trailing inflate/mismatched length, apply grayscale/RGB tRNS. |
| `kits/tools/controls.py`, `sweep.py` | Backend selection, local report-root option, pure-Python controls, preservation of failing output when requested. |
| `adventure_maker/static_preview.py`, `runtime/godot/noblender_capture.gd` | Separate static proof helper using shipped resolver/shader/capture mechanics, frozen UV animation time and explicit software fidelity label. |

New core files: `glbwrite.py`, `pybuild.py`, `triangulate.py`, `intersections.py`. New developer tools: `tools/parity_noblender.py`, `parity_noblender_refs.py`, `noblender_report.py`; `tools/__init__.py` makes repository tooling an explicit package instead of colliding with `kits/tools`.

### Reference-pack merge

The baseline has no `refpack` package. The neighboring `../lane-refpack` was a read-only directory snapshot, not a Git repository; its baseline modules, guards, schema and tests are copied here. Tests live in **`tests_refpack/`**, not over this repository's `tests/`. Reconcile newer lane-refpack work first. Portable changes are:

- new `refpack/decode.py`, `measure.py`, `proof.py`, `worker.py`;
- `refpack/tool.py`: use Python workers for both stages; old `blender` argument is compatibility-only and ignored;
- `refpack/blender_proof.py`: parameterize pure assembly helper, add proof renderer disclosure; retain Blender-only helpers as the reference backend, never call them in the new workflow;
- `tests_refpack/helpers.py` and `test_tool_e2e.py`: local fixture root, no Blender skip, hanging-Python timeout fixture;
- `tests/test_noblender_refs.py`: decode bounds, colour precision, worker/no-Blender regressions.

Do not overwrite a newer refpack guard/schema revision with the copied baseline. A read-only `git diff --no-index -- ../lane-refpack/refpack refpack` shows this lane's portable delta against the still-existing neighbor; that command returns 1 for differences.

### Doctor registration proposed for Main (not registered here)

Suggested name: `hermes64_doctor`. Description:

> Report the actual selected Python version and numpy/Pillow availability, discover existing Godot/Blender executables, and explain which features work. Read-only capability discovery: no installs, engine launch, network or settings changes. Missing dependencies name python_path, godot_path or blender_path. Detection is not verification of runtime compatibility or installed export templates.

Use the existing closed schema with a required `project` and `additionalProperties: false`. In the ordinary locked Service/Components path call `doctor.check(components)` and return that structured report plus a plain-words feature table. No script/path/command field should be accepted from tool arguments. Reconcile `plugin.yaml` declarations, `register` dispatch, tests for exact registered tool count and catalog disclosure together; this lane intentionally does not add an undeclared 14th tool. A CLI equivalent is already available with `python -B -m adventure_maker.doctor --table`.

Refpack orchestration is likewise **not newly exposed as a Hermes tool**. If Main registers it, run its trusted worker through the existing Runner project sandbox, not a direct `subprocess.run` in Hermes. Preserve guarded data paths, timeouts, report-size limits and `draft_unapproved`; do not accept executable overrides from tool arguments. Existing Python workers and their Godot child then inherit the containment policy. Standalone developer CLI use does not promise the plugin sandbox.

## Re-run after visual generator/texture/shader changes

Never reuse the old parity receipt as proof for new generators. The harness snapshots current generator/pack/validator source hashes and requested jobs before running both builders. Keep the original Blender tessellator and inspect failures rather than editing the oracle to match Python. Use **fresh output directories/tags**; old reports and failed artifacts are retained.

```sh
# Run with an existing Python that contains numpy (JPEG oracle also needs Pillow).
export TMPDIR="$PWD/evidence/noblender/tmp"
python3 -B -m unittest discover -s tests -v
python3 -B -m unittest discover -s tests_refpack -v
python3 -B -m tools.parity_noblender --out evidence/noblender/parity-after-visual --samples 3 --render
python3 -B kits/tools/controls.py --builder python --tag after-visual --report-root evidence/noblender/kit-reports
python3 -B kits/tools/sweep.py --builder python --gens all --packs polar_pod,forest_village --n 3 --tag after-visual --keep-glb --report-root evidence/noblender/kit-reports
python3 -B -m tools.parity_noblender_refs --job ../lane-refpack/probes/out/smoke_job.json --expected ../lane-refpack/probes/out/smoke_measurements.json --out evidence/noblender/ref-after-visual
python3 -B -m tools.noblender_report --matrix evidence/noblender/parity-after-visual --sweep evidence/noblender/kit-reports/sweep/after-visual --refs evidence/noblender/ref-after-visual
sh tools/verify_all.sh
```

These are **independent invocations**, not a chain with `&&`: currently the strict matrix, source sweep and retained reference comparison correctly return nonzero. Read all three result categories. The reference harness requires `--job` and `--expected` plus the images referenced by that job. Preserve the neighboring smoke evidence, or supply a separately recorded reference corpus and identify it accurately; do not substitute a synthetic image and call it retained-snapshot parity. JPEG comparison additionally needs Pillow and an existing Blender oracle.

Before a later default flip, all required matrix cases, structural/source budgets, controls and sampled image gates must be green or a narrower explicit product scope must be approved. Change **all four defaults** consistently: `builders.DEFAULT_BUILDER`, `pipeline.build_one`, `kits/build.py` argparse, `plugin.yaml`. `auto` is already an explicit opt-in; never silently fall back to Blender under `builder=python`.

## Existing receipts and handoff boundaries

- `evidence/noblender/summary.json`, `docs/NOBLENDER-PARITY.md`: exact matrix/sweep/render/reference totals.
- `evidence/noblender/plugin-python/report.json`, `doctor.json`: real Service/Runner scaffold/compile/build, missing Blender, existing numpy/Pillow venv; first build generates assets, second reuses Python cache.
- `evidence/noblender/proof-smoke/report.json`: both Godot and absent-Godot draft proofs, missing Blender.
- `evidence/noblender/fast-final.log`, `refpack-final.log`, `unit-final-03.log`, `controls-04.log`; `verify-all-*.log` points to full repository receipts.
- `NOBLENDER-BLOCKED.md`: unpassed promotion/retained-evidence gates. No test threshold or golden was loosened/blessed to make the lane appear complete.

Generated GLB/runtime caches are local evidence, not shipped libraries. Only selected text/source/report/image receipts are committed; full raw intermediate output stays in the owned worktree and the harness reproduces it. Do not include `.godot`, Python caches, copies of the entire runtime, failed-ref fixtures or all duplicate GLBs in a release. The copied reference notes/images remain provenance-bound study inputs, not new distributable assets.
