---
name: hermes64-generators
description: "Use when a game needs a new prop. Author bounded recipes."
version: 1.0.0
license: MIT
---

# Make a new environment piece (data, not code)

Use the existing terminal/file surface, not a new Hermes tool. Work in the plugin root with the configured Python 3.9+ interpreter that already has numpy. No installs, network/model endpoints or source modules are needed. `python` below means that interpreter. Builds use the existing Runner sandbox (currently macOS only; no sandbox means refusal, not an unsandboxed fallback).

1. Read the project's `brief.json`, taxonomy gap report, and `kits/core/style_bible.json`. A partial match is not the requested item: name a stand-in or generate a piece. Character bodies, audio and world layout belong to their own tools. Never claim this path generates those.
2. Choose a generic lowercase id, e.g. `potion_bottle`. Never copy franchise/real-person names into ids. Put detected names in the brief's `ip_terms` and pass them as `forbidden_terms` to `author`/the loop. The built-in common-name guard is not an exhaustive detector.
3. Choose the truthful class: prop (150 tris, .03–1.6 m), furniture (300, .15–4.5 m), structure (500, .5–40 m), terrain (512, 1–200 m). Read the bible for other classes. Do not relabel a prop as a building to evade a budget.
4. Decompose the silhouette into meshkit primitives: **box, prism, lathe, loft, tube, blob, torus, card, grid_surface** only. Metres, +Z up, front -Y; floor centre is finalized automatically. Recipe socket inputs use that mesh space; output `type:anchor` socket metadata uses native glTF +Y-up `(x,z,-y)` coordinates after centring and is retained in runtime bindings. Closed pieces become `kit_` nodes; cards `kit_card_`; grids `kit_shell_` (open surfaces, not watertight solids).
5. Write JSON matching `contracts/recipe/1.0.0.json`. `format`, `id`, `class`, `licence`, `operations` are required. No code, RGB colours, paths, textures, expressions, timestamps or unseeded random sources. `role` is both a semantic palette reference and a pack texture-role reference (`wood`, `paper`, `glass`, `stone`, etc.), never an image filename. The selected mood provides every colour/material.
6. Keep parameters bounded. Numeric references are `{"param":"height","mul":0.5,"add":0.02}`. This is affine data, not an expression language. Role references are `{"param":"surface"}` with an enum of allowed roles. Rotation is degrees, XYZ; scale then rotate then translate. Repeat is a fixed integer 1–32, optional translation `step` and per-instance `rotate`. No nested repeats/loops. Mirror adds one reflected copy about the named world-origin axis after the primitive transform. No more than 128 operations, 256 expanded instances, 8,192 vertices; class triangle budgets are tighter. Coordinates/reference results are finite and in [-100,100].
7. Account for triangles before building: box 12; a torus is `2*segs*sides`; lathe non-pole bands `2*segs` plus caps; every repeat/mirror multiplies the mesh cost. Use 5–8 sides for small round props. Do not add dense geometry for painted details.
8. Save to an authoring JSON file, then use:
   ```sh
   python -B -m adventure_maker.gen_tools author --project PROJECT --recipe FILE.json --model SESSION_MODEL --brief-line "potion bottle"
   python -B -m adventure_maker.gen_tools screen --project PROJECT --id gen:potion_bottle --pack castle_keep_purple_dusk
   python -B -m adventure_maker.gen_tools build --project PROJECT --id gen:potion_bottle --pack castle_keep_purple_dusk --seed 7
   python -B -m adventure_maker.gen_tools list --project PROJECT
   ```
   `author` refuses existing recipes unless `--replace` is explicit. Project data lives in `PROJECT/recipes/`. Project mood pack: `PROJECT/kits/packs/ID/pack.json`; otherwise a shipped pack is used. Every call is logged to `.maker/generators/calls.jsonl`. A build runs twice inside the existing sandbox, compares hashes, applies file/bible/texture gates, promotes only passing GLBs under `assets/generated/`, and retains failed diagnostic receipts in `.maker/local/gen/`.
9. Start from the **six actual JSON recipes** in this skill's `recipes/` directory and the construction notes in `docs/kits/FEWSHOT.md`. Copy the relevant archetype, rename it, alter its bounded dimensions/roles, and screen it. A potion bottle uses a five-ring lathe, a five-sided cork and a paper label. A staff is a five-sided tube with a faceted crown. A book is boxes; no imported mesh is required. These are examples, never a whitelist of available nouns.
10. For a new noun such as floating island or portal, compose a fresh recipe from these primitives; hand the recipe to `asset_loop.run` as a candidate or an author callback. The loop is **not** a language model and calls no network service: the agent authors the data. Audit the callback's model, brief line and recipe hash. Retry only bounded parameters; never change the bible, pack or gate thresholds. A no-candidate need is failed, never silently assigned to a familiar kit noun.
11. Place the `gen:<id>` reference in a project's pack preset (or explicit generated placement adapter), build and capture the real room. Numeric gates are not appearance approval. State what is shown, measurements, substitutions and mechanical defects. Appearance is for Dylan to judge. Keep an honest NOT-verified list, including unswept parameter combinations and Windows runtime when not run.
12. Use `asset_report` and `provenance` to bind every shipped generated/imported file to a hash, source, licence, seed and gates. Licence declarations are recorded, not independently verified. Unknown or missing required licences must fail export; never invent a licence.

## Measured workflow cautions

- In-memory `screen` checks geometry/bible rules; the sandboxed build checks the painted textures and real GLB. A passing palette pack can still have a failing **asset texture subset** (the existing continuity gate uses an upper median). Keep that refusal. Select another explicitly declared role in the same mood; do not raise a threshold.
- Record selected-parameter acceptance separately from full-range file sweeps. The recipe resolver and retry loop check the selected configuration. A role choice that fails remains a rejected range member even when another choice passes.
- Keep Godot STORY camera rows limited to id/position/look_at; put `fov` only in presentation camera data. A capture harness that fails compilation has produced no frame.
- Use an interpreter whose numpy is available under `-I`. A user-site numpy visible in a shell can disappear in the isolated sandbox child. Prefer the already-configured interpreter; do not install or fall back unsandboxed.
- Owner integration hunks live under `docs/agen-hunks/`: pack `gen:` ids, export provenance, skill registration and package-rule documentation. They are not silently applied by this lane. Normal runtime binding snapshots record every environment GLB when a project provenance manifest exists; legacy non-recipe projects without one remain unchanged.

Python generators enter the shipped library only by reviewed pull request. The hub carries data only; this lane does not change hub admission policy or auto-publish anything.
