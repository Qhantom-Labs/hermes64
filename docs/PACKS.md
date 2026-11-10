# Data-only pack contract (Hermes64 facade v0.1)

This is the plugin descriptor schema. Source of truth: `adventure_maker/packs.py:PACK` and `validate_pack`. Pack layout: `packs/<id>/pack.json`. Assembled examples: `polar_pod`, `forest_village`, plus explicit `n64_v0` compatibility mapping for Last Light. The two showcased themes render through one unchanged runtime template: palette/fog, bindings, presets and sound selections differ as data, not a second game-specific engine. Their actual captures are in RESULT.md. This does not prove automatic rebaking or arbitrary new-pack fidelity.

Required keys only:
- `format:1`, `id` lowercase slug, `name`, `description`.
- `palette`: 2–32 unique uppercase `#RRGGBB` colours.
- `materials`: unique IDs, supported `kind` (`baked_unlit`, `chrome_env`, `glass_env`, `emissive`, `card_alpha`), `colour` in palette.
- `lighting`: `fog_enabled:true`, palette `fog_colour`/`ambient_colour`, nonnegative `fog_start`, larger `fog_end` (maximum 1000).
- `presets`: 1–32 unique IDs, kit `asset_id`, bounded `params_json` object with scalar values. Per-kit parameter types/bounds come from KITS manifest when building.
- `sound_palette`: relative `ambient` and `interact` paths. Traversal/absolute paths/URLs reject. Validation does **not** claim those audio files exist.
- `thresholds`: positive bounded `character_tris` ≤700, `kit_tris` ≤1500 (room-shell exception ceiling), `prop_tris` ≤150, `room_tris` ≤6000, `texture_px` ≤128. Actual pack defaults can be tighter; validator checks data, not generated geometry.
- `kit_pack_id`: exact KITS manifest pack identity. A mismatch fails rather than using another theme's assets.

No script, executable, shell, URL loader, arbitrary extension field or new engine code is accepted. Additional fields require an explicit schema revision and tests, not loose passthrough. Material/light values must be from the palette; invalid fog order, duplicate IDs/colours, malformed JSON and nonfinite numbers reject.

Scaffold copies one reviewed bundled descriptor into the project and binds its canonical SHA-256 under `metadata.hermes64_pack`. `pack_create` writes a new descriptor only inside that project. `pack_select` copies a bundled descriptor if necessary, then either updates uncompiled source or creates a compiled+checked candidate. It never silently overwrites an existing ID. Pack descriptors are immutable snapshots; use a new ID for changes. Compiled output must still be regenerated through the compiler.

Core rendering rules, generators, humanoid/animal rigs, validators, audio generators and story semantics belong outside `packs/`. Palettes, materials, lighting, parameter presets, authored theme pieces, sound choices and theme thresholds belong inside. Current assembled descriptors resolve real kit/WAV paths and provide rendered local evidence, while `pack_validate` alone is still only data validation. Character rig and animation acceptance is not supplied by a valid pack.
