# STORY source contract 1.1.0 — READY / FROZEN

Published before wave-1b implementation. Consumer lanes may build against this document now; CHECKPOINT.md separately tracks implementation readiness. **1.0.0 remains supported without changed semantics or changed Last Light bytes.** Its complete contract is preserved at [v1.0.0/SPEC.md](v1.0.0/SPEC.md); all its definitions apply to 1.1.0 except the explicit additive extensions below. Unknown versions reject. No silent upgrades. JSON only, Python 3.9 stdlib producer.

## New required 1.1.0 fields

```
Spec += {
  contract_version: "1.1.0",
  collectible_groups: [Group],
  collectibles: [Collectible]
}
start += {collected: [CollectibleID]}  // sorted unique identity set
Group = {id: ID, name: string, kind: ID, required: nonnegative int}
Collectible = {
  id: ID, group: GroupID, room: RoomID, name: string,
  label: string, text: string, asset: relative asset reference,
  character: CharacterID | "", dialogue: DialogueID | "",
  follower_flag: ID | "", conditions: [Condition]
}
```

All fields are required; no other keys. Group/collectible entity arrays canonicalize by ID. `required` is a checker objective (e.g. cats_found=12), not an implicit ending guard. It may exceed supply in a structurally valid spec, but the checker MUST reject that impossible objective with an explanation. Every collectible must be reachable, even when not needed by an ending. Collection is monotone: an ID can only enter `collected`, never leave during gameplay. There is no count stored independently: group count is `len(collected ∩ group_members)`; identities remain available for coats, followers, memories and saves. No quantities, ordering or duplicate credit.

`follower_flag` is optional via the empty string, otherwise globally unique and disjoint from declared mutable `flags`. Its Boolean value is **derived** from membership of that collectible. It is exposed as `follower_flags` by the runtime/reference engine, not stored again in the mutable flag map or counted as a second state dimension. Use `{"collected":"cat_purl"}` to test it in logic. Cats may reference ordinary character assets and a vignette dialogue. `text` is the discovery/memory text; dialogue is additionally opened immediately on discovery when nonempty.

## New positive conditions

In every existing condition array, additionally allow exactly:

- `{"collected": CollectibleID}` — identity found.
- `{"group": GroupID, "at_least": nonnegative int}` — derived count threshold.

No negative collectible predicates, removal/consume effects or mutable counters. Existing item/flag predicates retain 1.0.0 behavior (including false tests). Existing inventory is separate from collectibles: keycards can remain ordinary finite inventory items. All new guards are ANDed with existing guards. Thresholds above supply are logic failures, not reasons to raise a search cap.

## Collection actions and dialogue

The runtime offers `collect:<id>` only in the collectible's room, outside dialogue, while the ID is absent, and when its conditions hold. Atomically add its ID and, if declared, enter the referenced dialogue's `start_node`. Target node conditions must hold in the resulting state; otherwise the action is disabled with **no** collection. Effects of the vignette's choices follow the ordinary dialogue contract; they do not secretly mutate collectibles. `cancel:<dialogue>` remains available.

For a found collectible with a dialogue, offer `recall:<id>` in the same room outside dialogue. It opens the same start node without adding another ID and without rechecking discovery conditions; target node conditions must still hold. This lets the player reread resident vignettes. Collections and recall pause the storm/tide clock, like all non-WAIT actions. Ends still terminate immediately. `collect:<id>` without a dialogue leaves the core state unchanged except collected membership.

## Authored character/suit extensions (1.1.0 only)

The old `params={costume,colour,voice_tags}` remains legal. Optional extra keys are `coat: ID` (cats), `dialogue_tags:[string]`, and `suit:Suit`. Role profiles use exactly the same params shape.

```
Suit = {
  hood: string, vest_pattern: ID, vest_colour: string,
  sweater_colour: string, sweater_wear: ID,
  trouser_colour: string, trouser_wear: ID, trouser_volume: positive number,
  gloves: ID, boots: ID, accessories: [string]
}
```

Hood is a nonempty theme-authored string, not a core enum. Per the shared core/theme addendum, Thaw's `silver_faceless` and cast/kit presets live in `packs/polar_pod/`; the core also accepts other packs' hood materials/styles. This is an explicit additive relaxation of the pre-implementation 1.1.0 draft, recorded in CHANGELOG.md; no existing 1.1.0 input changes meaning.

Thaw residents share body_id and base_rig_id and the same faceless silver hood. All identification comes from suit details/accessories; no faces or body-topology edits. Optional `role_text:{RoleID:string}` on a dialogue node declares authored role-linked text. E2, for the edited dialogue's character, selects `role_text[new_role]` into `node.text` when present, in addition to rewriting old-role conditions and selecting the new role profile. It never fabricates text or changes body/rig IDs. 1.0.0 E2 is unchanged.

## Exact checker strategy, not an unsafe counter merge

Default 1.1.0 analysis uses a **symbolic finite-state fixed point**: enumerate only the non-collectible core `(location, inventory, mutable flags, dialogue cursors, storm state/tick)`, and represent the exact set of collectible-identity subsets at each core by a reduced ordered binary decision diagram (ROBDD). Group predicates compile to exact cardinality BDDs. No two identities are collapsed to a count, and no player is credited with optional pickups they did not make.

Positive conditions/monotone updates are enforced by the contract, but **reversible movement, optional gates, a single SCC, or safe exploration are NOT assumed**. One-way gates, resource consumption, locked storms and irreversible dialogue/flag changes remain in the core. The solver must discover their softlocks and permanently missable collectibles. Ordinary 1.0.0 games still use the original exhaustive algorithm by default. `--strategy exhaustive` is an independent concrete-state oracle for small 1.1.0 games; `--strategy symbolic` selects symbolic analysis explicitly.

Exactness conditions and proof: [SYMBOLIC.md](SYMBOLIC.md). Resource bounds apply to core states and allocated BDD nodes, NOT represented concrete-state cardinality. Exhaustion is INCONCLUSIVE. No state cap was raised to hide the independent-collectible explosion.

## Additional proof obligations

Report (1) every ending reachable; (2) every collectible reachable; (3) each group.required and every authored at_least threshold attainable; (4) no reachable nonterminal state lacking any ending route; (5) no reachable **nonterminal** state from which a missing collectible can never be acquired before termination. The last obligation detects permanent loss after storm/gate transitions, including losses on a branch even if that collectible is reachable on another branch. Choosing an ending intentionally stops play and is excluded from the missability requirement. Counts refer to concrete states, not just core nodes. Return concrete, replayable witnesses for endings, found collectibles and failure examples. Capped output examples must be labelled and exact total counts preserved.

E1/E2/E3 API signatures and diff format are unchanged. Their regressions now use the 1.1.0 proof obligations. E3 continues to add a fresh mutable ending trigger flag. Save/room-bundle deltas are in [GAME.md](GAME.md).
