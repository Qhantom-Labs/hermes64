# RIGKIT API — rig contract `rig/1.0.0` ("rig kit")

Owner: lane NBCHARS (`wt-nbchars`, branch `noblender-chars-lane`). Published early so other builders can code
against it. Signatures and error codes below are the stable surface; the status table at the end says what is
implemented at each commit. CHARSYS, hub contributors, Blender artists and other tools build ON this contract and
must not duplicate it.

## 1. Files

| path | what |
|---|---|
| `contracts/rig/1.0.0.json` | JSON schema of `rig.json` (plus the clip-pack metadata and the validate report shapes) |
| `rigs/<rig_id>/rig.json` | the contract instance: bones, order, hierarchy, reference rest pose, conventions, joint limits, mirror pairs, seams, sockets, budgets, required clips |
| `rigs/<rig_id>/clips.glb` | the CLIP PACK: skeleton at the reference rest pose + every clip as a glTF animation, no mesh, separate from any character |
| `rigs/<rig_id>/clips.json` | clip metadata: loop flags, phases (combat hit windows, enemy telegraph/attack windows), face-atlas cells per clip, FSM map, sha256 of `clips.glb` and of each clip's key data |
| `rigs/<rig_id>/mannequin.glb` | plain mannequin (<= 400 tris, deterministic) skinned to the rig, every clip attached; the reference subject for tools and docs (human16_v1: 354 tris, quad16_v1: 248 tris) |

The human16_v1 reference body (rest skeleton, mannequin skeleton and clip-pack pose source) is the polar_pod
face-head `pp_medic`: its per-body arm solutions are the most conservative of the cast, so its clips copy onto
every published humanoid without a key leaving the validator limits (docs/RIGKIT.md).

Rigs:

| rig | used by | notes |
|---|---|---|
| `human16_v1` | all people (masked, face-head, cameo), humanoid robots (walker, brute) and **hover robots by mapping** (section 6) | 16 joints |
| `quad16_v1` | cats, dogs | separate contract |
| `dasher16_v1` | enemy `cairn_dasher` | creature contract, 16 joints |
| `warden15_v1` | enemy `reed_warden` | creature contract, 15 joints |

## 2. Conventions every rig shares (what "built on the skeleton" means)

- glTF 2.0 binary, metres, **+Y up, character faces +Z**. (Blender authoring: Z up, faces -Y, export with +Y up.)
- Exactly **one skin**. Skin `joints[i]` is the node named `rig.bones[i].name`: the joint ORDER is part of the
  contract. Armature node name `rig_<rig_id>`; skinned mesh node `kit_body` is a child of the armature node with an
  identity transform.
- **Rest pose:** every joint node has identity rotation and unit scale, translation-only offset from its parent
  (Blender: every bone points +Z, roll 0). Proportions may differ per character within `rig.json:proportions`.
- **Inverse bind matrices** are required: `IBM[i] = inverse(world rest matrix of joint i)` = a pure translation by
  `-rest_world_position[i]` (tolerance 1e-5 m).
- **Skin weights:** `JOINTS_0` (UNSIGNED_BYTE or UNSIGNED_SHORT) + `WEIGHTS_0` (FLOAT), at most **4 influences**,
  weights >= 0, sum = 1 +- 1e-3, no `JOINTS_1/WEIGHTS_1`.
- **Clips:** one glTF animation per clip, name = clip id; `STEP` interpolation; **16 keys at t = k/15 s**
  (k = 0..15, duration 1.0 s, "15 fps held poses"). Channels: `rotation` on every joint (root included) plus
  `translation` on the root (human/quad) or on the body bone (enemies: `hips` / `body`). No other channels.
  Root translation is **vertical grounding only** (x = z = 0, "no root motion"); enemies never animate the root.
- **Sockets / props:** sockets are child nodes `attach_<slot>` of joints (human: head, hand_l, hand_r, back→spine,
  belt→pelvis). Rigid props are unskinned mesh nodes `kit_acc_<slot>_<kind>` under the joint, <= 200 tris each.
  The weapon (`trail_staff`) attaches to `hand_r` with the per-character grip in the manifest.
- Material/extras conventions match the published cast (KHR_materials_unlit, baked vertex colour, `extras.n64`);
  they are checked by the existing style/GLB gates, not by the rig contract.

## 3. Python API (`adventure_maker.rigkit`, stdlib + numpy)

