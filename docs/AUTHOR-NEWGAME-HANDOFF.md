# AUTHOR → tbuild integration note (not applied)

`adventure_maker/newgame.py` remains untouched. The direct-author workflow is now exposed through the registered `hermes64-author` skill, scaffold's compact description, README and `docs/AUTHORING.md`. It does not reinterpret `/new` or claim that the starter is a complete original game.

Recommended tbuild-owned follow-up: the new-game result should explicitly call its output a starter and offer the agent `skill hermes64:hermes64-author` for the requested original design. Preserve the raw badge and all existing creation/refusal semantics. No additional tool schemas are required.

Do not wire this by renaming the starter's two rooms or by automatically treating a title/style as authored content. The model must author a brief, map, objectives, NPC dialogue, gates and endings, then pass the real tools. If using the compact outline compiler, feed its full emitted spec to `hermes64_scaffold.spec_json` rather than generating a premise starter first.

No code patch is necessary for the standalone skill/helper route delivered here. Any future `/new` dispatch change belongs to tbuild, and should retain conditional module status and visual failures rather than manufacture `new_game_ready`.
