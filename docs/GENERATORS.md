# Generator and asset-loop surface

No new Hermes tool schema is added. Use the shipped `hermes64-generators` skill and `python -B -m adventure_maker.gen_tools --help`. The skill's entrypoint registration is an owner hunk below; the CLI works without it. The configured Python must already carry numpy; nothing is installed. Builds use the existing Runner sandbox and fail closed when it is unavailable (currently Windows/Linux).

## Data contract

Recipes live only under `PROJECT/recipes/<generic_id>.json`, resolve as `gen:<generic_id>`, and never enter the global Python registry. Their vocabulary is the nine meshkit primitives, finite affine numeric parameter references, transforms, fixed repeats, mirrors, cardinal sockets and palette/texture roles. No Python, expressions, arbitrary colours, file references, imports, callbacks or network sources can appear in JSON. See `contracts/recipe/1.0.0.json` and `docs/kits/FEWSHOT.md`.

`author` stores data and author metadata; `screen` sweeps each parameter independently over minimum/default/maximum (each enum choice for roles); `build` screens, runs the real native pipeline twice inside the sandbox, compares GLB hashes, applies native file checks, bible and texture fidelity, and promotes only passing GLBs. The GLB embeds its textures. Generated models use the same +Z meshkit space, converted to +Y glTF by the existing exporter. Floor-centering also translates socket positions; published socket metadata uses the native `type: anchor`, glTF +Y-up `(x,z,-y)` coordinates, and is carried through runtime bindings.

The screen uses the existing `tools.style_bible.check_asset` consumer, not a copied threshold table. `tools/package.py` now explicitly ships that consumer; the new skill and recipes already match its `skills/*` rule. No style bible/gate threshold is changed.

## Loop and report

```sh
python -B -m adventure_maker.asset_loop --project PROJECT --brief brief.json --gaps gaps.json --pack castle_keep_purple_dusk --candidates candidates.json --tries 4 --seed 7
```

Candidate mapping keys are exact brief lines; values are recipe JSON, an existing project `gen:` id, or `{"recipe":{...},"model":"actual-session-model"}`. Missing candidates are looked up in project recipes and the six examples. A programmatic `author(want, brief)` callback may supply new **data**. The loop contains no language model client and makes no hidden network/model call. Every author request/response, build, attempt, adjustment, keep and drop is in `.maker/generators/calls.jsonl`. Interrupted work survives in `progress.json`.

At most four selected-parameter attempts are allowed. Automatic changes reduce declared segment controls, adjust declared size/taper controls toward class extents, or select another declared palette-role enum member in the same mood. They never alter parameter bounds, the pack, thresholds or bible. A schema refusal, topology defect, deterministic-hash failure or unadjustable candidate is dropped with its reason. Selected-parameter loop acceptance is **not** a claim that the whole parameter range passes; full independent range sweeps are recorded separately for the examples. No model rewrite call is invented.

`ASSET-REPORT.{json,txt}` distinguishes existed, remapped, generated, converted, substituted, failed and not covered. Failures and uncovered work come first. Unknown nouns remain failed, not silently replaced. Existing taxonomy matches are rebuilt through native generators; partial matches are never silently counted as complete. `asset_report.verify` checks files, hashes, totals and explicit placements. This lane does not automatically infer placements from an arbitrary room file.

## Provenance and export seam

`assets/PROVENANCE.json` records each built GLB's source, licence, seed, parameters, pack hash, recipe hash or native id, model attribution and gate results. Direct CLI builds and loop builds both record it. A normal runtime binding snapshot also calls `capture_bindings` when the project manifest exists, covering every bound environment GLB (not just recipes). Bundled kit rows use `bundle/<relative path>` with a trusted bundle root; missing source binding seeds are explicitly null, never guessed. `asset_report.with_bindings` attaches this file inventory and actual placement aliases without inflating the one-row-per-need counts. Cast/audio retain their existing manifests; this lane does not claim to join or re-license them. A converted record must include a source basename/hash/licence and a declared right to use it. **Licence declarations are recorded, not independently verified.** Missing/unknown required licences fail `provenance.require_export`; non-commercial/private licences are blocked from hub redistribution. Attribution licences need credit; `prepare_export` emits CREDITS.txt and a manifest remapped to actual export paths.

The existing `tools/provenance_audit.py` audits plugin-assembly source receipts, not project assets. It was read, is not a substitute for the new project manifest, and is left unchanged.

Protected seams are exact patches, not silent edits:

- `docs/agen-hunks/packs-gen-id.patch` lets a **project pack preset's asset_id** name a `gen:` recipe. Story art references stay plain `preset/<id>` aliases; no story/path validation is relaxed.
- `docs/agen-hunks/export-provenance.patch` applies the manifest/required-licence guard to the environment binding closure (project and bundled kit assets) and emits remapped credits/provenance.
- `docs/agen-hunks/register-generator-skill.patch` registers the new skill in the plugin entrypoint, adding no tool.
- `docs/agen-hunks/package-consumer-doc.patch` documents the shipped `tools/style_bible.py` rule. The worktree's package documentation test intentionally remains pending this owner-doc hunk; the integration-copy test includes it.

These patches are not applied to the lane's owner files. Their runtime integration must not be claimed until the integrator applies/tests them. `assets_v3.resolve_project_recipe` and the build-request branch are implemented here, with project pack-file lookup. A project-only mood also needs its rebuilt binding/view/env assets; the mood install helper demonstrates those in a disposable bundle. This lane does not silently bind base-coloured library meshes into a derived mood.

Python generators only join the library through reviewed source changes. This lane does not change the hub archive media/admission rules, ship Python from the hub, publish data, or add a new tool.
