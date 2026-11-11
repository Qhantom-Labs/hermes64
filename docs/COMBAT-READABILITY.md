# Combat readability

Lane COMBAT. This changes how a fight looks and sounds while it is running. It does not change how the fight plays.
The simulation never reads anything described here. Gameplay API 1.0.0 games produce the same state hashes as before:
Reedland Relay matches MERGE3's run on all 1901 ticks (see [COMBAT-RESULT.md](COMBAT-RESULT.md)).
Robot and boss behaviour is covered in [ROBOTS-BOSS.md](ROBOTS-BOSS.md).

## What changed

MERGE3's real-renderer filmstrips had five readability problems:

- the camera was wide and fixed
- the fighters were tiny (player about 30 px tall, enemies about 15 px, at 320x240)
- the arena was dim and brown
- dark enemies overlapped the player
- the telegraphs were subtle

### Camera: a challenge profile

When a combat attempt starts, the view eases from the room's authored camera into a closer combat framing:

- **Blend:** smoothstep over `camera.blend_ticks` (30 ticks, 0.5 s). After the attempt it eases back the same way.
- **Position:** behind and above the player at `camera.pitch_deg`, using the authored camera's yaw.
- **Centre:** between the player and the focus target, weighted by `camera.target_weight` and followed with a dead zone.
- **Distance:** pulls back only as far as needed to keep the player, the focus target and any robots within `camera.others_radius_m`. It stays within `min_distance_m`..`max_distance_m`.
- **Lean and lift:** when the player and the target line up along the view, one body would cover the other. That happens when the target stands beyond the player, or when a robot stands between the camera and the player. The view then does two things:
  - it orbits up to `camera.lean_deg` (10°) toward the side that separates them
  - it rises up to `camera.overlap_pitch_deg` (12°), because a steeper view spreads ground positions apart on screen

  Big robots widen this window, and they add to the fit margin (0.6 m per unit of visual scale above 1), so the boss stand-in keeps its whole body in frame. Both moves are eased, and the side has hysteresis.
- **Controls:** the authored cameras and `player.camera_basis` are never touched. Controls stay camera-relative to the authored view, so they read the same with the lean at most 10°.
- **Collision:** the eye is pulled in front of static geometry and kept under an interior ceiling.
- **Lens clear (exterior rooms):** while the combat view is at least half blended in, dressing is hidden if it would block the closer lens. That covers the "framing" pieces placed for the authored lens, plus any dressing within `camera.near_hide_m` of the eye or crossing the eye-to-fighter sight lines. It comes back as the view blends out.
- **No shake, ever.** The only time effect is the simulation's own 2-3 tick hit-stop.
- **Reduced motion** (the Actions option): the view cuts in and out instead of blending, follows with a wider dead zone, and never leans or lifts.

### Lighting and contrast

Lighting is scoped to combat and stays inside the N64 convention. Every term eases in and out with the fight. Nothing
here changes the room look outside a fight.

- **Actor kicker.** This is the one extra character light the convention allows, and it is the "rim" here. It eases up to `light.kicker`, capped at `kits/core/n64_look.json` `lighting.actor.kicker_max`. When the fight ends it returns exactly to the room's own kicker.
- **Fighter fill.** Each fighter gets a camera-side fill through the existing per-material vertex point light. It is warm on the player (`light.player_fill`) and cool on enemies (`light.enemy_fill`), so silhouettes separate by hue and value.
- **Floor pool.** One soft painted light pool on the arena floor (`light.pool`, capped at `lighting.lamp_pool.max_strength`) lifts the ground value under the fight.
- **Contact shadow.** A dark disc under every fighter (`light.contact_shadow`). Blob shadows only; no real-time shadows.
- **Particle motes** (room `look.exterior.particles`) are culled within `light.mote_near_m` of the closer lens. Without this they read as large discs. The cull is 0, meaning unchanged, outside combat.

### Telegraph language

Telegraphs are drawn as flat painted decals: unshaded, no glow, no depth write (`shaders/n64_marker.gdshader`). Each
marker is a pure function of fixed-tick state (`modules/combat/telegraph.gd`, `robot.gd telegraph_info`, `hazards.gd`).

| Threat | Floor marker | Timing cue |
|---|---|---|
| reed_warden melee (`melee_approach_v1`) | reach disc around the enemy | fills over the windup |
| dash (`melee_dash_v1`), walker bump, boss lunge | lane from the attacker along its latched direction | fills over the windup, turns danger red in the last `telegraph.danger_ticks` |
| brute slam, boss slam | landing disc at the impact point plus a thin outer ring at the shockwave's full reach | as above |
| shockwave | expanding ring band (the band that hurts) | danger red just before it reaches the player |
| drone shot, boss memo/volley | aim lane while it winds up; then a lane ahead of each live shot (short stub once it will miss); the orb has a contact dot and turns pale blue when deflected | as above |
| boss surge | dash lane plus a reach ring where the surge ends | as above |

