# Robots and bosses: authoring guide

Gameplay API **1.1.0** is additive. It adds three robot enemy templates, a boss template, fixed-tick projectiles and
shockwaves, reward drops, and checker rules that reject fights that cannot be won. A game author, or the agent,
creates a new robot or boss by writing data only. No per-game code is needed.

On compatibility:

- 1.0.0 games stay exactly as they were: the same contract files, the same proofs, the same runtime path and the same state hashes.
- To use the new templates, set `gameplay.api_version` and every module `version` to `"1.1.0"`. Mixed versions are rejected.
- 1.0.0 data is valid unchanged under 1.1.0.

Readability (camera, lighting and telegraph language) is covered in [COMBAT-READABILITY.md](COMBAT-READABILITY.md).
The worked example is `tools/city_arena.py` (`city_arena_test`).

## Templates

Every archetype has these fields:

- `id`, `name`, `max_health`, `speed_mps`, `aggro_range_m`, `leash_range_m`, `attack_range_m`
- `fsm`: `{template, initial: "idle", states: [idle, approach, telegraph, attack, recover, hurt, dead]}`

On top of those, each template takes its own blocks. Each block is closed, and every number has a bound (see
`story/modules/schema.py` and `contracts/gameplay/1.1.0/combat.json`).

| Template | Matches charsys robot | Behaviour | Extra blocks |
|---|---|---|---|
| `walker_patrol_v1` | `body.robot_walker` (small round walker, e.g. `g_porter`) | patrols `walker.patrol_m` around its spawn, spots the player (`spot_ticks`, turns to face), approaches, telegraphs a short **bump** lunge (`bump_speed_mps`), recovers | `attack`, `robot`, `walker` |
| `brute_slam_v1` | `body.robot_brute` (tall brute, `g_sentry`) | slow approach, big overhead **slam** on a landing disc (`brute.slam_radius_m`), which then sends a **ground shockwave** ring (`wave_speed_mps`, `wave_max_m`, `wave_width_m`); armoured until it recovers (vulnerable recovery) | `attack`, `robot` (usually `armor: until_recover`), `brute` |
| `hover_drone_v1` | `body.robot_floater` (`g_drone`) | floats at `hover.hover_m`, holds `keep_distance_m`, strafes (`strafe_mps`, alternating each cycle) for `strafe_ticks`, lines up, telegraphs, fires one slow **shot** (`hover.shot`: speed, radius, lifetime, deflectable) | `attack`, `robot`, `hover` |
| `boss_phases_v1` | `body.robot_brute` + boss crown (`g_foreman`, clip set `robot_boss`) | multi-phase health; each phase cycles through its own attack patterns | `robot`, `boss` (no `attack`) |

### `robot` block

All four templates take this shared tuning.

