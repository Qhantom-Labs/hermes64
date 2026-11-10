# STORY runtime contract 1.0.0

Status: READY / FROZEN. Consumer: Godot runtime lane. Producer: pure Python STORY compiler. Read SPEC.md for complete entity shapes and transition rules. JSON only; IDs/references are stable strings, not array indices. No asset or engine execution has been verified by this contract publication.

## game.json

```
{
  "contract_version": "1.0.0",
  "id": "last_light", "title": "The Last Light", "description": "...",
  "metadata": {},
  "spec_hash": "64 lowercase SHA-256 hex",
  "game_hash": "64 lowercase SHA-256 hex",
  "start": {"location":"fog_street", "inventory":[], "flags":{},
            "dialogue":{}, "tide":{"state":"low","tick":0}},
  "rooms": [RoomBundle],
  "characters": [Character], "items": [Item], "flags": [Flag],
  "interactions": [Interaction], "dialogues": [Dialogue],
  "tide": Tide, "quests": [Quest], "endings": [Ending]
}
RoomBundle = {
  ...all Room fields from SPEC.md,
  "build_hash": "64 lowercase SHA-256 hex",
  "content": {
    "characters": [Character placed in this room],
    "items": [Item referenced by this room's interactions or local dialogue],
    "interactions": [Interaction whose room is this room],
    "dialogues": [Dialogue for a character placed in this room]
  }
}
```

Top-level entities are authoritative for logic; room content is an identical dependency copy for incremental building, not a second state store. Collections sort by ID; entities referenced in room content are sorted by ID. Room content includes item definitions referenced in conditions/effects and take targets; local dialogues are included through resident characters. Room build hashes cover only the complete RoomBundle excluding its own `build_hash`, NOT global spec/game hashes, ending text, unrelated room data, global flag defaults, quest data or tide schedule. These global values affect gameplay and the game hash but need not rebuild meshes/local content. A room-only layout change therefore changes exactly that room's hash. Editing a local character changes all and only rooms placing that character or using its referenced dialogue content. Runtime must load the entire new game.json for logic edits, even when a room asset bundle remains cached.

Canonical JSON: `json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))` encoded UTF-8, with NO trailing newline. Finite numbers only; negative zero follows Python JSON spelling. Entity ordering normalization precedes hashing. `spec_hash = sha256(canonical(normalized source spec))`. `room.build_hash = sha256(canonical(room without build_hash))`. `game_hash = sha256(canonical(game without game_hash))` (includes spec_hash and room hashes). File byte SHA-256 differs from self-excluded game_hash; tooling reports both explicitly. Compiler must reject unknown contract versions. Runtime should reject unsupported majors; exact 1.0.0 supported here.

## Runtime execution

Initial state is a deep copy of `start`. Evaluate condition arrays as AND, exactly as SPEC.md. Available action IDs:

- `move:<room>:<door>`; conditions on this endpoint apply, result location=to_room.
- `interact:<interaction>`; current room and conditions must match, apply effects atomically.
- `choose:<dialogue>:<node>:<choice>`; current cursor, node and choice conditions must match; effects then cursor=next.
- `cancel:<dialogue>`; clear the active cursor.
- `wait`; advance tide by one tick only (cyclic duration schedule).

All action IDs are deterministic. No movement/interactions while in dialogue. Wait and cancel remain available to prevent UI lock-in. At most one active graph. Endings are checked before allowing actions and after effects. If two match, report an ambiguous terminal; do not silently select one. UI displays interaction text, node/choice text, tide labels and ending text verbatim. Character `body_id` + `base_rig_id` are asset identities and must not change for an E2 costume/role edit. `params` describes cosmetic role-linked parts only. Asset paths are placeholders until lane-kits integration supplies files; IDs can map to a manifest in the consumer.

The checker explores all reachable finite states, records shortest action witnesses for each ending, and reverse-marks states that can reach ANY ending. Reachable nonterminal states outside that reverse set are softlocks, including nonterminal cycles. Dead ends are nonterminal states with no state-changing successor; wait cycles mean a softlock need not be a dead end. A configured state cap produces INCONCLUSIVE (never a proof). Missing item/flag producers and unreachable condition values are diagnostics, not a substitute for graph search. Proof is existential reachability of each ending plus absence of reachable softlocks, under this discrete abstract model; geometry, input UX, wall-clock pacing and rendering are not proved.

## Save 1.0.0 and migration

```
Save = {
  "contract_version": "1.0.0",
  "spec_hash": "...", "game_hash": "...",
  "location": RoomID, "inventory": [ItemID], "flags": {FlagID: bool},
  "dialogue": {DialogueID: NodeID | ""},
  "tide": {"state": TideID, "tick": nonnegative int},
  "timestamps": {}  // optional opaque JSON; the only timestamp allowance
}
```

Save inventory sorted/unique; flags/dialogue keys exact. Validate references, cursor exclusivity, types, tide tick and actual reachable-state membership (terminal saves allowed). This prevents invented inventory/flag combinations passing merely because their IDs exist. Identical spec/game hashes: load AS_IS only if valid and reachable. Changed hashes: require exact source game (or an explicit source->target migration manifest) and full validation. In v1 CLI requires source game; unknown provenance fails closed. Migration never silently discards inventory, progress, locations or dialogue. Identity-preserving edits rebind hashes, preserve state and add new flags/dialogues at their defaults, reporting each addition. Changes to initial defaults of existing flags do NOT overwrite existing progress.

Migration response: `{status:"as_is"|"migrated"|"rejected", save:Save|null, report:[{action, path, before, after, reason}], reason:string}`. Explicit maps may rename rooms, items, flags, dialogues, dialogue node IDs, tide states; null map entries explicitly drop items/flags/dialogue graphs only. A location or active dialogue node cannot be silently dropped. Map collisions reject. A target state must be valid and reachable; otherwise reject, never reset to start. Missing/unsupported versions, corrupt hashes, mismatched source, unknown IDs and unreachable target state reject with clear reasons. Timestamps are preserved but excluded from game/spec hashing.

A migration manifest returned by edits is `{contract_version, from_spec_hash, from_game_hash, to_spec_hash, to_game_hash, maps:{rooms,items,flags,dialogues,nodes,tides}}`. `nodes` keys are `dialogue_id:node_id`, values are destination node IDs. Missing entries mean identity; supplied manifests must match both source and target fingerprints. Semantic change without any state remap still reports hash rebinding explicitly. Gameplay migration is not a persistent-world/geometry position remap: save position is RoomID, never XYZ.

## Initial integration targets

Source: `games/last_light/spec.json`. Generated runtime: `games/last_light/game.json` (not present until compile checkpoint). Core rooms: `fog_street`, `boathouse`, `keepers_cottage`, `lamp_room`. Items: `oil`, `clockwork_gear`, `lens_crystal`. Characters: `mara`, `ferryman`. Shared rig ID: `human_16`. Initial endings: `relight`, `leave_dark`; an E3 fixture adds `keep_watch`. The tool is `python3 -m story <compile|check|edit|migrate>`. See CLI `--help` and final README/RESULT for exact arguments and verified output.