- **Pre-attack flash.** The enemy's camera-side fill steps to `telegraph.flash_light` for `telegraph.flash_ticks` (10) before the attack. It is two bands, never a strobe.
- **Audio cue.** One catalog id per telegraph. It is chosen in this order: the robot's or boss pattern's own `cue`, then the template's audio, then `telegraph.audio`. Cues are staged as `cue:<id>` rows in `runtime/audio.json` with their catalog sha256, only for games that have a combat module. They play on two voices at -14 dB, and the same cue restarts at most every 4 ticks.
- **Safe-to-dodge glyph.** A small diamond appears near the threat only while a roll started now would carry the player through the contact on its i-frames (`Telegraph.dodge_open`: contact plus active ticks within `ROLL_IFRAMES` = 15). It is a glyph only, with no text.
- **Player hit feedback.** Robots and hazards apply a 2-3 tick hit-stop (simulation) and a 6-tick push slide away from the attacker (simulation, readable knockback). The view adds a thin screen-edge flash for `feedback.edge_flash_ticks` (presentation).
- **Boss.** A minimal pixel health bar with phase notches, and no text. Phase changes and the defeat play a short flat expanding floor ring and a cue.

The challenge entry posts of the fight in progress are hidden while it runs, because they would stand inside the arena
as clutter. Boss events never reopen the narration panel.

## Tunables for the owner

Edit `runtime/godot/modules/combat/readability.json` to change the defaults for all games. To change one pack or one
room, add a `"combat"` block with the same keys:

- **Pack:** in the pack's `view.json`.
- **Room:** in `metadata.presentation.rooms.<room>.combat`. The room wins over the pack.

Every value is clamped to the `ranges` table, and light strengths are capped by the N64 convention.

| Want | Key | Default | Range | Effect |
|---|---|---|---|---|
| camera closer / farther | `camera.distance_m` | 4.5 | 2.5-12 | base distance before fitting; also `camera.max_distance_m` (6.5) for crowded fights |
| camera higher / lower | `camera.pitch_deg` | 38 | 12-60 | higher = more top-down, separates fighters; lower = more cinematic |
| overlap handling | `camera.lean_deg` / `camera.overlap_pitch_deg` | 10 / 12 | 0-15 / 0-25 | how far the view orbits and rises when fighters line up |
| rim (kicker) strength | `light.kicker[1]` | 0.22 | capped at `kicker_max` | brightness of the character kicker during fights |
| enemy separation | `light.enemy_fill[1]` | 0.55 | 0-1 | cool fill on enemies |
| ground lift | `light.pool.strength` | 0.22 | capped at `lamp_pool.max_strength` (0.3) | brightness of the painted floor pool under the fight |
| telegraph timing (flash) | `telegraph.flash_ticks` | 10 | 0-30 | how early the pre-attack flash starts |
| danger colour lead | `telegraph.danger_ticks` | 10 | 0-30 | how early decals turn red |
| decal opacity | `telegraph.alpha` | 0.5 | 0.15-0.75 | floor marker strength |
| blend speed | `camera.blend_ticks` | 30 | 0-90 | 0.5 s at 60 Hz |
| edge flash | `feedback.edge_flash_ticks` / `edge_alpha` | 8 / 0.55 | 0-20 / 0-0.8 | screen-edge hurt flash |

To switch a group off, set `camera.enabled`, `light.enabled` or `telegraph.enabled` to false. The capture harness's
`readability_off` and the perf lever `readability_off` switch all three off, which gives the MERGE3 view of the same
fight.

The attack timing itself (windup, active and recovery ticks, the robots' push, hit-stop and knockback) is game data in
the combat module, not here. See [ROBOTS-BOSS.md](ROBOTS-BOSS.md).

### MERGE5 trials: contrast in the warm-earth pack

The style gate calls the closer combat frames of pack n64_v0 (kit forest_village) low-contrast, fog-flattened and flat.
MERGE5 tried the levers above on the city arena and Reedland films (`tools/merge5_contrast.py`; table and sheets in
`docs/MERGE5-LOG.md` section 9) and **kept none**: no setting passes the style gate on any frame. The most effective
block, if you want to see it, goes into `packs/n64_v0/view.json`:

```json
"combat": {"light": {"pool": {"strength": 0.3, "scale": 1.3, "color": "#fff8ec"}}, "camera": {"pitch_deg": 30.0}}
```

It clears most fog-flattened frames (city 59 of 63 -> 14) and lifts the global contrast (median 0.294 -> 0.364), but the
floor turns grey-beige, the red/orange telegraph markers get paler, flat-frame and no-highlight failures stay, and
Reedland's pixel-crisp n64 failures rise (18 -> 21 of 27). A combat fog push (lighter fog only while fighting) does not
exist in the runtime; emulated, it adds contrast (city 0.410) but not a pass.

## Files

- **Profile:** `modules/combat/readability.json` and `readability.gd` (resolution, clamps, caps)
- **Camera:** `modules/combat/camera.gd`
- **Lighting, decals, flash, contact shadows, projectile and drop visuals, lens clear, cues:** `modules/combat/stage.gd`
- **Telegraph functions:** `modules/combat/telegraph.gd`
- **HUD (dodge glyph, edge flash, boss bar):** `modules/hud.gd`
- **Shaders:** `shaders/n64_marker.gdshader`, `shaders/n64_snow.gdshader` (`near_cull`)
- **Cue staging:** `adventure_maker/assets_v3.py` `combat_cues`
- **Host wiring:** `modules/host.gd` (`tick_readability`), `view/audio.gd` (`cue`)
- **Tests:** `runtime/godot/tests/combat_robots.gd` (profile, camera), `tests_story/test_combat_templates.py` (profile data, caps, cues)
