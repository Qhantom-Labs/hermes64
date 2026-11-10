# STORY presentation documentation note 1.1.1

This is a documentation note only, **not** a new `contract_version`. The 1.1.0 wire format and semantics are unchanged; Last Light remains 1.0.0 and Thaw remains 1.1.0.

Optional `metadata.presentation` uses the existing free-form metadata extension point. Its conventions, typed values, rotation units/Euler order, camera selection, interaction/character/collectible anchors, ending titles and defaults are documented in [../PRESENTATION.md](../PRESENTATION.md).

The runtime consumes display metadata without introducing predicates, effects, save-state keys or new action preconditions. A metadata edit changes the game content hash; save migration must still be explicit. An unchanged room's semantic build hash is not a claim that its global presentation metadata did not change.

Original specs without this metadata remain regression fixtures. The engine tests compile and render those fixtures with default kit geometry/cameras; the facade showcase supplies the optional display metadata at scaffold time.