```python
from adventure_maker import rigkit

rigkit.list_rigs()                       # -> ['dasher16_v1', 'human16_v1', 'quad16_v1', 'warden15_v1']
rig = rigkit.load_rig('human16_v1')      # -> rigkit.Rig; schema-checked; raises rigkit.RigError
rig.id, rig.version, rig.bones, rig.parents, rig.rest   # names in joint order, {name: parent}, reference rest (glTF)

report = rigkit.validate_character(
    glb,                     # bytes | str | pathlib.Path
    rig='human16_v1',        # rig id or Rig
    *, clips=None,           # None = the rig's required clips; or an explicit list of clip names
    budget=None,             # None = rig budgets; or {'body_tris_lt': int, 'prop_tris_le': int}
    expect_sha256=None,      # manifest hash to verify (tamper check)
    profile='grounded',      # 'grounded' | 'hover' (section 6); anything else raises ValueError
    keys='all',              # 'all' = every key of every clip; or an int stride for quick checks
    tol_m=0.003)             # connectivity tolerance (3 mm)
# -> dict: {'schema': 'hermes64-rig-validate/1.0.0', 'ok': bool, 'rig': 'human16_v1@1.0.0',
#           'file_sha256': str, 'errors': [{'code', 'message', 'path'}], 'warnings': [...],
#           'checks': {name: {'ok': bool, ...metrics}}, 'metrics': {...}}

out = rigkit.attach_clips(glb, rig='human16_v1', *, clips=None, mode='copy', replace=True, ground='match',
                          guard=True)
# -> bytes: a new GLB = the input with the rig's clip pack animations written in (deterministic: same input,
#    same bytes). mode='copy' copies the pack's joint rotations verbatim (valid for any proportions because rest
#    rotations are identity); ground='match' recomputes the root/body translation per key with the numpy LBS
#    reference so the lowest vertex keeps the pack's floor clearance ('hover' adds rig node extras hover_m);
#    guard=True softens (slerp toward rest, 0.1 steps) the deepest joint of an edge that would leave the
#    validator's 0.45..1.8 limits on that key, listed in animation extras 'rigkit_guard'. Every animation carries
#    extras 'rigkit_pack' = '<rig>@<version>:<clips.glb sha256[:16]>' and the pack's own extras (n64_combat ...).
#    Raises rigkit.RigError when the file is not skinned to the rig (run validate_character first).
#    Generator-built characters keep their per-body solved clips from nbchars (parity-proven against Blender).

rep = rigkit.validate_prop(glb, rig='human16_v1', *, slot=None, budget=None, expect_sha256=None)
# -> same report shape (kind 'prop'): container, finite, unskinned + unanimated, every mesh <= rig props.tris_le,
#    slot (e.g. 'hand_r' for the trail staff) is a socket of the rig.

pos = rigkit.skin_vertices(glb, clip=None, key=0)
# -> numpy (N, 3) float64: linear-blend-skinned positions (glTF space) of every skinned primitive, concatenated in
#    file order. clip=None = rest pose. This is THE deformation reference used by every check (replaces Blender's
#    armature modifier / tools/probe_deform.py).

rigkit.lbs.joint_matrices(doc, binary, clip, key)        # world joint matrices (glTF) at one key
rigkit.lbs.skin(positions, joints, weights, joint_mats, ibms)   # vectorised LBS, (N,3)
```

CLI:

```
python3 -m adventure_maker.rigkit list
python3 -m adventure_maker.rigkit info human16_v1
python3 -m adventure_maker.rigkit validate FILE.glb [--rig ID] [--clips a,b] [--expect-sha256 HEX] [--json]
python3 -m adventure_maker.rigkit attach IN.glb OUT.glb --rig ID [--clips a,b] [--mode copy]
python3 -m adventure_maker.rigkit report --oracle PUBLISHED_DIR --out report.json [--md report.md]
python3 -m adventure_maker.rigkit build-kits [--out DIR]      # rebuild clips.glb/clips.json/mannequin.glb (dev)
```

Exit code 0 only when every file validates.

## 4. `validate_character` checks (each reported under `checks`)

