# STORY source contract 1.0.0

Status: READY / FROZEN for initial consumer implementation. JSON only, UTF-8. This document and GAME.md are the wire contract. Changes require CHANGELOG.md; breaking changes require a new major version. Implementation/evidence readiness is tracked separately in ../CHECKPOINT.md.

## Conventions

Required fields below are literal; no implicit defaults. Additional fields are rejected except the free-form `metadata` object. IDs match `[a-z][a-z0-9_]*`, unique within their collection. References must exist. Numbers must be finite. Objects are maps; every entity collection is an array sorted by `id` during compilation; choice, effect, tide-state and vector arrays retain order. All optional presentation enrichment belongs in metadata, not executable expressions. No scripts, eval, randomness, clocks or external URLs in logic. Paths are relative asset references, not promises that assets exist.

```
Spec = {
  contract_version: "1.0.0", id: ID, title: string, description: string,
  metadata: object,
  start: {location: RoomID, inventory: [ItemID], flags: {FlagID: bool},
          dialogue: {DialogueID: NodeID | ""}, tide: {state: TideID, tick: int}},
  rooms: [Room], characters: [Character], items: [Item], flags: [Flag],
  interactions: [Interaction], dialogues: [Dialogue],
  tide: Tide, quests: [Quest], endings: [Ending]
}
Room = {
  id, name: string, description: string, grid_size: [positive int, positive int],
  kit_refs: [string],
  doors: [{id, wall: "north"|"east"|"south"|"west", position: nonnegative int,
           to_room: RoomID, to_door: DoorID, label: string, conditions: [Condition]}],
  cameras: [{id, position: [number,number,number], look_at: [number,number,number]}],
  props: [{id, asset: string, position: [number,number,number], rotation: [number,number,number]}],
  character_ids: [CharacterID]
}
Character = {id, name: string, role: ID, body_id: string, base_rig_id: string,
  params: {costume: string, colour: string, voice_tags: [string]},
  role_profiles: {RoleID: {costume: string, colour: string, voice_tags: [string]}}}
Item = {id, name: string, description: string, asset: string}
Flag = {id, initial: bool, description: string}
Interaction = {id, room: RoomID, kind: "examine"|"take"|"use"|"talk",
  target: string, label: string, text: string, conditions: [Condition], effects: [Effect]}
Dialogue = {id, character: CharacterID, start_node: NodeID,
  nodes: [{id, text: string, conditions: [Condition],
           choices: [{id, text: string, conditions: [Condition], effects: [Effect],
                      next: NodeID | ""}]}]}
Tide = {id, states: [{id, label: string, duration: positive int}],
        wait_label: string, wait_text: string}
Quest = {id, title: string, description: string, conditions: [Condition]}
Ending = {id, conditions: [Condition], text: string}
```

`start.flags` must include exactly all flags and agree with `Flag.initial`; `start.dialogue` includes exactly all dialogues, normally empty cursors. At most one cursor can be active. Tide state must exist; tick is 0 through duration-1. Inventory has unique IDs. `rooms[].doors` describe both entrances and exits: reciprocal endpoints are mandatory (A.to=B and B.to=A). Door positions are tile offsets 0..width-1 for north/south, 0..depth-1 for east/west. Collision duplicates on the same wall/offset are invalid. Room coordinates: X east, Y up, Z south; one tile = one runtime unit; north Z=0, south Z=depth, west X=0, east X=width. Door centers are offset+0.5. Cameras/props use local coordinates; no geometric walkability proof is claimed.

## Executable conditions (AND lists; [] is true)

Exactly one form per object, with exact keys:

- `{ "flag": FlagID, "equals": bool }`
- `{ "item": ItemID, "present": bool }`
- `{ "location": RoomID }`
- `{ "tide": TideID }`
- `{ "role": CharacterID, "equals": RoleID }`
- `{ "dialogue": DialogueID, "node": NodeID | "" }`

Role checks read the compiled character role (not mutable state). Preconditions never change state. No implicit OR or negative inference. Node conditions and choice conditions both apply to a dialogue choice.

## Effects (ordered; exactly one form per object)

- `{ "flag": FlagID, "value": bool }`
- `{ "give": ItemID }` (inventory is a set; idempotent)
- `{ "take": ItemID }` (requires item already present; otherwise action disabled)
- `{ "dialogue": DialogueID, "node": NodeID | "" }`
- `{ "location": RoomID }`
- `{ "tide": TideID }` (tick resets to 0)

No item-quantity or floating-time state. Effects execute atomically: missing take prerequisites disable the entire action, not partial mutation. Taking an item is represented by a take-kind interaction with `give`, usually guarded by `present:false` plus an acquired flag if the item can later be consumed. Interactions and room travel are disabled during an active dialogue. Starting dialogue requires that target node's conditions hold in the resulting state. Choices apply effects, then assign the current graph cursor to `next`; `next:""` closes it. The destination node's conditions must hold in the resulting state. Every nonterminal active dialogue also offers `cancel:<dialogue>` (clears cursor with no other change). Wait is always available, including dialogue, unless terminal. Self-loop actions are legal.

## Timers, reachability and terminals

Time is explicit deterministic turn time, not real-time. Only `wait` advances the tide tick. After `duration` waits it advances to the next state in declared order, wrapping cyclically. All other actions pause tide. A runtime may present a wait button/animation but MUST NOT advance tide in the background. Terminal detection runs on the initial state and after every transition. Exactly one matching ending ends play, disables every action and displays its text. Multiple matching endings are a contract logic error detected by the checker. Quest completion is a derived condition, not hidden state.

## Edit and migration API

Pure Python functions do not write files or mutate arguments. `move_entrance(spec, room, door, wall, position)`, `change_role(spec, character, role)`, and `add_ending(spec, id, conditions, text, trigger)` return `{spec, game, diff, regression, migration}`. `trigger` is `{id, room, kind, target, label, text, conditions, effects}`. E3 creates a fresh `ending_<id>` boolean flag, appends it to trigger effects, and adds it to ending conditions. Existing IDs cannot be overwritten. E2 selects an existing role profile and updates only role plus params; matching role conditions throughout logic are rewritten old->new (dialogue, quests, interactions, exits, endings). Body, rig and unrelated values remain unchanged. Role-variant authored text can be selected by role-gated nodes; E2 does not fabricate dialogue text. E1 changes only the named endpoint's wall/position; IDs/topology and the opposite endpoint remain stable.

`diff` is a sorted list of `{path, before, after}` (JSON Pointer; ID-keyed entity addressing); `regression` reports solvability, old/new room hashes, changed/unchanged room IDs and byte identity of unchanged room bundles. `migration` names source/target spec and game hashes and explicit identity maps for rooms/items/flags/dialogues/nodes/tides; E1/E2/E3 preserve existing IDs. E3 adds the new flag at its initial value. CLI writes migrated artifacts and reports; Python API remains pure. Edits producing unsolvable games return a failed regression report, never a false PASS.

Save and migration wire schema is defined in GAME.md. Runtime/action IDs and hashes are also defined there.
