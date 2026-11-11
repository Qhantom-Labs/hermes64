# Bundled examples: every game has a bound player character

The owner's Windows run rebuilt the bundled **Reedland Relay: Arena** example (`game:relay_combat`,
`examples/gameplay-combat-arena`) and it had **no player character**; his PC agent added Relay's courier by hand.

## Cause

Four gameplay-module examples are data-only fixture exports (`adventure_modules/examples.py` writes them from the
test fixture `tests_story/test_modules_fixtures.fixture`, which has `characters: []` and empty `metadata`):
`gameplay-combat-arena`, `gameplay-mixed`, `gameplay-outdoor-regions`, `gameplay-timed-course`. The runtime takes the
player's body from `runtime.characters[metadata.protagonist]` (`runtime/godot/view/presenter.gd`); with no
protagonist the resolver gets `{}` and the presenter falls back to a generic placeholder (`room_root.person`). The
other bundled examples (Thaw, Last Light, Puzzle Hall, the kit demos, the Reedland runtime/regions games) already
bind a protagonist.

## Fix (data only, no plugin code)

`tools/bind_example_cast.py` (repository tool, idempotent, `--check` mode) applies the binding the runtime example
`examples/gameplay-reedland-runtime` already uses: the Reedland Relay courier Iri (`runner`: bundled
`human_base_v1` body on the `human_16` rig, `travel_coat`) appended to `characters`, `metadata.protagonist = "runner"`,
and `runner` in every room's `character_ids`. Rooms, gameplay modules, dialogue, items and endings are unchanged.
`game.json`, `proof.json`, `save.json` are rebuilt with the same functions `tests/test_modules_artifacts.py` checks.
Proof status and state counts are unchanged (combat 5 states conditional, mixed 35 conditional, regions 24 proved,
course 5 conditional; 0 dead ends each). The fixture in `tests_story/` is left alone (it is test data for the module
tools, which do not need a cast).

## Re-pin (hashes changed; legacy hashes kept as history)

| Example | old spec_hash | new spec_hash | old game_hash | new game_hash | proof |
|---|---|---|---|---|---|
| gameplay-combat-arena | `980d7a963cb9ef68` | `6eabe90ace9923ea` | `db5985176feb7c2f` | `0c72a34870f73319` | conditional |
| gameplay-mixed | `0a7cf2ca0ac3d331` | `06daffc93bb740b2` | `a2762c3f9ef3ed01` | `1cbc05862a86e728` | conditional |
| gameplay-outdoor-regions | `bc2c30517a2207fe` | `b7959277bfa34bca` | `1685493a76527f38` | `98a1fa70e3adf496` | proved |
| gameplay-timed-course | `7d7ea9547e3f30f8` | `cc4f9727043bc09d` | `c8eb54dfcb6f4a90` | `7cb70d86beffec17` | conditional |

The old hashes stay in `contracts/gameplay/evidence/` (`examples.json`, authoring and regression receipts): those are
historical receipts of the original fixture export and are not rewritten. Nothing in tests, the hub index or code
pinned the old hashes; the generated catalog (`catalog/catalog.json`) was rebuilt with `python3 -B -m tools.catalog
build` (4 spec sha256/byte rows; the bundled body's `used_by` now lists the four games) and `catalog check` is OK.
Thaw, Last Light, Puzzle Hall and the Reedland runtime/regions examples are byte-unchanged.

## Guard

`tests/test_example_cast.py`: every `examples/*/spec.json` (and the two sci-fi kit demo specs) names a protagonist
that is a cast member with `body_id` and `base_rig_id` and is placed in the start room; known-bad controls (the
pre-fix shape, an unbound id, a missing body, an unplaced protagonist) each fail; every catalog game outside
`projects/` has a person/creature asset that lists it in `used_by`; `bind_example_cast --check` is clean.

## Measured on this Mac (not Windows)

`tools.audit_examples --games relay_combat` before and after: proof `conditional`, style audit FAIL 0/100 both times
with the same errors (camera, contrast, cuboid_placeholder, fog, void: the fixture has no presentation or style pack;
unchanged by this fix). Contact sheets: `evidence/win2/relay_combat-before.png` shows a small green placeholder at the
back of the arena, `relay_combat-after.png` a dark two-legged figure in the same spot. At 160 px the figure is too
small to confirm the body visually; how it looks is for the owner to judge (test sheet v2, step C).
