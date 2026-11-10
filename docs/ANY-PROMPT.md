# Any prompt: the structured brief

Hermes64 should make a game from **any** prompt: a wizard's purple world, a frozen viking harbour, a candy kingdom, a detective's office in the rain. It will not hit the target every time. It must always try, say what it made, and say what it could not make.

The first step is the **brief**: a small JSON file that says what the prompt asks for in words the rest of the plugin understands. Contract: `contracts/brief/1.0.0.json` (`hermes64-brief/1`). Code: `adventure_maker/brief.py`. Saved as `<project>/brief.json`.

The style stays ours whatever the prompt says. Rules plus references set the look (low-poly budgets, small soft textures, vertex light, small accents). The brief chooses *what* to make and the *mood*. It never sets *how* it is rendered.

## For users

Write your idea in one sentence. Name the place, the time of day, the colours and the things you want to see if you care about them. Anything you leave out gets a sensible default, and the reply tells you which defaults it used.

| You write | The brief records |
|---|---|
| a fantasy game in a wizard purple world | fantasy, wizard hint, purple palette, dusk by default, wizard tower, an old wizard |
| a frozen viking harbour | viking, winter, snow, harbour, longhouse, longship |
| a toy-sized candy kingdom in pastel pink | candy, toy hint, pink, light values, candy castle, lollipop trees |
| a detective's office in a 1940s city on a rainy night | noir, night, rain, office and street, a private detective as the player |
| three zorblaxes in a cave | a cave, and three "zorblax" listed as a piece to make (or reported as missing, never swapped for something else) |

What happens with special requests:

- **Quality settings** ("use 4K textures", "20k triangles", "photorealistic", "ignore the style"): ignored and listed in the brief's `assumptions`. The brief has no field for them, and its text fields refuse them.
- **Brands, franchises or real people** ("a Mario style mushroom kingdom"): you get a **generic version** (a cheerful jumping hero in a mushroom kingdom). The name is recorded in `ip_terms` so it stays out of asset names, ids and hub entries.
- **Your own files** (a logo, a texture, a model, music): list them as slots (below). The plugin records the licence and credit you declare. **It records what you declared; it does not check it.**
- **Neon or glow everywhere**: recorded as a rich saturation. The style gates still clamp glow and neon, so it will look softer than you may expect.

## For agents

1. **Fill the brief yourself** when you can. Read the prompt, then write `<project>/brief.json` with your normal file tool. No new tool is involved.
2. **No model available?** Run the keyword fallback: `python3 -m adventure_maker.brief "<prompt>"` (or call `brief.from_prompt(prompt)` in code). It always returns a valid brief for any prompt up to 600 characters. Its `filled_by` is `fallback` and its `assumptions` list every default it chose.
3. **Check it**: `python3 -m adventure_maker.brief --check brief.json` prints one summary line, or one error line. `--needs brief.json` prints the need list that the asset steps resolve.
4. **Fix errors by changing the brief, not the rules.** Every error is one line: a code, the field path and what to do.

### Fields

| Field | Kind | Notes |
|---|---|---|
| `format` | `"hermes64-brief/1"` | |
| `prompt` | text, at most 600 | the user's words, kept as a record; never executed, never used as an id |
| `filled_by` | `model` / `fallback` / `user` | |
| `setting.genre` | closed word | `adventure fantasy medieval fairy-tale sci-fi space cyberpunk steampunk post-apocalypse horror mystery noir western pirate underwater desert volcano jungle polar ancient samurai viking candy dream cozy modern school sports` |
| `setting.genre_hints` | up to 6 closed words | any genre, or `platformer puzzle racing combat stealth exploration collectathon boss-rush survival arena magic wizard haunted robot toy mushroom dinosaur dragon ghost treasure heist farming cooking music` |
| `setting.place` / `era` / `scale` | short text (80/40/60) | labels such as "wizard tower and grounds", "small outdoor hub + 2 interiors" |
| `mood.time` | closed | `dawn morning noon afternoon golden-hour dusk night` |
| `mood.weather` | closed | `clear cloudy rain storm fog snow wind sandstorm ash underwater none` |
| `mood.season` | closed | `none spring summer autumn winter` |
| `mood.tone` | closed | `adventurous cozy mysterious eerie heroic playful whimsical melancholy tense serene epic gritty hopeful dreamy` |
| `palette_mood.dominant` / `accent` | hue word | `red crimson orange amber gold yellow lime green emerald teal cyan blue indigo purple violet magenta pink brown tan grey silver white black` |
| `palette_mood.support` | up to 3 hue words | must not repeat the dominant hue |
| `palette_mood.value_key` | `low` / `mid` / `high` | overall darkness |
| `palette_mood.saturation` | `muted` / `moderate` / `rich` | still capped by the gates |
| `build_types` | up to 12 short texts | structures and places: "tower", "library interior" |
| `props[]` | up to 40 | `want` (at most 60 characters; only ever a search phrase and a report label), `count` 1-32, `importance` `key` or `dressing`, optional `source` |
| `characters[]` | up to 16 | `want` (at most 80), `role` `player npc enemy boss companion crowd`, optional `count`; handed to the character system |
| `sources.user_assets[]` | up to 32 slots | `slot` id, `kind` (`model texture logo image audio character`), `for` (what it is used for), optional `file` (project-relative path), `licence` (SPDX id or `unknown`), `credit`, `rights_confirmed` |
| `sources.allow_generate` | true/false | may the plugin write new pieces for missing needs |
| `ip_terms[]` | up to 16 | `term`, `kind` (`franchise person brand`), `generic` (the stand-in used instead) |
| `unrecognised` | up to 16 words | prompt words nothing could classify; they show up in the report as gaps to check |
| `assumptions` | up to 24 lines | report only: what was defaulted and why; nothing reads it to build |
| `tags` | derived | written by `normalise()`; a hand-edited value is refused |

