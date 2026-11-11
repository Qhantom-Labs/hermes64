# Make your own game with Hermes64

Load **hermes64:hermes64-author** and give your agent a prompt. Ask for a small original world, not `/hermes64 new` alone. The agent must design the rooms, characters, conversations, objective, gates and endings; this release does not turn arbitrary prose into game logic by itself.

For example: “Build a purple wizard tower with four rooms, an archivist, a moon-key gate and a guardian who tests a word I learned earlier. Show me the actual game and explain missing art.” The complete worked source is [`examples/wizard-purple/world.json`](../examples/wizard-purple/world.json). Its public reused actors are not bespoke wizard costumes. Read [scope](AUTHORING-SCOPE.md) before requesting other genres.

## Before starting

Use an existing owner-chosen `projects_root` and trusted plugin bundle. Project arguments are slugs, not paths. The native runner on this base is macOS-only. Godot 4.6.2, a builder and numpy in the configured Python must already exist. No tool here downloads or installs them. `builder=python` is an explicit choice, not a silent fallback from Blender. An ordinary shell import of numpy can succeed while the sandboxed Python cannot; configure an already-installed interpreter that has numpy in its clean environment.

## Compact world-map format

The compiler is bundled with the plugin, needs only stdlib for source compilation, and is available through the agent's ordinary terminal/file tools. From the plugin root:

```
python3 -B -m adventure_maker.author catalog --pack castle_keep
python3 -B -m adventure_maker.author patterns
python3 -B -m adventure_maker.author compile world.json --out authored-spec.json
python3 -B -m adventure_maker.author lint authored-spec.json --report author-lint.json
```

Output files must be NEW; existing files are never overwritten. Compilation validates the exact story contract, but does not prove the game playable. Lint adds bounded logical analysis and explained structural warnings, not a fun score.

Required outline keys: `format:"hermes64-world/1"`, `id`, `title`, `brief`, `pack`, `start`, `hero`, `rooms`, `cast`, `endings`. Optional: `links`, `items`, `flags`, `actions`, `dialogues`, `quests`, `courses`, `patterns`, `mood`. Unknown fields refuse. Story IDs use lowercase letters/digits/underscores, beginning with a letter; they are never silently normalized.

| Field | Shape / behavior |
|---|---|
| rooms | `{id,name,description?,size?:[w,d],outdoors?,pieces?,look?,camera?:{position,look_at}}`; 4..16 metres each direction, default 10. Each room has a purpose, not just a different texture. |
| links | `{a:"court:east",b:"library:west",when?:[],back_when?:[],position?,back_position?,label?,back_label?}`; emits both reciprocal door records; default centered tile. Independent guards in each direction. Parallel links to the same room refuse. |
| cast | `{id,name,role,asset,room?,at?}`; `asset` is an explicit public cast ID from catalog, not a filesystem path. Copies actual body/rig/params while keeping authored identity. `hero` names a cast entry. |
| items | `{id,name,description?,asset?}`; absent asset becomes a semantic `inventory/<id>` token, **not** a made-up visible model. Add visible scenery explicitly. |
| flags | `{gate_open:false,beacon_lit:false}`; Boolean only. |
| actions | `{id,room,label,effects,text?,kind?,target?,when?,at?}`; kind defaults to use. Take targets an item, talk targets a cast member. Anchors default to the room center; keep scenery clear of them. |
| dialogues | `{id,character,room,at?,label?,nodes:[{id,text,when?,choices:[{id,text,when?,effects?,next?}]}]}`. First node is start; empty next closes. Compiler emits the talk action/cursor. |
| quests / endings | Quest `{id,title,description,when}` is derived. Ending `{id,text,when}` terminates immediately. Multiple matching endings are invalid logic. |
| courses | `{id,room,start:[x,y,z],checkpoints:[[x,y,z],...],deadline_ticks,par_ticks,countdown_ticks?,when?}`; 60 Hz, single lap, on foot, checkpoint retry, pause freezes clock. The course ID is also its challenge ID. |
| patterns | `{use:"key_pickup",args:{...}}`; inspect the data library for exact arguments. Five reusable key/switch/NPC/guardian/branch patterns, not hidden game-specific code. |
| mood | `violet_dusk` or `amber_evening`: runtime lighting/fog/grade, **not** new model textures. Optional per-room look supports consumed fog/background/ambient/key/fill/grade controls; no arbitrary metadata event wiring. |

