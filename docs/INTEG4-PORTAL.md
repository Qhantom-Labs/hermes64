# INTEG4 portal-ring taxonomy decision

## Decision: over-matching data, not a stale expectation

Keep `tests.test_taxonomy.TaxonomyTests.test_wizard_brief_gap_report`'s `portal ring = partial` expectation and **all taxonomy checker semantics unchanged**. Correct only `tools/tag_kits.py:OVERRIDES`, then regenerate `catalog/tags.json` and `docs/ABIBLE-REVIEW-NEEDED.md` with `tools.tag_kits build`.

On starting composed tree `add451d8` (ABIBLE merge `bff73bee`), the unchanged checker reports `exists`, specifically **2 pieces of kind portal**:

| Generator | Why the mechanical tagger called it portal | Geometry evidence | Correct kind |
|---|---|---|---|
| `cyroom.portal` | Generator id tail is `portal`; kind-from-id wins before description | `kits/core/gen_cyberkit_room.py:212–220`: two tapered jambs at x ±1.2, one bevelled lintel, inset light strips, `door_anchor` / door socket. Description: "Chamfered transit doorway frame". No gateway ring geometry | `door`, `arch` |
| `cydress.shutter` | No `shutter` kind; description-head fallback matches "portal" in "Recessed roll shutter in a chamfered steel portal." | `kits/core/gen_cyberkit_dress.py:62–69`: two frame slabs, header slab, rectangular door face card; roll shutter opening, not a gateway ring | `door` |

Both originate in CYBERKIT source history (`f713d4a9`, present via CYBERROOMS M1), not a newly invented ABIBLE generator. ABIBLE's main-based original tags lacked these imported generators; INTEG3 correctly regenerated coverage on the composed tree, exposing these ambiguous architectural uses of the word "portal".

## Criteria and unchanged semantics

`adventure_maker/taxonomy.py:410–418` makes a named kind exist when any piece is tagged that kind; related `arch` / `door` kinds are **partial** for portal. `split_terms('portal ring')` identifies the `portal` kind; "ring" is not an independent kind gate. The checker is tag-based, not a geometry/budget/style-bible validator. We have not added geometric or style tests to its semantics or changed thresholds to fix this case.

Independent default builds (`tools.style_bible.measure_library` / `check_asset`) show:

- `cyroom.portal`: **88 triangles / arch budget 300**, bible hard checks pass, no advisory warnings.
- `cydress.shutter`: **86 triangles / furniture_large budget 400**, bible hard checks pass, no advisory warnings.

Being in budget does not make a rectangular transit frame or shutter the same shape family as a portal ring. Both generated rows say **boxy**, not round. Neither has wizard/magic/fantasy genre tags (`cyroom.portal`: none; shutter: interior). They belong to the three cyber packs. Their valid asset budgets therefore do not cure the kind/style mismatch. They are usable **named stand-ins**, not evidence of a portal-ring capability. No aesthetic judgment is made.

The minimal fix seeds these two pieces' real architectural kinds; no aliases, thresholds, ranking, related-kind rules, expected test values or generator geometry change. Seeds remain explicitly `needs_review` under the existing tagger policy. There are no remaining generator rows of kind portal; the unchanged gap report now says **partial**, with named door/arch stand-ins.

## Receipts

- `evidence/integ4/portal_probe.py` and `portal.json`: exact before/after rows, gap output, default mesh stats, bible checks and unchanged checker/test source hashes; archived in the INTEG4 receipt index.
- `integ4-m6b-before`: reproduced **46 tests, one failure**, precisely portal ring exists vs partial; original compressed stdout/stderr retained in `docs/merge6/runs/`.
- `integ4-m6b-focused`: **the same 46 tests pass** with the expectation unchanged. Full split-stage / prior-tag legacy comparison result is recorded in `INTEG4-VERIFICATION.json` and `INTEG4-RESULT.md`; no acceptance implied until those checks complete.
