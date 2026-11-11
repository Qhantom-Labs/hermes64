# Proposed patch (not applied): a consumer for the `emblem_jacket` sheet

Lane L3 was not allowed to edit character files. The `emblem_jacket` slot is declared in the cyber packs' `slots.json`
(a 32x32 sheet with a transparent `clear` tone, consumer `character_emblem`), and the build bakes it when a value is
given. Nothing shows it yet.

Data the build already provides (theme.json):

```json
"texture_slots": {"sheets": {"emblem_jacket": {"path": "res://media/<sha>.png", "sha256": "<sha>", "consumer": "character_emblem"}}}
```

Smallest consumer, for the characters lane (`runtime/godot/actors/character.gd` or the presenter, after a character
visual is loaded):

1. Read the sheet once with `preload("res://view/slots.gd").load_png(path, sha256)`. It checks the hash and caches
   the texture.
2. For characters whose binding opts in (a per-character `emblem: {"bone": "spine_2", "offset": [0, 0.05, -0.12],
   "size_m": 0.18, "faces": "back"}` row in the cast/bindings data, so nothing is hard-coded to one character):
   attach a `MeshInstance3D` with a `QuadMesh` of `size_m` to a `BoneAttachment3D` on that bone. Its material is the
   N64 shader through `Mat.bind_external(m, tex)` with `alpha_cut = 0.5`, so the clear tone is cut out with no
   blending.
3. With no sheet (no value, or a neutral export) attach nothing.

Tests to add with it:
- a probe that the quad exists only when the sheet exists;
- the triangle cost is +2 per opted-in character;
- a known-bad wrong sha256 attaches nothing.

The alternative, painting the emblem into the character's own texture cell, needs the character texture atlas
layout from CHARS3 and is not proposed here.
