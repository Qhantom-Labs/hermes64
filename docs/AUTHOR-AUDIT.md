# Direct-author audit (phase 1, rc3-base-1)

Executed `tools/author_audit.py`: three hand-written original story specs, not `premise_spec` or `/new`. Calls use the existing Service/SHIP tool handlers. Full arguments, exact returns and immutable native receipts: `evidence/author/manual*/calls.jsonl`; short logs `manual-run.log`, `manual-02-run.log`. Evidence is local/ignored; reproduction driver is tracked.

| Game | Actual design | Check | Physical bots | Legacy replay |
|---|---|---|---|---|
| Violet Tower | 4 rooms; archivist dialogue; moon-key gate; guardian answer gate; beacon ending | proved | completed, ROUGH (4 missing bindings) | passed, including save round trip |
| Dry Creek Dispatch | 4 rooms; telegraph repair OR water/train objective; 2 endings | proved | completed, ROUGH (2 missing bindings) | passed, including both endings and save |
| Signal Sprint | 3 ordered checkpoint spheres; countdown; deadline; checkpoint retry | conditional | completed, ROUGH (2 missing bindings) | refused `unproved` |

## Friction, actual refusals and knowledge gaps

- Scaffold accepts structurally invalid 1.1/1.2 JSON as `scaffolded_unvalidated`; only compile validates it. A tool success is not an authored game.
- Talk targets must be **character IDs**, take targets **item IDs**. First wizard compile: `interactions/talk_archivist/target: missing reference 'talk_archivist'`. Base contract says `target: string`, not this reference rule.
- A malformed reciprocal endpoint: `court/door/to_library: missing reference 'missing'`. Both door records and geometry must be authored; tool exposes no world-map convenience.
- Invented economy effect: `interactions/talk_archivist/effects/0: unknown or malformed effect ['gold']`. There is no numeric currency or arbitrary action script.
- `1.3.0` direct scaffold: `Expected a story JSON object, contract 1.0.0, 1.1.0 or 1.2.0`. Puzzle tools use a **separate data pointer**, not the legacy current pointer.
- Course check returns `conditional` and `ok:false`, even when logically accepted under explicit conditional policy. It is not rejected and not proved. Legacy replay refuses: `Godot replay requires a current proved checker report`. No integrated movie-replay route is taught.
- First asset builds failed `No module named 'numpy'` although ordinary Python import worked. The subprocess's clean environment loses user-site numpy. Repeated using the already-installed Hermes venv Python (no install); builds passed. Subsequent native preview after an asset-build failure hit `KeyError: 'arch.floor_module'`; dependency failures cascade misleadingly.
- All three physical paths actually complete, but arbitrary cast IDs render placeholders: `character:unknown`, `character:archivist`, `character:guardian`. Public bound selectors require matching body/rig/params, not just a name. A declared protagonist and compatible public cast are necessary.
- Genre packs lack generic `arch.window`; bare rooms invoke that fallback and get missing-assets warnings. Agent must choose explicit room dressing, not assume one pack renders every semantic ID.
- Pack schemas let agents create palette/mood **data**, but this base builds model colours from a shipped `kit_pack_id`. No arbitrary prompt-to-mesh implementation is merged here. Room `look.grade.tint` is silently ignored; actual supported controls are gain/lift plus lighting/fog. Metadata is untyped and can accept no-op fields.
- Rooms have no default anchors for authored actions; physical bot constraints and story location-scoped menu rules differ. Explicit anchors are required for useful physical evidence.
- Story conditions are AND only. OR is separate actions/endings. Terminal endings disable further actions; keep mutually exclusive terminal triggers. Nonterminal branches must retain an ending route.
- Tide is WAIT-only turn time, **not** a real-time deadline. A timed game needs the course module.
- Existing skills contain historic pre-integration warnings: module runtime is now present, though old docs call it unimplemented. Seven skills are registered on this base (not five); none teaches complete original authoring.

No full art verdict, native Windows, fresh-profile install, or exported-recipient execution is claimed in phase 1. New helpers must address admission clarity, cast/dressing, outline expansion, lint and the timed replay seam without editing protected subsystems.
