# Contract feedback for Hermes Main

No upstream files were modified. Implemented versions: STORY 1.0.0 and 1.1.0. These are proposals, not silent contract amendments.

## Observed parity / resolved runtime issues

- Last Light exhaustive Python-vs-Godot comparison covers every reachable state and edge. Thaw ending and all collectible witnesses are replayed with every step's complete state and legal-action set, plus illegal-action refusal reasons. Final verification receipts determine the accepted counts; no semantic divergence remains in those tested domains.
- An early comparison reported all WAIT edges different because Godot's JSON parser returns `1.0` while runtime arithmetic creates `1`, and nested Dictionary equality is type-sensitive. Restoring integer **tokens** in the I/O adapter fixes the harness mismatch, not tide semantics (03/04). A later RED test (26) caught over-normalizing floating-point tokens; the final adapter preserves `1.0` / `1e0` for strict tick rejection and opaque timestamps (27).
- The initial runtime used the discovery label for recall. Python uses `Recall ` + the collectible's authored name. Regression 13 observed this failure; runtime label corrected. No contract behavior was changed.
- A collected cat initially remained as a static resident plus a follower. Regression 14 observed the duplicate presentation; fixed by hiding the resident instance for that collected follower. Identity/count state was already single-credit.

Readiness note: a later upstream Thaw recompile changed its style-pack name, added a derived quest and added keycard props. `tools/report.py` refused the stale snapshot rather than claiming current-source verification. `evidence/thaw-source-drift.json` records the diff; final acceptance uses a fresh `thaw-2` snapshot and reruns both headless and rendered proofs.

## Proposed versioned clarifications

### STORY 1.1.1 documentation-only proposal: presentation units and placements

1. Declare `props[].rotation` as XYZ **degrees**, Euler order matching the renderer contract, or explicitly choose a different convention. Current Last Light authors `[0,90,0]`; runtime treats it as degrees. The frozen contract supplies only numbers, not units/order.
2. Declare how multiple camera anchors select active camera. Current runtime uses nearest look-at point with 0.75m hysteresis plus manual cycle; no camera zones are in the wire schema. A versioned optional metadata layout convention could carry zones/spawns without changing logical state.
3. Declare positions for interaction targets, characters and collectibles through optional `metadata.presentation.rooms` (or a future versioned structural field). Current collectible schema has room but no transform; primitive layout uses deterministic placement. Complete legal room actions remain reachable via the sidebar, so this choice cannot silently invalidate a checker witness.

### STORY 1.1.1 clarification: WAIT while a graph guard becomes false

The Python reference permits WAIT during dialogue even when it changes tide away from the active node's guard. The cursor stays active; choices must satisfy node/choice guards; cancel remains legal. The GDScript does exactly this, including save membership for such reachable states. State validation must not invent an invariant that every active cursor's node guard always holds. Suggested explicit sentence avoids consumers accidentally refusing legal saves or WAITs.

### KITS/STORY integration mapping (Main decision, no semantic-ID mutation here)

STORY 1.1.0: `expedition_base_v1` / `human_16`, `cat_base_v1` / `cat_8`.
KITS 2.0.0: `char.expedition_figure` / `expedition16_v1`, `char.cat` / `cat16_v1`.

These are not equal identities or even equal cat bone counts. Propose a versioned asset-binding manifest mapping semantic story identities and suit/coat params to explicit built GLB variants, hashes, bone identities and animations. Do not silently substitute default variants for authored coats/suits or claim retargeting compatibility. Room shells use centred origins and need explicit half-room translation. Until that binding and actual manifest-backed GLBs exist, placeholders are intentional.

## Deliberate scope / limitations, not hidden parity claims

- Runtime's same-version save loader proves exact reachable membership by target-directed concrete search. It is not a port of the symbolic ROBDD solver. A budget exhaustion returns `inconclusive`, leaves live state untouched and asks for an external STORY migration/membership route; it never guesses acceptance from count ranges. Both current games and cumulative 20-pickup saves are exercised in final evidence.
- Cross-revision migration belongs to STORY. Runtime rejects changed hashes/version with an explicit migration-required reason; Main/plugin must supply the explicitly migrated, source-validated state-only save.
- The in-process GDScript API assumes valid compiled game dictionaries. It is not a full reimplementation of Python canonical game-hash/schema validation. Admission of tampered/untrusted JSON must go through STORY's compiler/validator first; don't present an in-process dictionary configure as a security boundary.
- The graphical bot dispatches actual room/UI actions, not a navigation planner. Logical proof does not certify physical pathfinding, arbitrary kit collision, visual quality, ten-minute pacing or human acceptance.
