# Optional Blender: static kits and reference packs

Status: **opt-in Python path; not promoted to the default**. The strict parity gate is not all green. See [NOBLENDER-PARITY.md](NOBLENDER-PARITY.md) and the retained failures, not just the successful renders.

## What works without Blender

| Feature | Requirement | Limits |
| --- | --- | --- |
| Story authoring, pack data, reading verified bundled assets | Python 3.9+ standard library | Not a rendering or art approval |
| New static kit GLBs and style-material/texture builds | Python 3.9+ and numpy in the selected `python_path`; `builder=python` or `auto` | Original source validators remain mandatory; some sampled parameter combinations fail |
| GLB binary container writer | Standard library only | `kits/core/glbwrite.py`, independently tested with `python -S` |
| Reference PNG measurement/drafting | Python + numpy | Noninterlaced 8-bit PNG uses zlib; grayscale, gray-alpha, RGB, RGBA, indexed and tRNS handled |
| JPEG, interlaced or sub-8-bit PNG reference decode | Also Pillow in `python_path` | No automatic install; **16-bit PNG is refused** rather than silently quantized; EXIF orientation/ICC conversion is not applied |
| Runtime proof, play, replay, screenshots, game export | Existing Godot; configure `godot_path` | Graphical renderer needed for actual captures; standalone executable export also needs export templates |
| Draft reference proof without Godot | Python + numpy software preview | Explicit `software_lower_fidelity` label; vertex colours only, no runtime textures, chrome, fog or shadows; cannot certify visual parity |
| Verified prebuilt cast | Existing bundled verified files | No Blender or generator required to reuse; rendering needs Godot |
| New character bodies/rigs/animation exports | Blender; configure `blender_path` | Not implemented by the static writer; character sources remain frozen |
| Legacy Cycles previews/manifest tooling | Blender | The new refpack proof is not a Cycles clone |

The plugin host interpreter is not necessarily the selected child interpreter. Runner deliberately sets `PYTHONNOUSERSITE=1`; a numpy installation in a user's site-packages can therefore be available in a terminal but unavailable to the plugin. Point `python_path` at an **existing virtualenv entrypoint containing numpy**. Do not replace its `bin/python` symlink with the resolved base executable. This lane fixes that discovery bug and tests the actual child through Runner. Nothing is installed, downloaded, enabled or added to a profile.

## Using the opt-in path

Set the existing plugin setting `builder` to `python` (or `auto`) and `python_path` to an existing supported interpreter. `auto` chooses Python for static assets; armatures select Blender. Explicit Python armatures fail with a `builder`/`blender_path` remedy. Missing executables name the setting to change.

Local CLI examples, from the repository root:

```sh
python3 -B kits/build.py --builder python --id furn.table --pack forest_village --out evidence/my-table.glb
python3 -B -m adventure_maker.doctor --table
python3 -B -m refpack --refs /absolute/reference.png --notes /absolute/notes.json --pack-id my_draft --project /existing/project
```

Use the chosen virtualenv's Python rather than `python3` if that command lacks numpy. Direct CLI tools are developer interfaces; the registered plugin continues to use its existing Runner sandbox. Refpack and doctor registration instructions for Main are in [NOBLENDER-INTEGRATION.md](NOBLENDER-INTEGRATION.md).

## Static GLB design and compatibility

The writer consumes the existing `Asset`, `Node`, and `Mesh` output. It reuses pack materials, `bake.corner_uvs`, light-ramp baking, `texgen.make_texture`, `alpha_mask`, and **exact PNG bytes from `png.encode`**. It does not replace generators or regenerate the shipped libraries.

- Deterministic JSON key order, node ordering, attribute splitting, binary packing and four-byte view/chunk alignment. No timestamps or output paths in GLB bytes. Accessor bounds describe the stored float32 values.
- Proper rotation `(x, y, z) -> (x, z, -y)`, UV `v -> 1-v`, retained winding and world-pivot-to-relative-parent translation. Cycle/unknown-parent/duplicate-name checks precede output.
- POSITION, NORMAL, TEXCOORD_0 and normalized unsigned-byte COLOR_0. Display-space colours are deliberately nonstandard glTF, exactly as the runtime adapter expects. `asset.extras.vertex_color_encoding = "srgb8"` makes the existing adapter idempotent; palette validation now respects that marker.
- Runtime-dependent material names and `extras.n64` keys (`kind`, `role`, `pack`, `tile_m`, `texture`, `env`, `tint`, `scroll`, encoding), embedded images, texture bindings, alpha-mask/double-sided semantics and `KHR_materials_unlit` are represented. Generator metadata remains in the sidecar, as with Blender; it is not invented as glTF extras.
- Deterministic ear clipping and visible hole bridges replace the missing-mathutils path. Invalid/crossing/degenerate polygons fail closed. The Blender reference retains its original tessellator, exposing real wall-subdivision differences instead of making both sides share the answer.
- Export shading normals are separate from the bake's welded, angle-limited lighting normals. Smooth sides exclude flat caps. The Blender exporter rounds loop normals to four decimal places and normalizes float32 before splitting; the Python path follows that representation. Residual normal/vertex-split differences remain gated, not excused by a wider tolerance.
- Numpy topology fallback uses the same welded-island/shared-vertex policy as the original BVH gate. Positive coplanar overlap and proper plane crossings are intersections; edge/point-only contacts are not. Both known-bad crossing controls and contact regressions are tested. Cross-validating retained Python GLBs in Blender exposed and fixed false-positive contact reports.
- Cache identities include the selected builder and encoding version for both individual requests and batched room kits. Builder aliases that select the same backend share that backend's cache, not a Blender cache.

