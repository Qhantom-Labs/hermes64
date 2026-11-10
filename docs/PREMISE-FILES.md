# Story files and reusable templates

`/hermes64 new "Keep Under Siege: defend the castle"` uses the bundled neutral arena story. You can also use `/hermes64 new "Your title" --story your-story-id`. The compact tool schema is unchanged: `hermes64_demo` finds a story by title, without another argument.

## Data and provenance

Place `premise.json` and optionally `prompt.txt` in `<games folder>/premises/<id>/`. The installed `premises/` folder supplies neutral examples. User-folder stories take precedence; duplicate matching titles within one folder are refused. Matching uses the exact case-insensitive title before the first colon, not fuzzy similarity. An explicit `--story` selects the id. The response and `project.json` show `Story: <id> (premise file, matched by title)` or the explicit selection, with the source file SHA-256. No story match means no `Story:` line.

The closed contract is `contracts/premise/1.0.0.json`. Files are at most 256 KiB; ids are slugs, symlinks and traversal are refused. A story contains values, never executable scripts, imports or filesystem paths. Audio uses AUDIOPIPE's `music.default/menu/boss/results/scenes/waves/events`, `voice`, `cues`, and `mix` slot names. It names asset ids, not music files. Actual media enters via the import/overlay owners.

## Templates

- `two_room_collect_v1`: the default two-room find-and-return starter.
- `arena_run_v1`: opening, arena rooms and finale from pack data, challenge/checkpoint per arena, gated forward doors, reversible chain, final interaction. Two distinct arena keywords select it conservatively; a lone “rescue” or “time” does not change the starter.
- Arena room data must exist for the selected pack. `castle_keep` is bundled first. Missing room data is a clear refusal before project creation, never an undressed placeholder fallback.
- Each wave index supports three spawns. Larger authored groups split into consecutive groups; more than eight groups or 24 enemies per encounter are refused, not truncated.

## Room interchange

Installed generation reads `kits/packs/<pack>/rooms.json`, `hermes64-pack-rooms/1`: a bounded array of `{id, roles, room, presentation, anchors, slot_pieces, tri_estimate}`. `room` is compiled story-room data; `presentation` is its kit dressing. Anchors: `hero_start`, `checkpoint`, positive-volume `arena: {min,max}`, at least eight `spawns`, three `boss` positions, `interact`, optionally `captive`. Positions are finite xyz metres. Authored door walls and positions stay unchanged; ids `forward/back` (or `north/south`) supply the two chain ports. Character ids are rebound to the chosen hero, not an assumed compiler demo id.

Authoring source plans may use `hermes64-room-plans/1`, but they must be baked before packaging. `python3 -B -m tools.pack_rooms --check` pins the neutral precompiled output. The installed plugin does not import a developer-only kit compiler. A room pack from another lane must provide this baked form and anchors; copying its compiler import name into JSON does not make that code safe or shipped.

## Honest readiness

Combat proof remains conditional. A completed real-input module bot with matching build hashes, nonempty successful paths, a physical receipt and all required modules can qualify the badge without turning it into logical proof. Failed assets or audit still mean `new_game_needs_work`. The current castle slice is physically completed but fails the rendered audit, including runtime gate-marker placeholders. Human art approval is not implied.

Fields awaiting their runtime owners are listed in `Not yet applied` and `template_pending`; recording a requested scene, clock, moveset or slot is not implementing it. Pack `hero_start` is stored as `player_start`, but the current runtime still uses its default opening entry; the source-only runtime-owner patch is not applied here. See the lane result for integration dependencies. The showcase story and media are external user data; the package includes only neutral story files.
