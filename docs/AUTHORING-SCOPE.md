# Hermes64 authoring scope

**A bounded 3D adventure toolkit, not an arbitrary game engine from any prompt.** Your agent can write finite game data and run checks. It must say what it cannot represent rather than silently replacing the request with a renamed starter.

## Three workflows, different scope

| Workflow | What to expect | Source |
|---|---|---|
| Plain request through `hermes64-create` | Plans an authored brief, builds rooms/assets, runs story checks and bots, writes `CREATE-REPORT.md`. The rc7 flow starts with an outdoor entry and one interior; more named places can become story spots, not additional rooms. Entry cast is bounded to 4 and interior cast to 3. `setting.room_scale` is optional. | [Create skill](../skills/hermes64-create/SKILL.md), especially “What the flow makes” |
| `/hermes64 new` / `hermes64_demo(premise=...)` | A quicker starter selected from supported templates; not the complete original-authoring workflow. | [Quick start](../QUICKSTART.md) |
| Direct authoring / module tools | Finite room graphs, authored dialogue, gates and endings; separate supported combat, course and grid-puzzle contracts. More authoring and checks are required. | [Authoring](AUTHORING.md), [module skill](../skills/hermes64-gameplay-modules/SKILL.md) |

## Supported contracts

- Room-to-room exploration, authored actions/conversations, finite quests and terminal endings; doors can be gated by keys, flags, roles and dialogue conditions.
- Inventory membership and finite story effects, not a general money/materials economy. Branching endings are authored guards/actions, not arbitrary program code.
- Bounded melee arenas, waves, robot and boss contracts. A combat/courses story proof may be **conditional**, not fully proved by the story checker.
- Ordered timed **on-foot** courses with checkpoints and retry; a timed run is not a platformer or vehicle race.
- Grid puzzles through the separate puzzle module/runtime workflow. The plain create flow does not build a grid puzzle automatically; it can report a door-lock or choice as the closest supported alternative.
- Bundled public cast/packs, supported character workflows and bounded data-only prop recipes. An asset for every noun, a new costume or an arbitrary imported rig is not guaranteed.
- Local captures, bot/replay reports and exports subject to engine/templates, platform and content restrictions.

## Not promised

| Request | Boundary |
|---|---|
| Platformer, precision jumping, climbing, swimming or flight | No general authored vertical-traversal/air-control system. |
| Vehicles, kart racing, driving simulation | No vehicle dynamics or racing AI. |
| General FPS/TPS or bullet-hell | Bounded enemy attack patterns are not a player aiming/ammo/weapon system. |
| Multiplayer, MMO, online co-op | No shared networked world/server-authority contract. |
| Seamless open world | Rooms form a finite graph, not continuous terrain streaming. |
| Crafting, economy, city/farm/survival simulation, arbitrary RPG stats | No general simulation/counter/production/levelling system. |
| Arbitrary module combinations | Module ownership restrictions apply; a puzzle room cannot also host a challenge. |
| Autonomous NPC conversations | Dialogue is authored text, not live NPC inference. |
| Any prompt represented exactly | Check `Not applied`; the agent must state unsupported details and alternatives. |
| Human fun, balance, appearance or production readiness | Checks and bots do not supply human acceptance. |

## What a report establishes

A finite story proof is not a physical playtest. A completed bot path is not every possible human route. A strict replay tests recorded inputs/hashes; image/geometry audits measure their named thresholds. Keep their verdicts separate, including conditional, refused and failed results.

`hermes64_edit` requires a proved story baseline. A combat/course game can refuse that tool as `baseline_unproved`; use the appropriate create/module workflow and re-run its checks instead of claiming every edit is automatically proved.

The manifest targets macOS and Windows; the latter's Job Object opt-in has no OS network/write confinement. Linux authoring is implemented behind bubblewrap and not verified ([LINUX.md](LINUX.md)). Clean installs, native Windows execution of the final package, recipient export boots and human approval remain separate acceptance checks. Historical measurements live in [game-type strengths](GAME-TYPE-STRENGTHS.md); they are not a certification of a later candidate.
