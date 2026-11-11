# The Violet Tower — authored example

A four-room wizard-tower quest: speak with Ione, recover the moon key, answer a non-combat guardian with the clue you learned, then restore the beacon. This is not the two-room keepsake starter.

- `world.json`: compact original outline and reusable NPC/key/guardian/finish patterns.
- `spec.json`: deterministic output of `python3 -B -m adventure_maker.author compile world.json --out <new-spec.json>`.
- Pack: `castle_keep`; mood: `violet_dusk`. The mood is runtime lighting/fog/grade over shipped models, not a newly generated asset pack.
- Cast: explicit public forest-cast stand-ins with original in-game names; no bespoke wizard costume claim.

Load the `hermes64-author` skill, compile/lint into new files, scaffold with `pack:"castle_keep"` and serialized spec contents, then compile/check/build/bot/replay/open/export as in `docs/AUTHORING.md`. `hermes64_demo example=wizard-purple` is **not** an enum value; use scaffold. No new demo selector or newgame.py change was made.

AUTHOR's real native run: story proved, physical bots PLAYABLE with no missing bindings, Godot replay/save passed and local macOS export boot passed. The style audit **FAILED**: the violet grade is off the shipped castle palette, contrast is low, the room cutaways expose background and the genre pack supplies no complete room shells. All four actual room captures were inspected; furniture is sparse, character silhouettes are not wizard-specific and the tower is a small in-room landmark. This is an authoring example, not approved production art.

Full source-only lane result: `docs/AUTHOR-RESULT.md`. Local retained captures and tool-call transcripts: `evidence/author/proof-01` in the source checkout; evidence is not shipped to users.
