# Game templates and premise files: L4 P0 design

Lane L4 TEMPLATE-PREMISE, phase P0 (reading step), plan `plans/05B-NOUS-DEMO-VIA-PLUGIN.md` section 4.
Written 2026-11-10 on `template-lane` from `main` 32a8ca48. Governing rule: `PRODUCT-PRINCIPLE.md`. Nothing
in plugin core may name Teknium, a CEO, Nous or the cyber city: those are data in a premise file, a pack or an
overlay.

Marking: **[read]** = read from the file in this session; **[ran]** = real command output in this session;
**[proposal]** = design for P1-P3, not built.

---

## 1. What was read and what was run

| Source | Fact | Mark |
|---|---|---|
| `adventure_maker/newgame.py` `create` | Stages `doctor, scaffold, compile, check, build_assets, playtest, play_runtime, audit`. `check` and `build_assets` are `required=False`; the result is `new_game_ready` only when `badge['ok']`. `starter_spec` calls `templates.premise_spec` and then binds public cast from `bindings.json` by `CAST[pack]`. | read |
| `adventure_maker/templates.py` | One function, `premise_spec`. Story contract **1.1.0** (not 1.2.0), `metadata.template: two_room_collect_v1`. | read |
| `adventure_maker/playtest.py:112` | A 1.2.0 game goes to `module_playtest.physical(...)`; the `PLAYTEST` seconds/mode are **not passed** on that path. | read |
| `adventure_maker/badge.py` `compute` | `ok` requires `proof.status == 'proved'`. A conditional proof can never give `ok`. | read |
| `adventure_maker/export.py` `qualify` | 1.2.0 + `conditional` exports only with `module_preview: true` and a fresh physical bot that is `PLAYABLE`, `completed`, and tested every one of `combat/course/regions` present. | read |
| `tools/city_arena.py` | 1.2.0 spec, gameplay API 1.1.0, modules `abilities`, `challenge`, `combat`; one encounter of 3 waves, one boss encounter with `boss` + `gate`; door condition `{'challenge': 'boss_fight', 'status': 'completed'}`. Proof status `conditional`. | read + ran |
| `tools/cyberkit_rooms.py` (on `cyberkit-lane` 03be2ccb only, not on `main`) | `compile_room(plan) -> (room, presentation, report)`. Hard-codes the hero id `'pilgrim'` in `character_ids`; doors only north/south at grid position 6; 6,000-triangle estimate check. | read |
| `tools/cyberkit_demo.py` (`cyberkit-lane`) | The four room plans are **Python code** in `plans()`, not data. Doors wired as a ring (prev/next). Uses gameplay API 1.0.0 `regions`, no combat. | read |
| `tools/{medieval,dungeon,scifi,western,ancient}kit_rooms.py` | Each kit has its own `compile_room`; plans live in each `tools/*kit_demo.py`. No `rooms.json` exists anywhere in `kits/`. | read |
| `tools/package.py` `INCLUDE` | Ships `contracts/*`, `kits/*`, `packs/*`, `examples/*`; ships only a few named `tools/*.py`. **No `tools/*kit_rooms.py`, no `premises/`.** | read |
| `story/modules/schema.py`, `validation.py:177`, `registry.py` | Spawns <= 24 per encounter, wave 0-7, encounters <= 16, archetypes <= 16, `max_simultaneous` 1-3 and **each wave index may hold at most `max_simultaneous` spawns**; `challenge.max_active` is const 1; `start.modules.completed` <= 16; one `boss` id and one `gate` door per encounter. | read |

**Probe [ran]** (scratch only, not committed: `~/.hermes/cache/scratch/l4p0/probe_create.py`): `newgame.create`
with `starter_spec` replaced by `tools.city_arena.make_city()`, real Godot and Blender on this Mac, empty games folder.

```
status new_game_needs_work, ok false, 19.8 s total
stages: doctor ready | scaffold scaffolded_unvalidated | compile compiled | check conditional (0.17 s)
        build_assets passed (4.5 s, blender) | playtest PLAYABLE (2.8 s) | play_runtime prepared | audit FAIL (12.0 s)
badge:  proof conditional · 3 bots played · assets built · style audit FAIL 66/100 (1/2 rooms) · 0 softlocks · PLAYABLE (headless)
playtest report: verdict PLAYABLE, completed true, modules_tested ['combat']
audit: forecourt cuboid_placeholder (a room with no kit shell)
```

