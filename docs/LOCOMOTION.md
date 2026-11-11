# Base locomotion (`base_v1`)

One run and one walk for every walking humanoid, made for that body's own legs.

A character file goes in; the tool measures the body, solves a planted-foot run and walk for it, checks both with
numbers, and either writes a new file with the two clips and a small `locomotion` block, or refuses in plain words and
writes nothing. The file that went in is never changed.

| Piece | Where |
|---|---|
| The format (plain data) | `adventure_maker/locomotion/base_v1.json` |
| Measure, bake, validate | `adventure_maker/locomotion/core.py` (`read_body`, `bake`, `check`, `attach`, `rig_contract`) |
| Command line | `tools/locomotion_bake.py` (`bake`, `check`, `shipped`, `fixture`) |
| Plugin action | `hermes64_character` `action: "locomotion"`; `build` bakes by default; `bind` takes `legacy` |
| Runtime | `runtime/godot/actors/character.gd` (`set_locomotion`, `drive`, `advance_pose`; continuous phase: `loco_*`; stepped: `drive_step`), `assets.gd` (`locomotion_block`), `bridge.gd` |
| Engine check | `tools/locomotion_runtime.py` + `runtime/godot/tests/locomotion_capture.gd` (strips, ground-line strips, slide in play; `id=file.glb@stepped` plays the stepped path), `tools/locomotion_compare.py` (before / after table) |
| Tests | `tests/test_locomotion.py` + `runtime/godot/tests/locomotion_legacy.gd`, `locomotion_slide.gd` (headless slide in play) |
| Box test bodies | `adventure_maker/locomotion/fixtures.py` |
| Shipped cast, baked as new files | `characters/locomotion/` + `manifest.json` |

It needs numpy (as the rig kit does). The plugin still loads without numpy; a build then keeps its own clips and says so.

## 1. What a body must have

Rig `human16_v1`, `human16_v3`, or any armature that carries these bones by name (extra joints such as toes or fingers
ride on their nearest listed ancestor; `--bone-map` renames):

- required: `pelvis spine head upper_arm_l/r forearm_l/r thigh_l/r shin_l/r foot_l/r`
- optional: `root hand_l/r`

Measured from the file (rest pose), all in the report under `measurements`:

| Measurement | How | Refused when |
|---|---|---|
| height | top of the skinned mesh over the floor | outside 0.3 to 4.0 m (`height`) |
| hip height | mean height of the two thigh joints | under 20 % of the height (`no_hip_height`) |
| thigh, shin length | joint to joint, per side | a segment under 15 % of the hip height (`short_leg_segment`); left and right differ by more than 5 % of the hip height (`asymmetric_legs`) |
| boot outline | vertices that follow the foot joint; toe, heel, ankle height, sole points | no such vertices (`no_boot`), no length (`no_boot_length`) |
| boot gap | inner edge of each boot to the centre line | a boot reaches across the centre line at rest (`legs_cross`) |
| arm lengths | upper arm, forearm (to the hand joint, or the end of the forearm's vertices) | no arm vertices (`no_arm`) |
| arm rest angle | upper arm away from straight down, front view | never; outside 5 to 40 degrees (T pose, arms flat on the body) the arm is first turned to 12 degrees and the report says so |
| torso lean limits | mean forward pitch of the pelvis-to-head line | data: run 12 to 18 degrees, walk 0 to 8 degrees |
| facing | boots reach further forward (+Z) than back | `facing` |
| joint scale | every rest matrix is a rotation | `scale` |

Other refusals before any clip is tried: `not_glb`, `no_skin`, `no_mesh`, `missing_bones`, `hierarchy`, `mirrored`.

## 2. The cycles

Both cycles are 16 keys at 15 fps, STEP, two steps of 8 keys; the right leg is 8 keys behind the left. Distances are in
standing hip heights, so step length and ground speed scale with the leg: a body's stride is
`stride_mps * hip_height / 0.804`.

- **run**: contact `[0]`, down `[1]`, push-off `[2, 3, 4]`, flight `[5, 6, 7]` (both boots off the ground). Reference
  ground speed 2.2 m/s; lean (`lean_deg`), pelvis yaw, hip height per key (`hip`) and arm swing (`arm_deg`) as written
  in the spec.
- The lean and yaw values of both cycles are those of the run and walk reviewed on tall_v3 (stills-04/05). Baking
  the tall_v3 file moves no dial and gives its own reviewed clips back (largest vertex distance 0.0 mm over all 32
  keys; `tests/test_locomotion.py` checks it when that build is on the machine).
- **walk**: stance keys 0 to 9 (keys 8 and 9 overlap the other foot's strike), passing pose at key 4, no flight.
  Reference ground speed 1.1 m/s.
- **blend**: run starts at `enter` 2.0 m/s and ends below `exit` 1.7 m/s on the reference build; both scale with the leg
  like the strides.

The planted foot is solved, not keyed: while a boot is on the ground its ankle is put where a boot that does not move
over the ground has to be, and the knee and hip follow. The swinging leg follows the angles (run) or ankle path (walk)
in the spec.

## 3. What is checked, and what happens on a failure

Limits live in `base_v1.json` (`limits`). Every clip is measured on the skinned mesh:

| Metric | Limit |
|---|---|
| planted-boot sliding (`slip_mps`) | <= 0.25 m/s; a clip with no boot on the ground at all fails (`no_contact`) |
| flight keys per step | run >= 2, walk = 0 |
| hip bounce (`bounce_hip`, in hip heights) | run 0.085 to 0.125, walk 0 to 0.08 |
| lean | run 12 to 18 degrees, walk 0 to 8 degrees |
| boots and the centre line (`boot_gap_min_m`) | >= 0: no boot crosses to the other side |
| legs in their plane | knee <= 10 mm out of the leg plane; leg midline <= 30 mm off its side |
| limb through the torso | 0 vertices of forearm, hand, shin or foot inside the torso surface (the bones are named) |
| seam gap (`seam_gap_m`) | <= 3 mm between mesh pieces that touch at rest (the rig kit's own seam check) |

**Fit dials.** The bake starts from the cycle as written. When a metric fails and has a dial, the dial moves one step
and the clip is measured again; the first setting that passes everything is kept. The report lists what moved
(`dials_moved`) and every attempt (`tried`). Dials: `boots_cross` (less pelvis yaw), `lean_high` / `lean_low`,
`bounce_high` (shorter step and lower ground speed together), `limb_in_torso` (upper arm further out), `seam_gap`
(the swinging foot follows its shin more closely; the planted foot is not changed).

**Refusal.** A failure without a dial, or a dial at its end, refuses the body: `clip_refused`, with the numbers in the
report. Nothing is written. Example from the shipped cast: `fv_elder` (legs pass through the robe, which follows the
pelvis; the base has no cloth that moves with the legs).

## 4. What comes out

A new GLB: the same meshes, materials, skin and every other clip with the same values, plus

- clips `run` and `walk` (16 keys, rotation on every skin joint, translation on the grounding joint);
- with `--keep-legacy`, the file's old clips as `run_legacy` / `walk_legacy`;
- root `extras.hermes64_locomotion`:

```json
{"format": "hermes64-locomotion-base/1.0.0", "base": "base_v1", "source_sha256": "...",
 "cycle_keys": 16, "fps": 15, "hip_height_m": 0.678,
 "walk": {"stride_mps": 0.928},
 "run": {"stride_mps": 1.855, "enter_mps": 1.687, "exit_mps": 1.434, "flight_keys": [5, 6, 7, 13, 14, 15]},
 "sole": {"l": {"toe": [..], "heel": [..]}, "r": {..}}}
```

and a JSON report (measurements, metrics per clip, dials, hashes). The same input gives the same bytes: across
processes, hash seeds and Python versions (measured: Python 3.9.6 / 3.14.3 / 3.14.9 with numpy 2.0.2 / 2.4.3 / 2.5.4
on one arm64 Mac; not measured on another CPU or operating system). For that reason the solver does not use
`math.hypot` or `sum()` over floats, whose last digit differs between Python versions; keep it that way when
editing `core.py` (`Determinism.test_same_bytes_under_another_python` fails otherwise).

**Loop period.** A clip keeps the rig kit's 16-key contract, so the file's clip ends at its last key (1.0 s) while one
cycle lasts 16 keys (16/15 s). A player must loop on `cycle_keys / fps`, not on the clip length; looping on the clip
length drops the last key and the planted boot slides. The runtime does this in `set_locomotion`.

**Rig kit contract.** A baked file passes `rigkit validate` except for one rule, replaced by name: the floor rule at
exactly the run's flight keys, where both boots are off the ground on purpose. `rig_contract(glb, rig)` returns those
six as `waived`; every other rig error stays an error.

## 5. Using it

Command line:

```bash
python3 -B tools/locomotion_bake.py bake in.glb --out out.glb [--report out.json] [--rig human16_v1] \
        [--keep-legacy] [--bone-map map.json] [--tuning tuning.json]
python3 -B tools/locomotion_bake.py check out.glb          # measure the run and walk a file already has
python3 -B tools/locomotion_bake.py shipped [--verify]     # the shipped cast -> characters/locomotion/
python3 -B tools/locomotion_bake.py fixture short_stocky --out body.glb
```

Exit 0 = written; exit 2 = `REFUSED (<code>): <message>` and no file.

Plugin (`hermes64_character`):

- `build`: a new character gets baked locomotion by default. The result carries `locomotion` (`baked`, file, strides,
  `changed_to_fit`), or `baked: false` with `why`. The build's own file is kept beside it.
- `locomotion` with `id` (a character built in the project) or `glb` (any character file in the project: imported or
  converted). Writes `characters/locomotion/<id>.glb` and `.json`.
- `bind`: binds the baked file when there is one; `legacy: true` binds the clips the character had before.

Pipelines (generated, imported, converted characters) call one function:

```python
from adventure_maker import locomotion
res = locomotion.attach(glb_bytes, rig='human16_v1')      # never raises for a refused body
if res['ok']:  glb_bytes = res['glb']                       # baked; res['report'], res['rig_contract']
else:          log(res['refused'])                          # {'code', 'message'}; res['glb'] is the input, unchanged
```

This is the hook for the converter tier: call `attach` on the converted GLB and keep the converted clips when the body
is refused; a converter with other bone names passes `bone_map={'shin_l': 'calf_l', ...}`. The converter lane lives in
another worktree and does not call it yet; in this tree the plugin's `build` does, and `locomotion glb=...` covers any
imported file.

## 6. Runtime

Opt-in is by file content. `assets.gd` reads the block from the file; `character.gd set_locomotion` accepts it only
when the file has a `walk` animation and a valid block. No block = `locomotion` stays empty = the playback path that
existed before (`bridge.gd`: walk at `speed / walk_stride_mps`), tick for tick.

With a block, `drive(speed)` picks the cycle (walk below `run.enter_mps`, run at or above it, back to walk below
`run.exit_mps`; 2.0 / 1.7 m/s on the reference build, scaled by the leg in the block) and `advance_pose(delta)` plays it
at **continuous phase**:

- **Phase rate.** Each cycle's phase advances `fps * speed / stride_mps` keys per second (15 keys per stride), every
  tick, fraction kept. A boot on the ground moves back in the body's frame as fast as the body moves forward, so it
  stays where it is on the ground at any speed.
- **Between keys.** Bone by bone between the two keys around the phase (rotations along the sphere). At a key the pose
  is the key, untouched; the file's clips stay STEP. Inside a key interval where a boot touches down or lifts off,
  joint interpolation would drag that boot through the ground band: there the boot goes the straight way between its
  transforms at the two keys (turning evenly), 2 mm above the band (`LOCO_LIFT`), and the thigh and shin are solved to
  reach it (two bones, knee in the plane of the leg as interpolated).
- **walk <-> run.** At load the runtime finds, per boot, where the other cycle's planted boot is where this cycle's is
  (toe and heel points on the ground in both, 4 samples per key) and the longest window, up to 4 keys
  (`LOCO_WINDOW_KEYS`), in which both cycles keep that boot down and the other in the air. The change starts when the
  shown cycle reaches its window: the other cycle comes in at the matching phase, each advances at its own rate, and
  legs, pelvis and root cross-fade over the window (the weight follows the phase of the cycle handing over); spine,
  head and arms fade over 0.2 s (`LOCO_UPPER_S`). Measured windows: 0.5 to 4 keys, the fade moves the planted boot 2 to
  7 mm per key. A file whose cycles have no window switches at a contact key with the phase kept.
- **idle -> cycle.** The cycle starts at the phase whose planted boot (the other in the air) is nearest, along the
  way, to where it is in the pose shown; the pose fades over 0.15 s (`LOCO_START_S`). The idle pose's boots ride with
  the body while the cycle's stays put, so the idle share times the distance travelled may grow and shrink by at most
  0.12 m/s (`LOCO_START_MPS`).
- **cycle -> idle.** The pose eases to idle key 0; a boot in the air or more than 2 cm (`LOCO_STEP_MIN`) from its idle
  place takes a settle step there, 0.25 s per step (`LOCO_STOP_S`), the boot in the air first, lifted 3 cm above the
  band while it moves along the ground; a boot on the ground waits for its step. Then idle plays as before.
- **Tables.** Read once per file from its own clips' tracks (the AnimationPlayer is not touched) and cached per set of
  clips: 21 to 22 ms per file the first time, 0.04 ms after (Godot 4.6.2, one arm64 Mac). Empty when the skeleton lacks
  thigh, shin and foot on both sides: `drive()` then takes the stepped path.
- **Stepped path** (`drive_step`): the runtime before continuous phase, kept as that fallback and as the known-bad
  control. It holds a key until the cycle reaches the next one, so a boot on the ground rides with the body inside a
  held key and jumps back at the next: 1.6 to 8.7 m/s over single ticks, and 0.15 to 2.2 m/s between pose changes
  away from a body's own stride. The clip length is set to `cycle_keys / fps` for it and for `play_clip` callers.
- **Animation is presentation only.** Nothing in the simulation reads the pose: the movie state hash
  (`input/movie.gd state()`) covers story, player physics, actions, camera, menus and module state, not the skeleton,
  the clip or the phase. Combat (`modules/animation_state.gd`) picks its keys from fixed-tick state and owns the actor
  (`module_animation_owner`): `bridge.gd` does not drive it then, and any `play_clip` (or `clip = ""`, a held pose)
  ends the continuous cycles.

Engine check (`tools/locomotion_runtime.py`, Godot 4.6.2, tall_v3, tavi, pp_kid, fv_smith): slide of a planted boot at
or under 0.191 m/s in every play (own strides, controller 1.1 and 3.2 m/s, slow ramp across both thresholds, speed
held between them, a controller programme with stops), drift over one contact at most 1.7 cm. Before / after table,
replay and golden proof: `docs/SLIDEFIX-RESULT.md`.

## 7. Rollout (additive)

Shipped files are not modified. `characters/locomotion/` holds new files, listed in its `manifest.json` with the
source hash, the baked hash, the metrics of the baked clips and of the clips the file had before.

- baked (16): `new_arrival tavi neri sol ivo luma study_07 study_08` (masked bodies), `pp_engineer pp_medic pp_kid
  pp_elder fv_warden fv_smith fv_scribe` (face bodies), `cameo_visor_01` (adult family, tall_v2 / r21;
  `cameo/cameo_visor_01.glb` is untouched). Every baked file also carries the clips it replaced as `run_legacy` /
  `walk_legacy`;
- `cameo_visor_01`'s baked file is not in the repository (`characters/.gitignore` keeps `cameo_visor_01.glb` out of
  `characters/`; manifest row `in_repo: false`). `shipped` writes it on the machine, and a bake of
  `cameo/cameo_visor_01.glb` gives the bytes whose hash the manifest pins (tested);
- refused (1): `fv_elder`;
- not covered: the quadrupeds (`quad16_v1`) and hover bodies.

A project gets a baked file only by binding it. New characters built through the plugin get it by default.

## 8. For agents

- Do not hand-tune a clip in a character file. Change the spec (a new base id) or pass `--tuning`, then bake.
- A refusal is an answer. Report the code and message; do not force a bake by loosening a limit.
- Do not judge the look. Report the measured numbers and mechanical defects; the look is for a human.
- To add a body type the base cannot serve (robes, quadrupeds, hover), write a new base spec; do not special-case
  `core.py` for one character.
- After any change to `base_v1.json` or `core.py`: `python3 -B -m unittest tests.test_locomotion`, then
  `tools/locomotion_bake.py shipped --verify`, then `tools/locomotion_runtime.py` on at least two characters.
- After any change to the runtime (`character.gd` `drive`, `advance_pose`, `loco_*`): `python3 -B -m unittest
  tests.test_locomotion` (ContinuousPhase and Runtime run real Godot headless), then `tools/locomotion_runtime.py --views
  side --ground` with each baked character also given as `id=file.glb@stepped`, and `tools/locomotion_compare.py`
  against the previous `runtime-metrics.json`: the stepped rows must equal the previous numbers and the legacy controls
  must be unchanged. Do not tune a slide away by changing the keys; the keys are the approved poses.
