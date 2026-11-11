---
name: hermes64-author
description: Use when building original games. Compile maps and verify.
version: 0.1.0
author: Dylan, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [games, authoring, world-map, quests]
    related_skills: [hermes64, hermes64-gameplay-modules, hermes64-playtest-and-ship]
---

# Author an original game, not a reskinned starter

Use for an original prompt, room graph, NPC conversation, gates, branching quest or timed course. The **agent designs the game**. The compiler does not interpret prose or call a model. `/hermes64 new` still makes a starter; do not present it as the requested original game.

Read `docs/AUTHORING-SCOPE.md` first. Work inside an existing owner-chosen projects root; never install tools, enable a profile, download, publish or modify plugin code for a game. Godot 4.6.2 and Python with numpy must already be available; the native sandbox currently requires macOS. Verify numpy in the clean child environment, not just your interactive shell. Use `hermes64_doctor` on an existing project, or follow the main skill's first-run guidance.

## Procedure (do every stage)

1. **Brief.** Write title, protagonist, objective, 2–3 concrete verbs, fail/retry behavior, intended length and a distinct decision or challenge. Name unsupported requests plainly; don't translate a platformer into an adventure silently. No arbitrary code, currency, XP, physics scripting or metadata behaviors.
2. **Map.** Write a new JSON outline (`format: hermes64-world/1`) with a different graph, not the starter's two rooms. Start with 4–6 rooms for exploration, fewer for a focused course. Draw links on paper/in text: `court:east ↔ library:west`; a gated forward endpoint need not gate return. List where the gate's key/fact is produced. Never put a sole key behind its own gate.
3. **Rooms.** Give each room a purpose, name, description, size (whole metres 4..16) and a landmark. Coordinates are `[x,y,z]`, X east/Z south. A link generates both reciprocal door records, centered by default. `position`/`back_position` are tile indices. Avoid duplicate wall slots. Author cameras only after checking actual framing.
4. **Characters/NPCs/dialogue.** Run from the installed plugin root:
   `python3 -B -m adventure_maker.author catalog --pack castle_keep`
   Pick **explicit** public cast IDs for each `cast[].asset`; authored IDs/names stay yours. These are disclosed stand-ins, not original wizard/pirate costumes. `hero` names a declared cast ID. Dialogue has `id,character,room,at,nodes`; a node has `id,text,choices`; choices have `id,text,when?,effects?,next?` (empty next closes). Compiler creates the talk action/cursor. Avoid trapping a player in dialogue; cancel stays available. Custom character proposals still require the user's choice through the character skill; never auto-adopt one.
5. **Items/gates/quests.** Declare `flags` as `{id:false}`, inventory `items` as `{id,name,description?,asset?}`. An omitted item asset is a semantic `inventory/<id>` token, **not a generated visible model**. Put visible scenery separately in rooms. Actions have `id,room,label,effects` plus `text,kind,target,when,at`. For take, target must be an item; for talk, a character. Conditions/effects are exact STORY objects, not expressions. AND only; make alternative actions for OR. Conditions: `{flag,equals}`, `{item,present}`, `{location}`, `{dialogue,node}`, `{role,equals}`, `{tide}`; module challenges add `{challenge,status:"completed"}`. Effects: `{flag,value}`, `{give}`, `{take}`, `{dialogue,node}`, `{location}`, `{tide}`. No negative collectible or numeric counter invention. Endings are `{id,text,when}` and stop play immediately. Use separate explicit terminal flags for branches; let players explore both preparations before choosing. Quests `{id,title,description,when}` are derived objectives, not implicit gates.
6. **Reusable data.** `python3 -B -m adventure_maker.author patterns` lists `key_pickup`, `flag_switch`, `npc_hint`, `guardian_answer`, `branch_finish`. An instance is `{use,args}`; supply every named argument exactly. Patterns only expand finite data. The guardian is a conversation/riddle, **not a combat boss**. The worked example below uses this honestly.
7. **Mechanics.** `courses` adds STORY 1.2 with abilities/challenge/course modules: `{id,room,start:[x,y,z],checkpoints:[[x,y,z],...],deadline_ticks,par_ticks,countdown_ticks?,when?}`. 60 Hz, one lap, on-foot speed ceiling 4 m/s, radius .8 m, freeze on pause, checkpoint retry. Keep clear paths and a generous but finite deadline. Gate finish on that course id's completed challenge. For combat, region graphs or grid puzzles use the module skill and authoritative closed contracts; this outline compiler does **not** invent arbitrary module JSON. Full STORY 1.2 specs can still use scaffold; 1.3 puzzles need the separate module pointer workflow in `docs/PUZZLES.md`. Do not feed 1.3 directly to legacy scaffold/check/replay.
8. **Style/mood/assets.** `hermes64_packs {action:"list"}` then `hermes64_kits {action:"inspect",id:"..."}` or the catalog CLI above. Choose a pack for the whole project; room pieces must actually be bound in that pack. Outline `mood:"violet_dusk"` or `"amber_evening"` is consumed lighting/fog/grade data, not new textures. Neutral door-cut wall modules are generated for interiors. Add real `rooms[].pieces` `{asset,position,scale?,yaw?,kind?,mounted?}` from the catalog; never silently substitute. Keep the central walking lanes and anchors clear. Moods do not relax any gate. Model palettes remain shipped kit colours. User asset conversion/generation is not implemented by this authoring compiler; disclose gaps instead of claiming arbitrary asset creation.
9. **Compile source, then scaffold.** Use file tools to write a fresh outline, then:
   `python3 -B -m adventure_maker.author compile world.json --out authored-spec.json`
   `python3 -B -m adventure_maker.author lint authored-spec.json --report author-lint.json`
   Both outputs must be new files. Lint distinguishes admission, unplayability and structural warnings, **not fun**. Read all issues and the proof, fix the outline and use a fresh output filename. Do not raise caps or weaken gates. Unknown fields/IDs/assets refuse with plain errors.