So: `check` and the physical playtest accept a module game as is. Two things stop `new_game_ready`:
(1) `badge.compute` refuses any conditional proof; (2) the style audit fails grid rooms without kit dressing.

---

## 2. Template registry [proposal]

`adventure_maker/templates.py` becomes a small registry. `premise_spec` stays byte-identical (A8).

```python
TEMPLATES = {
  'two_room_collect_v1': {'contract': '1.1.0', 'build': premise_spec, 'words': (), 'needs_rooms': False},
  'arena_run_v1':        {'contract': '1.2.0', 'build': arena_spec,   'words': ARENA_WORDS, 'needs_rooms': True,
                          'min_hits': 2},
}
DEFAULT_TEMPLATE = 'two_room_collect_v1'

def pick_template(premise, explicit=None, premise_file=None) -> (template_id, reason)
def build(template_id, premise, project, pack, rooms=None, slots=None) -> spec   # pure, deterministic
```

- `ARENA_WORDS = fight, waves, robots, boss, bosses, beat, brawl, arena, rescue, time, fastest` (plan list), counted
  like `pick_style` (plural `s` stripped). **Threshold 2 hits, and `time` never counts alone**, so an existing prompt
  such as "rescue the lost cat" keeps the starter. The demo prompt scores 6 [ran]: `fights, waves, beats, rescues,
  fastest, time`. The fox prompt scores 0.
- Precedence: premise file `template` > explicit > words > default.
- `needs_rooms`: `arena_run_v1` refuses (one plain line, nothing created) when the chosen pack has no room plans, and
  says which packs have them. It never falls back to bare grid rooms, because those fail the audit (probe above).
- `newgame.create` gains one line in the message, `Template: arena_run_v1 (auto: matched ...)`, and, with a premise
  file, `Story: <id> (premise file, matched by title)`. `project.json` gains `template` and `story` keys.
- Cast binding stays in `newgame.starter_spec` for the starter; `arena_spec` takes bound character rows from a shared
  helper so binding logic is not duplicated.

### Pack room data (the input `arena_spec` instantiates)

The kit room compilers live in `tools/` and are **not shipped**, so `create` cannot compile room plans at run time.
Room data must therefore be **pre-compiled** pack data, regenerated by a tool and pinned by a test:

`kits/packs/<pack>/rooms.json`, format `hermes64-pack-rooms/1`:

```
{format, pack, generated_by, rooms: [{
   id, name, description, roles: ['opening'|'arena'|'finale'],
   room:         compiled room row (grid_size, cameras, doors with ids 'north'/'south'),
   presentation: compiled metadata.presentation.rooms.<id> row (kit_shell, pieces, cameras, look_profile ...),
   anchors: {hero_start, checkpoint, arena:{min,max}, spawns:[[x,y,z] x>=8], boss:[[x,y,z] x>=3],
             captive?, interact?},
   slot_pieces: {<texture slot id>: [piece index ...]},
   tri_estimate }]}
```

`arena_spec` only renames ids, rewrites `character_ids` (the compilers hard-code `pilgrim`), wires doors as a forward
chain with challenge conditions, and places spawns on anchors. A test regenerates every `rooms.json` from its kit
compiler and requires equal bytes.

### What `arena_run_v1` generates on today's fields (P1)

- Rooms: `opening` (no enemies) -> N arena rooms -> `finale`, order from slots or pack default.
- Per arena room: one `combat` challenge with its own checkpoint, `retry: checkpoint`, condition = previous
  challenge completed; one encounter; forward door `conditions: [{'challenge': <this>, 'status': 'completed'}]`
  (city_arena pattern) and encounter `gate` = that door.
- Waves: a premise wave of more than 3 robots is split over consecutive wave indices of at most
  `max_simultaneous` (3). Waves 0-7, 24 spawns per encounter.
- Finale: **one** `boss_phases_v1` boss per encounter today. Three at once needs L1 (`encounter.bosses`,
  `attack_budget`). Until then P1 builds three sequential boss challenges in the finale room.