Lenient input: `normalise()` lowercases closed words and accepts common spellings ("warm gold" becomes `gold`, "sunset" becomes `dusk`, "sci fi" becomes `sci-fi`, "cosy" becomes `cozy`). It fills `season` (`none`), `saturation` (`moderate`), empty lists and `allow_generate: true` when they are missing, merges duplicate props, and drops the dominant hue from `support`. Everything else must be right.

### Hard rules (validator)

- No unknown fields anywhere. `texture_size`, `neon_limit`, `triangles` and the like are refused (`brief_unknown_field`).
- Text fields refuse quality or override wording: triangle or polygon counts, `4k`/`8k`, texture size or resolution, photoreal, ray tracing, PBR, normal maps, ignore/override/bypass (`brief_style_override`). Describe the thing, not the rendering.
- No `ip_terms` entry may appear in `place`, `era`, `scale`, `build_types`, prop or character `want`, slot ids or `for`, `unrecognised`, or its own `generic` (`brief_ip_leak`).
- User asset files are project-relative (`assets/user/logo.png`): no absolute paths, drive letters, backslashes or `..`. The extension must suit the kind (models `glb gltf obj`, characters `glb gltf`, images `png jpg jpeg`, audio `wav ogg mp3 flac`) (`brief_slot`). Whether JPEG is converted later is a separate decision (plan 07, Q4).
- Closed words outside the lists are refused with the nearest allowed words (`brief_word`).

Error codes: `brief_prompt brief_type brief_unknown_field brief_missing_field brief_empty brief_too_long brief_too_many brief_word brief_count brief_format brief_slot brief_palette brief_tags brief_style_override brief_ip_leak brief_missing brief_invalid_json`.

### The keyword fallback, honestly

`from_prompt` is a deterministic keyword reader: phrase and plural aware, with tables for genre, hints, time, weather, season, tone, colours, build types, props and characters, and a default row for every genre. It is a floor, not a mind:

- It reads words, not meaning. "A lighthouse that is *not* haunted" still gets the haunted hint. A model-filled brief is better whenever one is available.
- Unknown nouns are never replaced. After a number ("three zorblaxes") they become a `key` prop; otherwise they go to `unrecognised`.
- The franchise list is a small safety net of very common names. **The model is the primary detector** of franchise and real-person names and must record them in `ip_terms`.
- Idioms are handled on purpose: "golden hour" is a time, not the colour gold; "fairy tale" does not add a fairy; "ghost town" does not add a ghost.

### Needs

`brief.needs(brief)` turns the brief into one row per need: palette, sky, each build type, each prop, each character, each user slot and each unrecognised word. Each row has an `id`, a `kind`, an `importance`, a `count` and a `route`:

- `assets` goes to the asset tiers: the kit library, remapped to the mood, then generated, then converted (plan 07 sections 2.4-2.8).
- `characters` goes to the character system.
- `audio` goes to the audio import.
- `user` is your own file.
- `check` is an unrecognised word to look at.

Nothing is dropped. The asset report (plan 07 section 2.11) has one line per need.

## What exists today and what does not

Exists (this lane): the contract, the validator and normaliser, the keyword fallback, the needs list, tests with known-bad controls, the wizard-purple-world brief and 20 varied prompt fixtures.

Not yet:

- `/hermes64 new` does not write `brief.json` yet. The exact hunk is in `docs/anyprompt/newgame-brief.patch` for the integrator. It writes `<project>/brief.json` (keeping one the agent already wrote), adds `paths.brief` and a one-line `brief` summary to the game card, and rewords the no-match style reason. It adds no reply line, because `tests/test_newgame.py` pins the reply at 4-5 lines; a `Brief:` reply line needs that test updated in the same change.
- The brief does not change the chosen pack or build anything yet. Mood packs, tags, generated pieces, conversion and the asset report are later lanes (A2-A8).
- Until then, an unmatched prompt still gets the default pack. With the patch applied, the style reason says so plainly ("no shipped pack matches this fantasy prompt yet, so the default; brief.json records what was asked") instead of silently.

Platform note: the brief itself is pure Python and runs anywhere. Later tiers that run agent-written generators or the converter need the build sandbox, which is macOS-only today.
