# STORY runtime/save contract 1.1.0 — READY / FROZEN

This is the additive 1.1.0 delta to [v1.0.0/GAME.md](v1.0.0/GAME.md). Both exact versions are supported; retain the original data/semantics for 1.0.0 Last Light. Full base wire shapes, hash algorithms, coordinates and ordinary action IDs remain in the archived contract. New source shapes/logic: [SPEC.md](SPEC.md).

## game.json additions

Top-level `collectible_groups` and `collectibles` are canonical ID-sorted arrays copied from source. `start.collected` is a canonical sorted unique ID array. Runtime state/save 1.1.0 has this extra state field; **do not add it to 1.0.0 artifacts**. Group counts and follower flags are derived, never independently mutable.

RoomBundle.content gains `collectibles:[Collectible in this room]`. Its `dialogues` dependency list is the union of resident-character dialogues and explicit dialogues referenced by local collectibles. Thus editing a local collectible or its vignette invalidates that room's build hash, while unrelated rooms remain byte-identical. Local referenced item dependencies continue to be copied. Global group objectives/threshold definitions remain global logic, not room-build dependencies; load new global game.json on every edit even if mesh/local bundles are cached. Other room, spec and game hashing rules are unchanged; canonical JSON has no trailing newline/timestamps.

Optional new character params (`suit`, `coat`, `dialogue_tags`) and node `role_text` are preserved in both global definitions and room dependency copies. Render node.text; E2 selects the authored role variant into this authoritative field. For Thaw, cat character IDs use their own shared cat body/rig; all residents/new arrival share the expedition body/rig and silver faceless hood. Semantic asset refs remain integration placeholders until the kits lane maps them.

## Additional action IDs

- `collect:<collectible>`: outside dialogue and only in the named room; conditions true and not found; add ID, open its optional vignette atomically. Render discovery `text`. Update group counters and follower flags from identity membership. Never duplicate a follower or counter increment.
- `recall:<collectible>`: found collectible with a dialogue, same room/outside dialogue; reopen the vignette without a second pickup. Does not require discovery conditions, but destination node guards still apply.

Every other action and WAIT-only cyclic storm/tide behavior remains as in 1.0.0. The `tide` field is retained on the wire for compatibility; Thaw supplies storm labels/state IDs instead of water labels. Choosing an ending disables further collection. Placement of spheres is an interaction guarded by spheres_found>=8; membership is not consumed or cleared when the table is filled.

Reference-engine derived view:

```
counts = {group.id: number of its collectible IDs in state.collected}
follower_flags = {c.follower_flag: c.id in state.collected
                  for c in collectibles if c.follower_flag != ""}
```

Do not insert follower flags into the ordinary mutable flags map. Save IDs, not only counts: identities preserve coat/follower/memory presentation and make migrations unambiguous.

## Save and migration 1.1.0

Save 1.0.0 fields plus `collected:[CollectibleID]`, sorted and unique, and `contract_version:"1.1.0"`. Optional timestamps remain allowed only in saves. A legal membership set still requires exact **reachable-state membership**, proved symbolically for large games. No save is accepted merely because its counts are within range.

Migration manifests in 1.1.0 add `maps.collectibles` to the prior maps. Identity is the default; explicit ID renames/drop-null entries are reported. Unknown collected IDs, collisions, implicit loss, invalid source provenance, unsupported version changes and unreachable target states reject. Missing new collectibles stay unfound; derived counters/follower flags recompute from preserved IDs. Added ordinary flags follow existing rules. Source and target must use the same supported contract version; this release does not silently upgrade 1.0.0 saves into 1.1.0 games.

## Reports and bounds

`check` retains status `proved|rejected|invalid|inconclusive`. 1.1.0 reports also expose `strategy`, exact represented `state_count`, `core_state_count`, BDD node usage when symbolic, `collectibles` (reachability + concrete witness), `groups` (required/supply/attainability), `thresholds`, and `permanently_missable` IDs/examples. Softlock/dead-end counts remain exact concrete-state counts. In symbolic mode `--max-states` bounds core nodes; `--max-bdd-nodes` independently bounds allocated BDD nodes, not total Python/cache memory. Reaching either budget produces INCONCLUSIVE, never a proof/rejection based on incomplete search.

Python/CLI defaults: auto chooses original exhaustive for 1.0.0 and exact symbolic for 1.1.0. Explicit exhaustive is for small differential tests and must never be used to brute-force Thaw merely by raising caps. Witnesses contain real action IDs/labels and can be replayed by the reference engine; formatted witnesses are also saved with acceptance receipts.

## Thaw integration IDs

Source/runtime: `games/thaw/spec.json`, `games/thaw/game.json` (compile readiness in CHECKPOINT.md).

Rooms: `pod_bay`, `workstation`, `conversation_pit`, `curved_corridor`, `snow_field`, `dome_shelter`.

Groups: `cats_found` (12), `spheres_found` (8). Cards remain ordinary inventory items. Residents share `expedition_base_v1` + `human_16`; cats share `cat_base_v1` + `cat_8`. Body/rig IDs do not change under E2. Initial endings: `thaw`, `quiet_night`. E3 fixture: `shared_glow`.

The core promise is logical, not geometric: no engine, asset, follower navigation, camera, collision or visual test is supplied by this contract or the Python checker.