The current core registry intentionally excludes `gen_char`, `charrig` and `chartex`. Main must pass `needs_armature=True` when wiring any future custom-character caller to `builders.select`; this lane does not invent a new character-generation tool.

## Reference-to-pack

The baseline did not contain `refpack`; this lane imports its source/guard/test snapshot from the read-only neighboring `lane-refpack` directory. This was a directory snapshot, not a Git repository with a retrievable commit. Main should merge the portable changes over any newer refpack source, not overwrite newer work wholesale.

The public `pack_from_refs` workflow now uses Python measurement and proof workers. `blender` is retained only as an ignored compatibility argument. The Blender measurement module remains as a test oracle; the Blender proof module supplies pure validation/layout/sheet helpers but its Blender setup/render functions are never called by the Python workflow.

PNG decoding is bounded by header dimensions and inflated byte length. Existing file-size/format/CRC/dimension, symlink, write-location, foreign-pack, notes-schema and zero-variance guards remain. Measurements use the unchanged `measure_np` algorithm. Byte-to-float conversion uses **float32 multiplication by the float32 reciprocal of 255**: direct division differed from Blender by one ULP and changed one rounded highlight statistic. The fixed decoder matches freshly rerun Blender PNG and JPEG measurements exactly in the measured cases. The older retained smoke statistics differ from both fresh measurements; those differences are retained separately and not called a pass.

Proofs assemble the same lounge layout in Python, use the same physical cameras transformed to Y-up, load GLBs with shipped `view/assets.gd`, shade with shipped `look/n64_mat.gd`/N64 shader, and capture a SubViewport using the same readback mechanism as `presenter.capture_low`. This is a static proof harness, **not a complete gameplay-camera or Cycles acceptance test**. UV scroll time is frozen for repeatability. No renderer is installed; a failed installed Godot is reported instead of silently producing software evidence. If Godot is absent, the labelled software preview is allowed only for draft review.

`pack.json.refpack.status` and provenance stay `draft_unapproved`; successful API status `draft` never means approved. References remain private study inputs; proof thumbnails are not distributable pack assets. The proof smoke exercised both Godot and no-Godot paths with a deliberately missing Blender path.

## Later lane: pure-Python skinned characters (design only)

Do not route characters through this static writer. A later implementation must reproduce:

1. The existing bone names, hierarchy, rest transforms, skeleton/root node, attachment conventions, +Z-to-Y conversion and inverse bind MAT4 accessors; validate that each joint's bind/rest composition is identity.
2. JOINTS_0 unsigned indices, WEIGHTS_0 normalized weights, `skins.joints`, skeleton root, inverseBindMatrices and mesh-node skin bindings; bind poses and weight sums must match the character contract.
3. Every named clip and track, root motion policy, local translations/quaternions/scales, animation samplers/channels, strictly increasing frame times and **15 fps STEP interpolation**, without linear interpolation or sampling drift.
4. Existing character material/atlas and cast-selector metadata, attachment points, deformation/stretch validators, deterministic bytes and character-specific cache identity.
5. Paired Blender/Godot rest-pose and motion captures for all supported rigs/clips plus known-bad bind/weight/joint/time controls. Prebuilt cast hashes must remain unchanged.

Estimate for one experienced engineer: **8–13 working days** (2–3 for skin/joint representation, 2–3 for clip serialization, 2–4 for deformation/runtime parity, 2–3 for integration and failure controls), conditional on the current generator retaining accessible numeric rig/action data. If it only exposes bpy-side state, data-model extraction is an additional scoped task; this estimate is not a delivery promise.

## Not verified / limits

Strict all-case parity and default promotion are **not achieved**. Render parity covers only the fixed sampled subset. Other machines, GPUs, operating systems (especially Windows), Blender/Godot versions, numpy versions beyond the local runs, all PNG/JPEG encodings, custom-character generation, game exports on other platforms and unsampled visual combinations are not verified. Software preview is not visual parity. No golden was blessed or approved, no library/cast was rewritten, no remote was pushed, and no catalog/public release was made.
