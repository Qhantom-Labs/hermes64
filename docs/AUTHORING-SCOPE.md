# Hermes64 authoring scope

This is a bounded 3D adventure authoring toolkit, **not an arbitrary game engine from any prompt**. Themes and narratives are general; verbs and runtime mechanics are finite. An agent must say when a prompt requires unsupported mechanics, not deliver the same starter under a new title.

## Available on this base

- Room-to-room exploration; reciprocal doors with finite key/flag/role/dialogue conditions; explicit actions, conversations, quests and terminal endings.
- Inventory items (finite identity membership, no quantities), optional monotone collectibles and identity-based groups through full STORY 1.1 data.
- Branching objectives and endings as separate actions/guards. Conditions are AND lists; no general Boolean expressions. Effects are a closed whitelist.
- Non-combat NPC guardians and clue/key/puzzle **gates** authored as finite story logic. These are not autonomous AI NPCs or combat bosses.
- STORY 1.2 bounded combat arenas/waves/robot and boss templates **through the existing module contract**, not through new per-game scripts. Combat code is owned by the combat lane and unchanged here. No combat playability/balance acceptance is supplied by AUTHOR's three games.
- STORY 1.2 ordered timed **on-foot** courses with countdown, deadline and checkpoint retry. Conditional logical proof plus real-input bot evidence, not a human difficulty guarantee.
- STORY 1.3 grid puzzles (switches, keys/locks, blocks, braziers, pressure plates, timed gates) via their documented **separate module data-pointer and puzzle runtime workflow**. They do not go through legacy scaffold/check/replay. The new compact outline compiler emits 1.1 or course-only 1.2, not 1.3.
- Explicit public cast reuse with authored names/roles, existing bundled pack scenery, data-only lighting/fog/grade moods, actual native captures and local exports.

## Out of scope today

| Request | Why it cannot honestly be promised |
|---|---|
| Platformer, precision jump course, climbing, grappling, swimming, flight | No general authored jump/air-control/vertical traversal system. Flat X/Z room layouts and on-foot checkpoint spheres are not a platformer. |
| Racer, kart game, driving/flying simulator | No vehicle dynamics, steering model, laps beyond the course's one-lap contract, opponents, traffic or racing AI. A timed walk/run is not vehicle racing. |
| FPS/TPS, bullet-hell, arbitrary shooter | Existing bounded enemy projectile patterns are not a general ranged-player/aiming/ammo/weapon game system. |
| Multiplayer, MMO, online co-op, persistent server economy | No networking, server authority, accounts or shared persistent world. |
| RTS, city builder, farming/survival simulation, crafting/economy | No general resources/counters, scheduling, production, construction or simulation loops. Inventory is finite identities, not a money or materials economy. |
| Seamless open world | Regions are a finite connected room graph, not continuous terrain streaming or global simulation. |
| Arbitrary RPG statistics, XP, branching skill trees, procedural loot | Abilities are finite monotone tokens; no general leveling, currencies, random loot or per-game scripts. |
| Arbitrary genre mashup/module combination | Contracts impose ownership and family restrictions; e.g. a puzzle room cannot also host a challenge and the puzzle family excludes regions. |
| Original assets for every noun in a prompt | This lane reuses existing bound assets and colours the runtime mood. It does not implement prompt-to-mesh, general image/texture generation, external converters or arbitrary project-local generators. A purple fog/grade is not a new purple asset library. |
| Bespoke wizard/pirate costumes or autonomous conversations | Public cast are stand-ins. Character generation/adoption remains separately gated; dialogue is authored finite text, not live NPC inference. |
| Native Windows/Linux host certification | Native tool runner on this base requires macOS Seatbelt. Windows export is a target, not evidence of native Windows operation. |
| Human fun, art approval, balance or production readiness | Checkers and bots measure bounded properties. The author can inspect pixels and list weaknesses, but cannot approve art on the user's behalf. |

## What “passed” means here

1.1: `proved` story obligations, complete physical bot paths for every ending, and Godot witness replay/save round-trip. 1.2: `conditional` stays conditional; AUTHOR adds a replay route for single-ending module games requiring **fresh** complete physical module coverage, strict recorded input/movie hash playback and a real initial-checkpoint save/load. Multi-ending module movies are refused rather than inferred from one continuous terminal run. 1.3 is documented separately, not newly verified here.

A stranger's install, a second model following the skill, five varied prompts, native Windows, recipient exports and human visual acceptance remain separate product acceptance requirements.
