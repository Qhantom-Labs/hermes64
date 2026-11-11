# TIERS baseline: the 27 tools, tagged

Source: the packaged plugin (rev 313a383d + stack A owner hunks, `tools/tiers_proof.py prepare`): 27 tools, 5868 tokens by the plugin's own measure (`tools/schema_budget.py`: json of name + register kwargs, chars/4), budget 6000. The figure 5,952 in the lane brief was not reproduced on this package. Raw numbers: `docs/tiers/baseline.json` (`python3 -B -m tools.tiers_measure --host --work DIR`).

**CORE** = what a game-making agent needs: set up, make (plan then build), check (proof, bots, audit), edit, play, export, find. **ADVANCED** = everything else, used only when the user asks for that thing.

| tool | tier | intent | tokens (plugin measure) | purpose |
|---|---|---|---:|---|
| `hermes64_playtest` | CORE | check | 215 | bots play the build: SOLID / PLAYABLE / ROUGH / BROKEN |
| `hermes64_check` | CORE | check | 199 | story proof (endings, softlocks, collectibles); action=audit scores the style |
| `hermes64_edit` | CORE | edit | 242 | one story edit, recompiled and re-proved; only a passing edit is kept |
| `hermes64_export` | CORE | export | 186 | local web / macOS / Windows builds |
| `hermes64_packs` | CORE | find | 136 | list or inspect the styles (theme packs) |
| `hermes64_demo` | CORE | make | 258 | one-sentence premise -> playable starter game with a proof badge |
| `hermes64_scaffold` | CORE | make | 190 | start a project from a story spec (the data contract) on a pack |
| `hermes64_compile` | CORE | make | 152 | deterministic compile of the story spec into a build |
| `hermes64_build_assets` | CORE | make | 149 | build the room models for the chosen style |
| `hermes64_open` | CORE | play | 168 | open the game in a short preview window; screenshots=true captures rooms |
| `hermes64_doctor` | CORE | setup | 132 | check Python/numpy, Godot and Blender; read-only |
| `hermes64_audio` | ADVANCED | audio | 467 | music, sounds and voices |
| `hermes64_cover` | ADVANCED | box art | 428 | box-art covers |
| `hermes64_character` | ADVANCED | characters | 393 | new house-style characters |
| `hermes64_module_edit` | ADVANCED | enemies, abilities, puzzles | 283 | typed module edit |
| `hermes64_module_benchmark` | ADVANCED | enemies, abilities, puzzles | 266 | measure module edits |
| `hermes64_module_add` | ADVANCED | enemies, abilities, puzzles | 246 | add an enemy, ability or puzzle switch |
| `hermes64_module_check` | ADVANCED | enemies, abilities, puzzles | 201 | check (and adopt) a module source |
| `hermes64_modules` | ADVANCED | enemies, abilities, puzzles | 130 | list gameplay module contracts |
| `hermes64_benchmark` | ADVANCED | proof details | 200 | measure a series of story edits |
| `hermes64_replay` | ADVANCED | proof details | 121 | replay proof witnesses in Godot |
| `hermes64_hub` | ADVANCED | sharing | 328 | search, install, pack and publish Hub entries (local) |
| `hermes64_pack_from_refs` | ADVANCED | styles and moods | 228 | draft a pack from reference images |
| `hermes64_pack_validate` | ADVANCED | styles and moods | 142 | validate pack data |
| `hermes64_pack_select` | ADVANCED | styles and moods | 142 | switch a game to another pack |
| `hermes64_pack_create` | ADVANCED | styles and moods | 134 | new data-only theme pack |
| `hermes64_kits` | ADVANCED | styles and moods | 132 | inspect kit pieces of a style |

## Default-schema size

| measure | all 27 tools | CORE only (11 tools) | ADVANCED (16 tools) |
|---|---:|---:|---:|
| plugin measure (tokens) | 5868 | 2026 | 3841 |
| host estimate, tools eager (compact OpenAI JSON / 4) | 4283 | 1409 | 2874 |
| host 0.22.7 default (all deferred): listing added to the bridge | +641 | +265 | +376 |
| host 0.18.2 default (auto, 10% of context; Hermes64 alone never trips it) | 4283 | 1409 | 2874 |

The plugin measure is larger than the host estimate because it counts the description twice (schema and kwarg) and uses spaced JSON. On 0.22.7 the bridge itself (535 tokens) is present in a default session without Hermes64; Hermes64 adds only listing lines. Exposing only CORE would cut the eager schema on 0.18.2 from 4283 to 1409 host tokens (67% less), but no host version offers a way to defer the rest (docs/TIERS-HOST.md).
