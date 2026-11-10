# Optional presentation metadata

## Documentation convention 1.1.1, not a semantic contract upgrade

`metadata.presentation` is optional display data carried by the existing compiler. Keep `contract_version` at the story's actual version (Last Light **1.0.0**, Thaw **1.1.0**). This note does not introduce 1.1.1 wire semantics, change the checker, modify action preconditions, save extra XYZ fields, or invalidate old specs. Metadata affects content hashes; unchanged room build hashes remain local to semantic room dependencies, not an assertion that global presentation metadata did not change.

The original Last Light spec remains unchanged in `examples/last_light/spec.json` and is separately compiled/tested without presentation metadata. Showcase metadata is authored in `examples/*/presentation.json` and supplied to **scaffold** by `tools/e2e.py`, not patched into compiled output.

## Coordinates and rotations

- Runtime/glTF coordinates: metres, right-handed; +X east, +Y up, +Z south. A room spans X 0..grid width and Z 0..grid depth.
- Blender assets are exported through glTF's normal Y-up conversion; do not apply a second Z-up correction.
- All authored `rotation` arrays and `yaw` values below are **degrees**. Euler order is **YXZ** (Godot's explicit `EULER_ORDER_YXZ`). `yaw` rotates around +Y using Godot's right-handed convention.
- Positions are absolute room-space triples `[x,y,z]`; scales are dimensionless triples. These are visuals, not additional logical doors or action guards.

## Shape

```json
{
  "metadata": {
    "presentation": {
      "convention": "hermes64-presentation/1",
      "rotation_units": "degrees",
      "rotation_order": "YXZ",
      "ending_titles": {"quiet_night": "Quiet Night"},
      "rooms": {
        "pod_bay": {
          "camera": "wide",
          "cameras": [{"id":"wide","position":[14,9.2,17],"look_at":[7,0.8,5],"fov":62}],
          "props": {"warmth_lamp":{"position":[7,0,7],"rotation":[0,0,0],"scale":[1,1,1]}},
          "characters": {"tavi":{"position":[5,0,4],"yaw":180}},
          "collectibles": {"sphere_01":{"position":[5,0.8,5]}},
          "interactions": {"interact:examine_lamp":{"position":[7,1,7]}},
          "pieces": [{"asset":"furn.bed","position":[9,0,3],"scale":[1.2,1.1,1.1],"yaw":0}]
        }
      }
    }
  }
}
```

`convention`, `rotation_units` and `rotation_order` describe this convention, not arbitrary parser switches. Other units/orders are unsupported. Use valid typed values; this display convention is not a new STORY validation module.

## Selection and defaults

1. Room presentation is looked up by exact room ID. Without it, story `props.position/rotation`, `rooms.cameras` and collectible/character anchors continue to work.
2. Optional `cameras` replaces the room camera array. `camera` selects its exact initial anchor ID; otherwise the first anchor is used. An empty array gets a deterministic oblique default based on grid dimensions. FOV defaults to 52 degrees. Camera C still cycles; the controller preserves held direction across cuts.
3. `props` overrides position, rotation or scale by exact prop ID. Missing fields retain story position/rotation and scale 1. A character-bound collectible has one actor, not a duplicate prop.
4. `characters` overrides position/yaw. Otherwise use `metadata.collectible_prop_ids` anchors, then deterministic spaced room positions. Found cats become one cosmetic follower each; a save stores collected IDs, not duplicate follower state.
5. `collectibles` overrides action-target positions; unanchored pickup visuals use them. For a collectible already bound to a prop/character, move that prop/character too; the target override does not detach the bound visual.
6. `interactions` supplies positions keyed by complete action ID, e.g. `interact:foo`. Defaults resolve known prop, character and door targets. Position is advisory; legal actions remain those of the story engine.
7. `ending_titles` supplies display titles. Fallback is the ending ID with underscores replaced and capitalization; ending conditions/text are untouched.
8. `pieces` adds decorative built GLBs through explicit pack bindings. No executable or arbitrary file path is accepted as an asset key.
9. `exterior:true` removes the default cutaway walls. `floor` chooses an asset key (default `_floor`, empty string disables visual floor); `floor_scale` defaults to room width/3, 1, depth/3. Collision floor and grid bounds remain independent. Theme-specific staging lives in example/pack data, never an `if game == Thaw` runtime branch.

## Default rendering and limits

Any compiled layout can use default cutaway floor/wall GLBs and its existing camera anchors without this metadata. Unknown refs are listed in `missing_assets`; unbound props use a conspicuous diagnostic proxy and unbound characters use the legacy static proxy. They are not passed as resolved assets. Existing exact bindings are hash-checked before loading.

Metal/Mobile is the desktop default. For a future web build the candidate renderer is Compatibility (`--rendering-method gl_compatibility`); web export/templates and current assembled Compatibility parity are **not verified**. The LOOK shader explicitly handles display-space sRGB8 colours differently from generic glTF materials. See `ASSET-BINDINGS.md`.
