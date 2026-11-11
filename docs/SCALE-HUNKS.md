# SCALE shared hunks and trial merge into mergeprep-lane

Trial: scale-lane `dfb4595c` merged with mergeprep-lane `428ce0b9` in a throwaway `git clone --shared` (no ref
or worktree of the real repo touched). `git merge` reports 2 conflicted files. The other 5 shared files auto-merge.
Re-checked at the final scale-lane head with `git merge-tree --write-tree --name-only`: the same 2 files conflict.
The later commits touch only `room.gd`, `room_scale.py` and docs.

| File | Merge | What SCALE changes there |
|---|---|---|
| `adventure_maker/newgame.py` | **4 conflict blocks** + 2 semantic fixes | `create(..., scale=None)`, room-scale pick/apply after `starter_spec`, `Rooms:` summary line, card `rooms`, `parse(include_scale=)`, `command()` passes the scale word |
| `tests/test_newgame.py` | **1 conflict block** + line count | the summary has one more line (`Rooms:` at index 2) |
| `adventure_maker/brief.py` | auto | optional `setting.room_scale` word, `from_prompt` keyword |
| `adventure_maker/premise_packs.py`, `contracts/premise/1.0.0.json` | auto | optional `room_scale` enum |
| `contracts/brief/1.0.0.json` | auto | optional `setting.room_scale` |
| `runtime/godot/view/presenter.gd` | auto | `apply_room_look()` legacy-look branch: per-room `presentation.fog` (near/far, optional colour, max, sky `fog_scale`) |
| `runtime/godot/view/room.gd` | auto | `compose_exterior()`: `presentation.layout_dressing` skips pack clusters/rhythm; framing moves beside `presentation.clear_core` |

New files (no conflicts): `adventure_maker/room_scale.py`, `adventure_maker/room_layouts.json`, `tests/test_room_scale.py`,
`tools/scale_proof.py`, `docs/SCALE-*.md`, `docs/SCALE-MERGE.diff`.

## Resolution (verified on the trial tree)

`docs/SCALE-MERGE.diff` is the full SCALE delta of the two conflicted files on top of mergeprep-lane `428ce0b9`.
On conflict: `git checkout --theirs adventure_maker/newgame.py tests/test_newgame.py` (mergeprep side), then
`git apply docs/SCALE-MERGE.diff`. Block by block:

1. `def create(...)`: mergeprep's REUSE docstring with SCALE's signature `story=None, scale=None)`.
2. After mergeprep's `base = ...` / `spec = starter_spec(..., games_root=root)`: insert SCALE's block
   (`room_scale.pick` + `room_scale.apply` + `scaled['reason']`). Drop SCALE's `if record: ...premise` lines:
   mergeprep's `spec_for()` stamps the premise.
3. In mergeprep's split-out `finish()`: SCALE's `lines.insert(4, 'Story: ...')`, followed by mergeprep's
   Earlier / `Rooms: your games folder` / Audio lines.
4. `command()`: mergeprep's create-flow split. The `/hermes64 new` path uses
   `parse(raw, include_story=True, include_scale=True)` and `create(..., scale=scale)`.
5. `tests/test_newgame.py`: mergeprep's card/blender assertions with indices +1, SCALE's `Rooms:` assertion at
   `lines[2]`, `assertIn(len(lines), (5, 6))`, and the Blender note at `lines[5]`.

Two semantic fixes are needed even where git merges cleanly. They are already in `docs/SCALE-MERGE.diff`.

- **NameError trap:** git places SCALE's `room_scale.card(scaled)`, `room_scale.summary_line(scaled)` and
  `'rooms': card['rooms']` inside REUSE's `finish()`, where `scaled` is undefined. The fix passes `scaled` as
  the last argument of `finish(...)` (default `None`, which means not planned) and adds `from . import room_scale`
  there.
- **Renamed projects:** REUSE's `spec_for(candidate)` rebuilds the starter for a taken name. Without a fix, a
  renamed project silently loses the scaled rooms. The fix re-applies `room_scale.apply(...)` for
  `candidate != base`.

Trial tests after resolution (`TMPDIR` outside /var, `HERMES64_TEST_PYTHON=/opt/homebrew/bin/python3`):
`test_room_scale test_newgame test_brief test_schema_budget test_templates_premise test_reuse test_place` all pass:
**104 tests OK** (67 s). `test_create_flow` was added in a second trial run; its result is in SCALE-RESULT.md.
Schema budget: mergeprep-lane alone gives 27 tools / 6,000 tokens, and the trial merge gives 27 tools / 6,000.
SCALE adds 0 tokens and no tool descriptions; guidance goes in the `adventure-maker-verification` skill.

## Not integrated (stack A owners)

- `create_flow` (`/hermes64 new create`, `command_create`) builds rooms with kit compilers / placemaker and
  `create_patterns.json`. It does not read the dial. The brief contract accepts `setting.room_scale`, so a
  create-flow brief carrying it validates. Pattern sizes still ignore it, and on that path the scale word is
  parsed as a style. Wiring it means passing `brief['setting'].get('room_scale')` into `stage_rooms`' pattern
  choice and scaling its sockets. Not done, not verified.
- `arena_run_v1` / games-folder rooms (`rooms_source`): the dial leaves them alone (`Rooms: <scale> not applied
  (...)`). Both `Rooms:` lines appear when a games-folder room set is used.
