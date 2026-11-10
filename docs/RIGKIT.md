# Rig kit: build a character on the skeleton, and the clips work

The rig kit is a versioned skeleton contract (`contracts/rig/1.0.0.json`). Anyone can build characters on it: the
generator, CHARSYS recipes, a Blender artist, another agent or tool, hub contributors. A character skinned to the
skeleton gets the rig's whole clip pack with one call, and one validator decides whether it is usable. Exact
signatures are in `docs/RIGKIT-API.md`. Stdlib and numpy only; Blender is never needed.

| rig | for | joints | clips in the pack |
|---|---|---|---|
| `human16_v1` | people, walker and brute robots, hover robots (mapped, see below) | 16 | 7 base + 6 combat |
| `quad16_v1` | cats, dogs | 16 | 7 |
| `dasher16_v1` / `warden15_v1` | the two enemy creatures | 16 / 15 | 7 (enemy FSM) |

Each `rigs/<rig>/` holds four files. `rig.json` has bone names and order, the hierarchy, the reference rest pose,
axis and scale conventions, mirror pairs, joint limits, the proportion envelope, sockets and budgets. `clips.glb` is
the clip pack: the skeleton plus every clip, with no mesh. `clips.json` holds per-clip metadata: loop flag, phases,
combat hit windows, i-frames, guard frames, enemy FSM states, face cells and floor clearance per key, plus the
sha256 of every file. `mannequin.glb` is the plain mannequin: 354 tris for human, 248 for quad, every clip attached.
It is the reference subject.

## Build on the skeleton

**In Blender.**
1. Import `mannequin.glb`. It brings the armature with the exact names, order and rest pose.
2. Model your mesh around it, then parent it to the armature with weights:
   - at most 4 influences per vertex, normalized;
   - do not rename, add or reorder bones;
   - do not rotate a bone at rest. Every bone points +Z with roll 0, so rest rotations are identity.
3. Export glTF binary with +Y up.
4. Run `attach_clips` to add the pack, or author your own clips at 15 fps STEP, 16 keys.

A from-scratch armature works too: bone heads go at `rig.json` `rest_world`, converted from glTF to Blender as
(x, -z, y), and each tail sits at head + (0, 0, 0.05). Proportions may differ from the reference, within
`rig.json:proportions`.

**In code.**
1. Write a GLB with one skin whose `joints` are the rig's bones in contract order. The armature node is
   `rig_<rig>`; the skinned mesh is `kit_body`.
2. Joint nodes are translation-only, with inverse binds = translation(-rest_world).
3. Use JOINTS_0 / WEIGHTS_0.
4. Then:

```python
from adventure_maker import rigkit
glb = rigkit.attach_clips(my_glb_bytes, 'human16_v1')    # copy the clip pack in (deterministic bytes)
report = rigkit.validate_character(glb, 'human16_v1')   # report['ok'], report['errors'], report['checks']
```

The generator path writes characters with the Blender-free exporter (`adventure_maker.nbchars`). Its clips are
solved per body and are parity-proven against Blender.

CLI: `python3 -m adventure_maker.rigkit validate FILE.glb` (exit 0 = pass), `... attach IN.glb OUT.glb --rig ID`,
`... report --oracle DIR --out report.json`.

## What passing means

Passing means all of the following hold:
- the file is valid glTF;
- it is skinned to exactly this skeleton: names, order, hierarchy, identity rest rotations, consistent inverse binds;
- weights sum to 1 with at most 4 influences, and nothing is NaN;
- the budgets hold;
- every required clip is present at 15 fps, 16 keys, STEP;
- the root moves vertically only;
- on every key of every clip, measured with the numpy LBS reference (what the runtime plays):
  - the seams stay closed within 3 mm at the neck, limb roots and attached pieces;
  - no triangle edge stretches or collapses outside 0.45 to 1.8;
  - the lowest vertex stays on the floor (±2 mm; creatures may lift, never sink).

Passing does not mean the character is on-style (the style gates cover palette, shading and faces) or good art
(human review). Crossfades are not validated either; the runtime plays STEP.

## How attach works, and its limits

- **Copy, not solve.** Joint rotations are copied verbatim. That is valid on any proportions because rest rotations
  are identity. Per key, the root is regrounded so the lowest vertex keeps the pose source's floor clearance. Hand
  IK targets are not re-solved for the new body: held props, hands on hips and the like may drift a few cm.
- **Deformation guard.** On a key where your skinning would collapse an edge past the validator limit, the joint
  causing it rotates less: slerp toward rest in 0.1 steps. Changed keys are listed in the animation extras
  `rigkit_guard`; turn this off with `guard=False`.
- **Pose source.** The human pack is posed on the `pp_medic` face-head body. Its generator arm solutions are the most
  conservative of the cast. Copied verbatim, the pack validates on all 29 published characters (16 combat cast,
  visor cameo, 12 animals) with no guarded key. The first choice, a masked hood body, collapsed the blended
  face-head shoulders at `death` key 8.
- **Seams.** Generator-built files are checked with the generator's own join table. Any other build uses the generic
  rule: separate mesh pieces must form one connected body at rest, and each contact must stay within 3 mm on every
  key. A rigid piece with a vertex at its joint pivot, buried in the parent piece, always passes; that is how the
  mannequin is built. One continuous, smoothly weighted mesh also works, if its bends stay inside 0.45 to 1.8.
- **Hover robots** use `human16_v1`, with no separate `hover12_v1`:
  - the shell maps to pelvis + spine, the dome to head, the arm pods to the arm chains, the skirt to pelvis;
  - the leg joints carry no weight;
  - set rig node extras `hover_m`, attach with `ground='hover'` and validate with `profile='hover'`. The lowest
    vertex then stays at or above the hover height, proportions are measured from the floor, and `sit` is
    optional.

  Every clip, socket and validator path then works unchanged. A test proves it: the mannequin with its legs
  deleted, at `hover_m` 0.35, passes on every clip.
- **Versioning.** The rig id plus version (`human16_v1@1.0.0`) is the hub compatibility field:
  - patch releases change metadata only;
  - minor releases add clips;
  - any bone, order or convention change is a new rig id.
