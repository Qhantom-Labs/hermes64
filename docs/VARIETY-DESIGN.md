# VARIETY design: craft the game the brief asks for

Lane VARIETY, branch `variety-lane` from rc7 (`807b472d`). Numbers only; looks are for the owner to judge.

## Answer first

In rc7 a second prompt gives the first prompt's rooms because nothing in the default path makes anything new. The
picked fix (option B below) moves crafting into `create_flow run` itself: every run makes the game's own hero and
three or four of the things the brief names, and picks the entry layout from the setting words. The user types a plain
sentence; no helper wording, no new parameter, no new tool.

## What the pipeline does now (rc7), end to end

| stage | what decides it | what a plain brief gets |
|---|---|---|
| brief | the agent writes `brief.json`, or the flow's no-LLM brief | stock words the user never said (squire, well, cart, village house) |
| style | pack scored on genre, hints, place, builds, props, time | `medieval_village*` for 5 of 6 briefs, `frontier_town_night` for the station |
| mood | derived from the brief's palette words, else a shipped time variant | night/dusk/snow variants do change sky and light |
| assets | library match per need; a recipe only when the agent wrote one into `create/candidates.json` | 0 generated pieces in 6 of 6 plain runs |
| cast | spec compose binds the stock traveller | `human_base_v1`/`travel_coat` "Traveller" in 6 of 6 runs |
| rooms | `choose_pattern`: first pattern whose tag appears in the brief words, by word order | `plaza` in 5 of 6 (the family has 2 outdoor patterns), camera is part of the pattern: 2 distinct cameras in 6 games |
| audit/gates | story check, bots, style gate, N64 gate | unchanged by this lane |

## Where sameness is structurally forced

1. Pattern count: the medieval family has two outdoor patterns (`plaza`, `plaza_snow`) and the pick is word order, so
   every non-snow medieval brief is the plaza with the plaza camera.
2. Default cast: the player is always the stock traveller. `hermes64_character` sits under "Advanced tools: only when
   the human asks for that thing", so no agent calls it for a plain brief.
3. Generator trigger: a piece is generated only when the agent authors a recipe, which the skill also lists under
   Advanced. The tower prompt got new pieces only through the helper sentence.
4. Skill steps: the golden path has no craft step. An agent that follows every step exactly still ships catalog only.
5. The no-LLM brief adds the same stock props to every game, so the placed piece sets overlap (Jaccard up to 0.92).

## Why brief (b) reused the environment (Opus medium, rc7, `agents-before/o-b`)

- The agent followed the golden path with no skipped step: `vocab`, `find`, wrote a brief (`filled_by: model`),
  `plan`, `run --style medieval_village_night`, read the report. 11 tool calls, 0 calls to `hermes64_character`,
  0 recipes authored.
- Pattern: `plaza` + `taproom`. The brief's place was "moonlit medieval village at night with an old chapel"; no
  outdoor pattern is tagged for night, chapel or love, so the first pattern won.
- Cast: report line "character: knight is not covered: no new character made; the public cast 'fv_scribe' stands in".
- Generated pieces: 0. Not because the brief lacked an unusual object: the generators are never part of the default
  path. The chapel and cottage the agent asked for were "made but not placed: no free building lot in the plaza
  pattern".

## Options

| option | what changes | cost | risk | by 2 PM |
|---|---|---|---|---|
| A. Skill text only | tell the agent to call `hermes64_character` and author recipes for every brief | ~30 lines of skill, 0 code | depends on the model following it and on hand-authored recipes passing gates (4 tries each, +10 to 15 min per run); a weaker model skips it and sameness stays | yes |
| B. Craft inside the flow (picked) | `create_flow run` makes the hero (character maker propose/build/bind from the brief's words) and 3 to 4 brief-named pieces from bounded recipe templates through the existing generator loop and gates; the entry layout is chosen from setting words; agent recipes and agent casts still win; the skill tells the agent to fill what is missing | 1 module, 1 data file, 7 small `create_flow` hunks, skill text; no tool or schema change | finite template list (23); layouts are variants of one kit skeleton, not new rooms | yes |
| C. Craft phase + style brief + normalizer | a new craft stage with a visible plan, a `style` tool action with measured ranges and reference ids, a normalizer post-pass, 2 to 4 new room patterns per biome | new tool action (schema is at 5,998 of 6,000 tokens), new data, new patterns that need the full gate sweeps | each new pattern needs the anchor and audit sweeps TFIX needed; schema headroom is 2 tokens | no (more than a day) |

## Pick: B, and why

- It is the only option that removes the wording dependence: the default path makes new things with any agent and with
  no agent at all (the direct runs in `docs/VARIETY-RESULT.md` use the no-LLM brief).
- It uses only mechanisms that already ship and already have gates: the character maker, the generator loop
  (`asset_loop`, at most 4 tries, look and class-extent gates, provenance), kit pattern anchors.
- It leaves room for the agent: a recipe in `create/candidates.json` or a cast made with `hermes64_character` replaces
  the default for that thing, and the skill's step 6 asks the agent to make what the run did not.
- Style is kept by construction, not by a new pass: templates name pack palette roles, never colours; every crafted
  piece goes through the same look gate as any generated piece (set median texture energy at most 0.050) and a miss
  is a `Not applied` row, never a silent catalog fallback.

## How B works

1. Protagonist (`create_craft.craft_protagonist`): the user's own words pick a body and outfit line from
   `create_craft.json` `protagonists` (knight, keeper, fox, mechanic, pirate, apprentice ...; default traveller);
   propose, build, bind with up to 4 tries; the built cast replaces the stock traveller in the spec.
2. Pieces (`create_craft.plan`): up to 4 pieces the prompt names, then brief-only words and defaults up to 3. Each is
   a unit-space `hermes64-recipe/1` template whose every length is a multiple of one `height` parameter, so the
   loop's class-extent repair can resize it; `a|b` palette-role alternatives let the loop step to a calmer role.
3. Landmark: a crafted `landmark` piece takes the entry pattern's landmark slot.
4. Layout (`create_craft.setting_pattern`): layouts in `create_craft.json` are the shipped kit skeleton with another
   plot ground, entry building or wall piece and, where set, mirrored (camera, door, anchors, landmark slot). A layout
   is taken only when it names strictly more of the brief's setting words (prompt words count double) than the
   word-order choice. A brief that asks a room scale keeps the scale's choice.
5. Report: `Made new for this game: hero ...; pieces N of M planned: ...`, and one `Not applied` row per miss.

## Cut (not in rc8v)

- The style brief tool action and reference lookup (option C).
- A separate style normalizer pass with its own numbers: the generator's existing gates are the only style check.
- New room skeletons: the four layouts reuse the plaza or plaza_snow skeleton.
- Weather rendering (storm, fog stay story text) and any sci-fi kit: the station brief is built on the frontier pack.
