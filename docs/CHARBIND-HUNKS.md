# CHARBIND: every hunk on a file that already existed

The base is `fabc04f8`, the last of the four lane merges: chars6 `c4551b33`, robots `8afc9d4d`, cast1 `bea1b945`,
cast2 `d9a78f1b`. All four were normal `--no-ff` merges with no textual conflicts. Ranges are `-old +new` lines from
`git diff -U0 fabc04f8`.

New files (no overlap possible):
- `adventure_maker/cast_binding.py`, `adventure_maker/rigkit/conform.py`, `adventure_maker/rigkit/declare.py`
- `tests/test_charbind.py`, `tests/test_charbind_validator.py`
- `docs/demobuild/charbind_{prep,proof,bots}.py`
- `docs/CHARBIND-{MODEL,HUNKS,RESULT}.md`

| File | Hunk | What |
|---|---|---|
| `adventure_maker/adapters.py` | -167,0 +168,2 | `prepare_runtime`: after `stage_runtime`, call `cast_binding.stage(destination, project, root)` |
| `adventure_maker/character_tools.py` | -442,0 +443,3 | bind of a file: validate every clip the file carries, plus idle (was: the rig's required set) |
| | -448 +451,2 | a refused bind adds `reason` (one plain line, `cast_binding.plain_reason`) |
| | -470,0 +475,6 | bind reports `used_by`: ids of the current game that use the cast row |
| | -472 +482,4 | the bind result gains `used_by` and `next` |
| `adventure_maker/newgame.py` | -194,0 +195,3 | arena: a non-bundled `binding` is recorded as a project cast id |
| | -197 +200, -204 +207 | the old `hero.binding` / `npcs.binding (bundled fallback)` pending notes are replaced by the record above |
| | -206,0 +210,7 | `bosses[]` / `robots[]` `binding` go to `metadata.presentation.cast`; one pending note names the ids |
| `adventure_maker/premise_packs.py` | -55,3 +55,3 | premise schema: optional `binding` on `robots[]` and `bosses[]` |
| `contracts/premise/1.0.0.json` | -222,0 +223,6; -523,0 +530,6 | regenerated with `python3 -B -m tools.premise_contract` (the two `binding` fields) |
| `adventure_maker/templates.py` | -176,2 +176,2 | `npcs[].clip` is written to the room placement (`clip`), replacing the `npcs.clip (idle fallback)` pending note |
| `adventure_maker/rigkit/validate.py` | -21,0 +22,30 | declared forms: constants and `declarations(doc)` for the run flight keys of the locomotion block, and seats |
| | -177 +207,2 | `_clips` takes the declarations |
| | -226 +257,7 | root motion: a declared seat keeps one placement (within 0.5 m of rest); undeclared clips unchanged |
| | -270 +307,3 | `_posed_checks` takes the declarations |
| | -321,0 +361,4 | floor: a declared seat never goes below the floor; declared run flight keys may be above it up to 0.15 x H; everything else unchanged |
| | -341,0 +385,3 | report: `declared_flight`, `declared_seats`, `flight_max_m` (only when declared) |
| | -380 +426,2; -385 +432 | `validate_character` computes the declarations once and passes them in |
| `runtime/godot/actors/assets.gd` | -18 +18,3 | `character()`: a row with `for_ids` matches by game id, ahead of the selector rows |
| | -41,0 +44,5 | `cast_character(id)`: a scene actor that is not a story character resolves to its cast row |
| `runtime/godot/actors/bridge.gd` | -22,0 +23,4; -25 +29 | room actors play their authored `clip` (for example a seated captive) after placement and after dialogue; idle otherwise |
| `runtime/godot/view/scene_cards.gd` | -541,0 +542 | a card actor that is not a story character falls back to `resolver.cast_character` |
| `story/presentation/scenes.py` | -248,0 +249,17 | `actor_ids(doc)`: combat archetype ids and `presentation.cast` keys |
| | -262 +279; -276 +293 | scene card actors may also use those ids; unknown ids are still refused (`missing character`) |
| `docs/demobuild/build.py` | -109,0 +110,17 | stage `cast`: copy and bind each `data/characters.json` GLB through `hermes64_character bind` |
| `tests/test_rigkit.py` | -65,2 +65,2; -70 +70; -82 +82 | merge fix: chars6 added rig `human16_v3` (16 bones, version 3.0.0, combat pack); the rig list, version and pack tests now include it |
| `tests/test_templates_arena.py` | -69 +69,2 | the npc clip is now applied: asserts `clip == 'captive'` instead of the pending note |
| `docs/CHARACTERS.md` | -35,0 +36,31 | section "A bound character in the game (CHARBIND)" |
| `skills/hermes64-characters/SKILL.md` | -36,0 +37,4 | bind → game id mapping, `used_by`, one-line `reason` |

Not touched:
- `adventure_maker/character_schemas.py` and every tool schema (27 tools, no new action or argument)
- `character_gate.py`, `seams.py`
- `characters/`, `rigs/`, `kits/`, `bindings.json`
- other lanes' worktrees