| check | rejects (error code) |
|---|---|
| `container` | anything `adventure_maker.glb_validate` rejects (`container.*`, `accessor.*`, `primitive.*`, `skin.*`) |
| `finite` | NaN/Inf in any float accessor (`data.nan`) |
| `rig` | wrong joint names (`rig.bone_names`), wrong joint order (`rig.bone_order`), wrong parents (`rig.hierarchy`), non-identity rest rotation/scale (`rig.rest_rotation`), missing IBMs (`rig.ibm_missing`), IBM != inverse rest (`rig.ibm_mismatch`), proportions outside `rig.json` (`rig.proportions`) |
| `skin` | weights not summing to 1 (`skin.weights_sum`), more than 4 influences / JOINTS_1 (`skin.influences`), negative weight (`skin.negative_weight`), joint index out of range (`skin.joint_index`) |
| `clips` | missing clip (`clip.missing`), missing/extra channel (`clip.channel_missing` / `clip.extra_channel`), not STEP (`clip.interpolation`), key count != 16 (`clip.key_count`), key times != k/15 (`clip.time_mismatch`), non-unit quaternion (`clip.quat_norm`), horizontal root drift (`clip.root_motion`), rotation outside joint limits (`clip.joint_limit`, warning by default) |
| `budget` | body tris over the rig budget (`budget.body`), prop over 200 (`budget.prop`) |
| `connectivity` | a seam gap > 3 mm at neck / limb roots / attached pieces on any key of any clip (`mesh.connectivity`), measured on the numpy-LBS-skinned GLB data itself (the 4-influence weights the runtime plays) |
| `deformation` | triangle edge-length ratio outside [0.45, 1.8] on any key (`mesh.deformation`) |
| `silhouette` | grounded clips that leave the floor or sink (lowest vertex not at y=0 +- 2 mm, `mesh.silhouette.floor`); posed bounds exploding past 1.6x rest height or a vertex leaving its bone chain by > 0.5 m (`mesh.silhouette.blowup`); rest height outside the rig range (`mesh.silhouette.height`) |
| `hash` | `expect_sha256` given and different (`hash.mismatch`) |

Connectivity method: if the file carries a known generator topology (`rig_*` node extras `topology` +
`params_json`), the exact generator join table (`core/connectivity.JOINS`: buried / sector / anchored joins) is
applied to the GLB's own skinned vertices (vertices mapped back to generator parts by rest position). Otherwise
(any other builder) the generic method is used: separate mesh pieces (connected components after welding by
position) that touch or interpenetrate at rest must stay within 3 mm of each other on every key ("anchored"); a
piece that floats free at rest is reported as `mesh.connectivity.floating`.

## 5. What passing means, and limits

Passing means: the file is structurally valid glTF, is skinned to exactly this skeleton (names, order, hierarchy,
identity rest rotations, consistent inverse binds), every required clip is present with the 15 fps / 16-key STEP
convention, and on every key of every clip the mesh stays closed at its seams (3 mm), does not tear or collapse
(edge ratio) and stays on the floor. It does not mean the character is on-style (palette, shading, face style: the
style gates), or that the art is good (human review), or that a crossfade between clips looks right (only STEP
playback is validated).

## 6. Robots and the hover decision

- Walker and brute robots are humanoid: they use `human16_v1` directly.
- **Floater/hover robots map onto `human16_v1`** (no `hover12_v1`). Mapping: shell/torso -> `pelvis`+`spine`, head
  dome -> `head`, arm pods -> the arm chains, hover skirt/emitter -> `pelvis`; the six leg joints stay in the
  skeleton with zero weight. Why: every existing clip (7 base + 6 combat), the weapon socket, the validator, the
  clip pack and the runtime's actor code work unchanged; a new 12-joint contract would need its own clip pack
  authored from nothing and a second validator path for no runtime gain (16 joints is far below every engine
  skin limit). The one rule that changes is grounding: validate with `profile='hover'` — the lowest vertex must
  stay >= the declared hover height (`rig_<id>` node extras `hover_m`, error `mesh.silhouette.hover_missing` when
  absent) instead of touching the floor, and attach with `ground='hover'`; proportions are measured floor (y = 0)
  to top instead of over the mesh extent, because the hover gap stands in for the legs (report
  `checks.rig.height_basis`); walk/run read as a glide because the legs carry no vertices; `sit` is optional for
  hover characters (checked only when present). Vertices that no triangle references are ignored by every
  geometric check (glTF allows them; they are not rendered).

## 7. Status

Implemented and verified (docs/NBCHARS-RESULT.md): rig.json x4, clip packs x4, mannequins x2, validate_character,
validate_prop, attach_clips, report; the Blender-published files validate 37/37 and the human pack attaches to all
29 published characters. Single status table for both APIs: `docs/NBCHARS-API.md` section 7.