| Field | Meaning |
|---|---|
| `hurt_ticks` | stagger length after a landed hit (armoured robots do not stagger) |
| `knockback_m` | how far a hit pushes the robot (over 6 ticks) |
| `push_m` | how far its hit pushes the player (a 6-tick readable slide) |
| `hitstop_ticks` | 0-3: the whole fight holds for this many ticks when it hits or is hit; a dodge or swing pressed meanwhile is kept |
| `armor` | `none`, or `until_recover`: hits land only while it recovers from its own attack (others show an armour clink) |
| `heal_drop` | 0-4: health restored by the pickup it leaves on death (the encounter's last robot ends the fight, so its drop is moot) |
| `cue` | telegraph audio catalog id (`''` falls back to the template's), presentation only |

### Boss block

```json
"boss": {
  "defeat_hitstop_ticks": 6,
  "phases": [
    {"id": "opening",     "health_permille": 1000, "patterns": ["lunge", "memo"]},
    {"id": "restructure", "health_permille": 600,  "patterns": ["slam", "memo", "lunge"]},
    {"id": "overclock",   "health_permille": 300,  "patterns": ["surge", "slam", "volley"]}
  ],
  "patterns": [
    {"id": "lunge", "kind": "bump", "windup_ticks": 34, "active_ticks": 14, "recovery_ticks": 60, "damage": 1,
     "speed_mps": 5.0, "size_m": 1.2, "count": 1, "deflectable": false, "cue": "core.combat.swing.light"}
  ]
}
```

- **Phases.** A phase is active while health is at most `health_permille`/1000 of `max_health`. The first phase is 1000, and the rest must strictly descend (1-4 phases). Crossing a threshold plays the phase beat: a 3-tick hit-stop, a floor ring and a cue, plus the story event `boss_phase`. The boss then restarts the new phase's list from the top.
- **Patterns** (1-8 per boss) reuse the robot attacks plus one signature. Their `speed_mps`, `size_m` and `count` mean different things per kind:

| `kind` | `speed_mps` | `size_m` | `count` |
|---|---|---|---|
| `bump` | lunge speed | contact reach | - |
| `slam` | shockwave speed | shockwave reach | - |
| `shot` | projectile speed | projectile radius | fan of 1-5 shots, 18° apart |
| `surge` (signature) | dash speed along a lane | reach of the ring it leaves at the end | - |

- **Defeat beat.** When the boss falls:
  - `defeat_hitstop_ticks` of hit-stop, then a large floor ring and a cue
  - the challenge rewards
  - the story event `boss_defeated`, followed by `encounter_cleared` once the beat has played

### Encounter fields (1.1.0)

- **`boss`** names the spawn whose defeat is the boss beat. It must be a `boss_phases_v1` spawn in the last wave.
- **`gate`** names a door of the encounter room. While the fight runs, the arena clamp locks the player in. The door itself stays shut until the owning challenge completes, which must be one of its own conditions: `{"challenge": <owner>, "status": "completed"}`.

The runtime shows bars across that door: rust while the fight runs, dark iron before it. They are gone once the
challenge completes. Waves (`spawns[].wave`, 0-7) spawn in order as each wave is cleared.

### Projectiles, shockwaves, drops

All three are fixed-tick state, hashed and saved with the fight (`modules/combat/hazards.gd`).

**Projectile**

- moves `speed/60` per tick
- hurts once on contact unless a roll's i-frames cover the contact
- despawns at `lifetime_ticks` or the arena edge
- a deflectable shot is reflected by a swing whose hit window meets it in front of the player; it flies back 1.5x faster and damages the first robot it reaches

**Shockwave**

- a ring band growing at its speed up to its reach
- hurts a grounded player once while the band covers them
- a roll's i-frames pass through it

**Drop**

- heals when walked over, within 0.7 m
- expires after 900 ticks

## Checker rules

Each 1.1.0 encounter gets proof obligations from `story/modules/combat_bounds.py`:

- `combat_stall:<encounter>`
- `combat_strength:<encounter>`
- `combat_projectile:<encounter>`
- `combat_shockwave:<encounter>`
- `boss_gate:<encounter>`, when the encounter has a gate

The bound is optimistic for the player: perfect swings, no travel time. Failing it rejects the game. Passing it does
not prove the fight is fair or fun.

| Rule | Rejects | Known-bad control |
|---|---|---|
| stall | a boss phase with no pattern (the boss stops fighting; armoured, it can never be hit) | `city_arena_phase_no_attack` |
| strength | more than 5400 ticks (the playtest budget per challenge) of perfect play, or unavoidable damage (windup < 6 ticks and contact outlasting the roll's i-frames, undodgeable shots or rings) adding up to the player's health | `city_arena_boss_strong` |
| projectile | a shot that can be neither side-stepped (run + roll before it arrives) nor rolled through (its pass over the player outlasts the 15 i-frame ticks) | `city_arena_projectile_unavoidable` |
| shockwave | a ring that cannot be rolled through and reaches across the whole arena | (covered by the tests) |
| boss gate | a gate door whose other conditions can never hold after the boss falls (the arena stays locked) | `city_arena_gate_never_opens` |

The schema and validation also reject these at compile time:

- a boss that is not in the last wave
- an unnamed or wrong boss spawn
- a gate door that is missing, or that lacks the owner condition
- phases that are not strictly descending, or a first phase below full health
- unknown or duplicate pattern ids
- robot blocks on the melee templates, or an `attack` block on the boss

Each of these has a control in `tests_story/test_combat_templates.py`.

## Art binding (stand-ins, replaced in MERGE5)

The robot models come from the character system. Bound in MERGE5 (below); before that, and still as the fallback:

1. The host binds each robot to an existing enemy model as a stand-in, using `runtime/godot/modules/combat/robots.json`. Each row gives a model, scale and lift. The defaults:
   - walker → `reed_warden` at 0.95
   - brute → `cairn_dasher` at 1.45
   - drone → `reed_warden` at 0.78, floating 0.6 m over its contact shadow
   - boss → `cairn_dasher` at 1.9
2. Robots play the enemy clip names the combat art already uses, one per FSM state: idle, move (approach), telegraph, attack, hurt, death and recover. The charsys `robot` and `robot_boss` clip sets contain exactly these names, and `robot_boss` adds `attack_sweep` and `attack_slam`.

**The manifest seam.** The host resolves an archetype's art in this order:

1. `combat.json` `enemies[<archetype id>]`
2. `combat.json` `templates[<fsm.template>]`, the manifest's own alias
3. the stand-in table

`combat.json` is produced from `characters/combat/manifest.json` by `characters/integration.py stage_combat`. When
MERGE4 stages the robot GLBs as enemy rows, either keyed by archetype id or aliased by template, they replace the
stand-ins with no code change. Hit and telegraph windows already come from each row's clip phases.

Charsys robots run about 1.2-1.8 m tall. If a robot reads wrong at combat distance, adjust its row scale in
`robots.json`, or the staged row.

### MERGE5: the character-system robots are bound

The stand-ins are replaced for both combat kit packs (forest_village, polar_pod). `python3 -B -m tools.merge5_robots`
builds the four robots with the production character pipeline (python exporter, every gate including the Blender
silhouette review, a second build for determinism) from MERGE4's parity briefs, and stages them as
`characters/combat/robots/<pack>/<id>.glb` with the side manifest `characters/combat/robots.json`:

| Template | Row | Body | Height | Triangles (GLB) | Clips |
|---|---|---|---|---|---|
| `walker_patrol_v1` | `robot_porter` | walker | 1.21 m | 450 | 17 |
| `brute_slam_v1` | `robot_sentry` | brute | 1.93 m | 460 | 17 |
| `hover_drone_v1` | `robot_drone` | floater | 1.17 m (hovers 0.23 m from its own clips) | 456 | 17 |
| `boss_phases_v1` | `robot_foreman` | brute + crown | 2.16 m | 570 | 19 (adds `attack_sweep`, `attack_slam`) |

`stage_combat` merges the rows for the robot templates a game actually uses into its `combat.json`, as enemy rows
plus `templates` aliases (step 2 above), hash-checked like the rest of the combat art. The host then binds them with
no runtime change: no stand-in scale or lift applies, the visor face atlas animates per clip, and a game without
robot templates gets an unchanged `combat.json`. The stand-in table stays as the fallback for a build without the
robot art. Tests: `tests/test_merge5_robots.py` and `runtime/godot/tests/merge5_robots.gd`
(`python3 -B -m tools.merge5_robots godot LABEL --pack forest_village|polar_pod`).

Not done: the host plays `attack` for every boss pattern; the `attack_sweep` and `attack_slam` clips are in the boss
GLB but no runtime rule selects them yet. The foreman's crown is declared 56 triangles in
`characters/library/parts.json` but measures 76 in the GLB (the actor total, 570, is under the 900 cap).

## Testing a new robot or boss

```sh
python3 -B -m tools.city_arena /tmp/my_arena            # compile + check the example (or your own spec)
python3 -B -m tools.combat_acceptance LABEL --python <venv python> --games city_arena_test
python3 -B -m tools.combat_godot LABEL                   # Godot assertions per template
python3 -B -m tools.combat_capture LABEL <run folder>    # real-renderer filmstrips
```

The module bot (`runtime/godot/playtest/combat_bot.gd`) fights 1.1.0 encounters through the real Actions layer. It:

- holds Focus near the target
- walks out of floor decals
- rolls through rings and shots when the dodge glyph's window is open
- deflects deflectable shots from its target
- baits armoured robots and strikes during their recovery

It reads only what the player sees. 1.0.0 encounters keep the original bot path, so their inputs and hashes are
unchanged.