- Goal: final interaction (e.g. free the captive) gated on the finale challenge; ending on its flag.
- `abilities.config.max_health` from the run-rules slot; no clock, no death penalty (not in today's contract).
- Exports with `module_preview: true` (`export.py` `qualify`).

---

## 3. Complete slot list

Every slot has a default, so a bare prompt that picks `arena_run_v1` still makes a game. "Spec field" is where the
value lands. Phase = when the slot becomes live.

### Identity and style
| Slot | Default | Spec field | Phase |
|---|---|---|---|
| `title` | `title_for(premise)` | `title` | P1 |
| `description` | the premise | `description` | P1 |
| `template` | `pick_template` | `metadata.template` | P1 |
| `style` (pack id) | `pick_style` | `metadata.style_pack` | P1 |
| `story` id + sha256 | none | `metadata.premise: <id>@<sha>` | P2 |

### Cast
| Slot | Default | Spec field | Phase |
|---|---|---|---|
| `hero` {id, name, binding (bindings.json `character_id`)} | pack `CAST[0]`, id `hero` | `characters[]`, `metadata.protagonist` | P1 |
| `npcs[]` {id, name, binding, room, anchor, pose/clip e.g. `captive`} | pack `CAST[1]` in the finale | `characters[]`, room `character_ids`, presentation `characters` | P1 (pose P3 with L6) |
| `robots[]` {id, name, base: walker/brute/drone, overrides: max_health, damage, speed, cue} | stock `pitch_walker`-style rows from `city_arena` numbers, renamed neutrally | combat `archetypes[]` | P1 |
| `bosses[]` {id, name, patterns: charge/fan/ring -> bump/shot count 3/slam or surge, max_health} | one stock `boss_phases_v1` | combat `archetypes[]` + finale encounter | P1 (one), P3 (three at once) |
| robot liveries per archetype | stock robot art | robots.json staging (not a spec field today) | M8 / L6 |

### Rooms and flow
| Slot | Default | Spec field | Phase |
|---|---|---|---|
| `rooms.order[]` pack room ids with role | pack order: opening, arenas, finale | `rooms[]`, doors | P1 |
| `rooms.<id>.name` / `description` | pack values | room `name` / `description` | P1 |
| `arenas[]` {room, label, waves: [[{robot, count}]]} | 3 arenas, 2-3 waves of walkers/brutes/drones | challenge + encounter per arena | P1 |
| `arena.label` (wave title shown to the player) | room name | **no consumer today**; `metadata.presentation.challenges.<id>.label` for L2 | P1 data, P3 shown |
| `finale` {room, bosses[], attack_budget} | one boss | finale encounter(s) | P1, budget P3 |
| `goal` {label, text, ending text} | "Finish" / generic | final interaction, flag, ending | P1 |
| `weather.<room>` (rain) | off | presentation (L5 `weather.gd`) | P3 |

### Run rules (L1)
| Slot | Default | Spec field | Phase |
|---|---|---|---|
| `run.max_health` | 3 | today `abilities.config.max_health`; L1 `gameplay.run` | P1 / P3 |
| `run.death_penalty_ticks` | 600 | `gameplay.run` (L1) | P3 |
| `run.clock` from first control to last boss | on | `gameplay.run` (L1) | P3 |
| `moveset` | `brawler_v1` | `abilities.moveset` (L1) | P3 |

### Scenes and results (L2)
| Slot | Default | Spec field | Phase |
|---|---|---|---|
| `scenes.opening[]`, `scenes.pre_finale[]`, `scenes.ending[]`: card {room, camera, actors [{id, clip}], line {id, speaker, text}, voice line id, hold ticks} | none (no cards) | `metadata.presentation.scenes` | P3 |
| `results` {enabled, title} | enabled, game title | results card (L2) | P3 |

### Audio slots (L3 and/or AUDIOPIPE; schema owner to be decided, see section 5)
| Slot | Default | Phase |
|---|---|---|
| `audio.music.title`, `audio.music.results` | generated track | P3 |
| `audio.music.room.<room id>` (per arena, finale) | generated track | P3 |
| `audio.music.scene.<scene id>` | room music | P3 |
| `audio.voice.<line id>` | none (subtitle only) | P3 |

Files never sit in the premise file: it names slot ids only; the overlay (`overlay/overlay.json`) maps slot id ->
file + sha256.

### Texture slots (L3)
| Slot | Default | Phase |
|---|---|---|
| `textures.<slot id>` -> pack `slot_pieces` names (e.g. tower sign, sky signal, terminal screen) | neutral pack texture | P3 |
| `textures.hero_emblem` | neutral emblem | P3 |

Demo values for these slots (Teknium, the CEOs, the companies, the lines, the 12 audio names, the logo) go only in
`premises/teknium-vs-tyrants/` and the overlay.

---

## 4. Premise file [proposal, P2]

`premises/<id>/premise.json` + `premises/<id>/prompt.txt`; contract `contracts/premise/1.0.0.json`, closed objects,
ids `[a-z][a-z0-9_]*`, text lengths capped, no paths, no scripts; every slot in section 3 is a field. Fields that need a
lane not yet merged (scenes, audio, textures, run, moveset, bosses > 1) are accepted by the contract from P2 but
reported as `not yet applied: <field>` until P3 switches them on, so the file does not change between P2 and P3.
Loader in `adventure_maker/premise_packs.py`: `find(title)` (text before the first colon, case-insensitive, exact),
`load(id)`, `validate`, `apply(slots, pack_rooms) -> slots`. `newgame.parse` gains `--story <id>`; no tool schema
change (budget stays 27 tools / 5,868 tokens).

Second example (A9): `premises/keep-under-siege/` on `castle_keep`, bundled cast, stock robots renamed by data.

---

## 5. Files each later phase edits

| Phase | Edits (L4-owned) | Needs from others (request, not edited by L4) |
|---|---|---|
| **P1** | `adventure_maker/templates.py` (registry, `arena_spec`, `pick_template`); `adventure_maker/newgame.py` (`create` uses the registry, `Template:` line, card key; `starter_spec` body untouched); `adventure_maker/premise_packs.py` (new: pack rooms loader/validator); `tests/test_templates.py`, `tests/test_templates_arena.py`; this doc | **`adventure_maker/badge.py`** (owned by no lane): accept `conditional` when the playtest report is a completed physical module run that tested every combat/course/regions module present (same rule as `export.qualify`), text `proof conditional (module bot completed)`. Ask Main to assign it to L4. **`kits/packs/castle_keep/rooms.json`** + generator (`kits/` is L5's): P1 needs one on-`main` kit with room data before L5's cyber rooms land at M1. Ask Main: L4 writes `tools/pack_rooms.py` (new) + `kits/packs/castle_keep/rooms.json` (new), or L5 does. |
| **P2** | `contracts/premise/1.0.0.json` (new); `adventure_maker/premise_packs.py`; `premises/teknium-vs-tyrants/{premise.json,prompt.txt}`; `premises/keep-under-siege/{premise.json,prompt.txt}`; `newgame.py` (`parse --story`, `create(story=)`, `Story:` line); `tests/test_templates_premise.py` | **`tools/package.py`**: add `'premises/*'` to `INCLUDE` (and `tools/check_install.py` if it pins the list), else premise files do not ship. |
| **P3** (on M1-M5) | `templates.py` (switch to L1's gameplay 1.2.0 fields: `bosses`, `attack_budget`, `run`, `moveset`; L2 `presentation.scenes`; L3 slots; L5 weather); `premises/*`; `tools/make_demo.py` (new); `skills/hermes64/SKILL.md`; tests | L5 `kits/packs/neon_city_night/rooms.json` in the section 2 format (incl. `tower_roof`, `server_room`, anchors, `slot_pieces`); L1/L2/L3 field names frozen in their docs. |

---

## 6. Conflicts to expect

Base for P1-P3 is tag `rc3-base-1` (not yet created when this was written).

**MOVE** (`move-lane` 7af12ee4, 35 ahead of `main`; uncommitted: `tools/move_browser.py`, `tools/move_chrome_batch.sh`,
`tools/move_review.py`). Touches `adventure_maker/newgame.py` +6 lines (an extra `next` step when the audit FAILs
with no fix, inside `create` just before the `build_assets` step insertion) and `adventure_maker/audit.py` (2 lines),
plus runtime view files L4 never edits. Already in `rc3-base-1`, so no textual conflict for L4. Later MOVE commits
(M6) conflict only if they touch `newgame.py` again. Semantic: camera/audit changes can move style-audit results of
generated games; re-check A1 after M6.

**WINDOWS** (`windows-lane` 42cc93b6, 2 ahead; uncommitted README, tests, `tools/windows_*`). Edits `newgame.py` in
**three** places, not only `preflight`: (a) `preflight` platform check; (b) `starter_spec` `read_text(encoding='utf-8')`
on `bindings.json`; (c) `create` `command = command_line(argv)` via a new `platforms.py`. (b) and (c) sit in code L4
changes. L4 rule: leave `preflight` and those two lines byte-for-byte, add new lines elsewhere, and use
`encoding='utf-8'` in every new file read so the M9 union is mechanical. Also edits `badge.py` `_read` (1 line,
encoding), `playtest.py` (encoded writes), `export.py` (117 lines, L3's file), `module_playtest.py` (4 lines). The
L4 badge change is in `compute`, a different hunk from `_read`.

**AUDIOPIPE** (`audiopipe-lane` fb8825e2: only `docs/AUDIOPIPE-MODEL.md` committed; no working-tree changes when
read). Its brief (`LANE-AUDIOPIPE.md`) includes project-data audio slots "hookable from premise/recipe data" and
runtime music per scene with cross-fades and busses, i.e. `runtime/godot/view/audio.gd` and the audio schema. Plan
05B gives exactly that to L3 and does not mention AUDIOPIPE. For L4: the premise `audio` block (section 3) maps to
whichever slot schema lands; L4 P3 reads its field names from the owner's doc. **Main must name one owner of the
audio slot schema and of `audio.gd` before L3 starts.**

**COMBAT2** (L1): no branch or worktree exists yet. `wt-combat` / `combat-lane` da52f813 is the old, already merged
COMBAT lane (0 ahead, 108 behind `main`). No shared files with L4 (L1 owns `story/modules/*`, `contracts/gameplay/1.2.0/`,
combat runtime). Semantic dependency only: P1 targets gameplay API 1.1.0 limits above; P3 switches to L1's names.
Naming hazard: story `contract_version` 1.2.0 vs gameplay `api_version` 1.1.0 today and 1.2.0 after L1; both are
called "1.2.0" in the plan.

**L5 CYBER-ROOMS**: L5 hands its `newgame.py` style-keyword hunk to L4 as a patch file (plan). L5 must also emit
`rooms.json` in section 2's format; agree the format before L5 writes it.

---

## 7. Plan assumptions that turned out wrong or incomplete

1. **Room plans are not data.** The cyber room plans are Python in `tools/cyberkit_demo.py:plans()`, and every
   `compile_room` lives in `tools/`, which `tools/package.py` does not ship. "Room plans read from pack data" only
   works if packs carry **pre-compiled** rooms (section 2) or the compiler moves into `adventure_maker/`.
2. **`compile_room` is not template-ready.** It hard-codes the hero id `pilgrim`, north/south doors at position 6, and
   the demo wires doors as a ring, not a forward chain.
3. **`new` cannot return `new_game_ready` for a module game today** [ran]: `badge.compute` requires `proved`; combat
   games prove `conditional`. Needs a `badge.py` change, a file no lane owns.
4. **Bare grid rooms fail the style audit** [ran: `cuboid_placeholder`]. `arena_run_v1` needs kit rooms, and on
   `rc3-base-1` no pack has room data yet (cyber arrives at M1), so P1 needs `castle_keep` room data first.
5. **Wave sizes:** each wave index holds at most `max_simultaneous` (<= 3) spawns. Plan rows "2 walkers + 2 drones"
   and "2 brutes + 2 walkers" must be split over two wave indices.
6. **The 10-second `PLAYTEST`** does not apply to 1.2.0 games (the physical bot ignores it). The probe's bot finished
   a two-room combat game in 2.8 s.
7. **WINDOWS edits more of `newgame.py`** than `preflight` (section 6).
8. **AUDIOPIPE overlaps L3**, and 05B never mentions it.
9. **`premises/` would not ship**: `tools/package.py` has no `premises/*` rule.
10. **The starter is story 1.1.0**, not 1.2.0. The registry has to carry a contract version per template.

## 8. Not verified in P0

- The style audit on kit-dressed rooms of any pack inside `create`; whether `arena_spec` rooms pass the audit.
- Three `boss_phases_v1` spawns in one encounter (L1 P0 spike).
- Export of a `create`-made module game (`module_preview`), any target.
- The cyber rooms on `cyberkit-lane` through `create` (not on `main`; not run).
- That `kits/packs/<pack>/pack.json` is the right home for `rooms.json` versus `packs/<pack>/`.
- AUDIOPIPE's actual slot schema (nothing written yet when read).
- Behaviour on Windows; the probe ran on this Mac only.