10. **Tool calls**, in order (JSON strings below are serialized **file contents**, not paths):
    - `hermes64_scaffold {project:"violet-tower",pack:"castle_keep",spec_json: JSON.stringify(authored_spec)}`
    - `hermes64_compile {project:"violet-tower",spec_path:"source/spec.json"}`
    - `hermes64_check {project:"violet-tower"}`
    - `hermes64_build_assets {project:"violet-tower",seed:7}`
    - `hermes64_playtest {project:"violet-tower",mode:"both",seconds:5,seed:7,render:false}`
    - `hermes64_replay {project:"violet-tower"}`
    Check every return and follow a truncated response's `report_path`. A 1.1 check must be `proved`. For 1.2, also call `hermes64_module_check {project:"signal-sprint",spec_path:"<revision.spec returned by compile>",adopt:false}` and require `ok:true` under its explicit conditional policy. Its status stays **conditional**, never proved; raw legacy `hermes64_check` may still say `ok:false`. This extra admission check does not adopt a module data pointer or prove runtime feasibility. `ROUGH`/missing assets is not passed. Timed replay support and exact acceptance are documented in `docs/AUTHORING.md`.
11. **Fix.** For proved 1.1 games use `hermes64_edit` with guarded JSON Patch and `expected_spec_hash`, then check/build/bot/replay again. Never recompile stale `source/spec.json` after an adopted edit. Conditional module edits use `hermes64_module_check/edit` with exact hashes; their data pointer is separate from legacy runtime selection. Source-revision repairs before initial adoption can use `hermes64_compile.patch_json`, but it does not rewrite source. Never edit generated `.maker/runs` files. Preserve failed receipts.
12. **View/export.** When opening is authorized (as in an explicit capture request), `hermes64_open {project:"violet-tower",seconds:8,screenshots:true}`. View actual PNGs yourself. This visits every room for visual coverage; it is not a physical playthrough. Also run `hermes64_check {project:"violet-tower",action:"audit",views:0}` if judging measured style. Never call machine gates art approval. Export locally: `hermes64_export {project:"violet-tower",targets:["macos"]}`; a conditional course requires `module_preview:true` and fresh physical coverage. Templates must already exist; no download. Report actual paths and unverified recipient/browser/Windows/human/art gates.

## Worked example: The Violet Tower

Read the complete compact source in `examples/wizard-purple/world.json`. Copy and author it as data, not plugin code. It has four purposeful rooms, two NPCs, a moon-key gate, a clue-gated non-combat guardian and a beacon ending. `examples/wizard-purple/spec.json` is the compiler output for reproducibility, not a required template. Run the compile/lint commands and tool sequence above; use a new project slug. Change the room graph, verbs, gate producers, NPC text and endings for another prompt, not just title/palette.

`tools/author_proof.py` (repository-only QA) logs all three independent re-authorings and real tool calls. The installed user path needs only the bundled compiler, data library, this skill and ordinary Hermes file/terminal tools. No new advertised tools or schema fields are needed.

## Handoff

Say what was made; cite current source/game hashes, checker status, each ending's bot/replay coverage, assets/captures/export paths, and what still looks weak. Keep art approval, human balance, clean-profile install, recipient execution and native Windows in NOT VERIFIED unless actually performed. A deterministic compiler and scripted tool loop do not prove a different model can autonomously design a good game.