Coordinates: X east, Y up, Z south. A tile is one metre. Links use north/east/south/west walls. Interior walls are assembled as neutral `_wall` kit pieces with visible door gaps and a low south cutaway; floor uses the built `_floor`. These are a fallback architecture, not a replacement for detailed themed room plans. `pieces` are `{asset,position,scale?,yaw?,kind?,mounted?}` and must exist in the chosen pack. Do not mark a solid obstacle as mounted just to pass a bot; rearrange it.

Conditions/effects retain exact STORY semantics ([base contract](story/v1.0.0/SPEC.md)). All condition arrays are AND. Inventory is finite identity membership, not quantities. Separate actions/endings express OR. Flags, keys and dialogue choices cannot execute scripts. Tide advances only on WAIT, so use a course for a real deadline. Full 1.2 combat/region data and 1.3 grid puzzles remain available through their own [module](MODULES-CONTRACT.md) and [puzzle](PUZZLES.md) workflows; the compact format currently emits only 1.1 and on-foot-course 1.2.

## Build and verify through tools

After reading the compiler's emitted source file, serialize its contents into `spec_json`:

```
hermes64_scaffold {project:"violet-tower",pack:"castle_keep",spec_json:"<serialized authored-spec.json>"}
hermes64_compile {project:"violet-tower",spec_path:"source/spec.json"}
hermes64_check {project:"violet-tower"}
hermes64_build_assets {project:"violet-tower",seed:7}
hermes64_playtest {project:"violet-tower",mode:"both",seconds:5,seed:7,render:false}
hermes64_replay {project:"violet-tower"}
```

Require `proved` for 1.1; modules remain `conditional` with named skill assumptions. Check's `ok:false` for conditional is not a rejection. For a 1.2 source, also call `hermes64_module_check {project:"signal-sprint",spec_path:"<revision.spec from compile>",adopt:false}` and require `ok:true` under the existing explicit conditional policy. This does not adopt a data pointer, change legacy check semantics or prove physical feasibility. Check every physical report: complete paths with missing assets are ROUGH, not a pass. Follow full `report_path` on truncated tool responses. Repeat verification after fixes; use the guarded edit tools for adopted revisions, never generated files. The main skill explains revision pointers and conditional module edits.

**New replay support:** an explicit conditional STORY 1.2 single-ending game now uses a fresh physical module run, then actually plays its recorded movie against periodic/final state hashes in Godot. It also writes/loads the legal initial checkpoint save. It never executes `assume:complete` as a player action or promotes conditional logic to proved. Uncovered modules, missing art, movie divergence and multi-ending module runs fail closed. Legacy 1.0/1.1 replay is unchanged. No new tool or schema field is added.

With permission to open a preview, call `hermes64_open {project:"violet-tower",seconds:8,screenshots:true}` and inspect its PNGs. Screenshots visit rooms for visual coverage, not physical traversal proof. Optional `hermes64_check` `action:"audit"` measures style without granting art approval. Report weak framing, colour, stand-ins and missing visuals even if numeric gates pass.

Export locally with `hermes64_export {project:"violet-tower",targets:["macos"]}`. Conditional course preview needs `module_preview:true` and a fresh complete physical run. Missing templates refuse, never download automatically. A built app is not another person's tested app; web/browser, Gatekeeper, Windows and human judgments remain separate.

The source QA driver `tools/author_proof.py` demonstrates this exact pipeline on three independently authored outlines and retains every public registered tool argument/result. It is not shipped or required for user authoring. No newgame.py change is part of this lane.
