# WAIVER merge hunks

Branch `waiver-lane`, cut from `charbind-lane` 82bca4bd. Three normal `--no-ff` merges, local only:

| merge | commit | conflicts |
|---|---|---|
| meshy2-lane `9cc1427c` (Teknium v2 ingest, `tools/meshy_ingest.py`, MESHY-INGEST.md) | `27950b4b` | none: 27 files added, no file changed on both sides (base `c4551b33`) |
| meshy3-lane `bcc8c822` (girl v2 ingest, `tools/meshy3_ingest.py`, MESHY3-INGEST.md) | `f474c31e` | none: base `dc2d546c` (meshy1 5b) holds the shared `tools/meshy1_*`, `tests/test_meshy1.py` and MESHY1 docs, which neither side changed |
| slide-lane `0b2a808f` (continuous-phase locomotion, with chars5 B1-B7) | `cad7eba3` | 1 conflict, below; 4 files changed on both sides merged automatically |

## Both ingest tools kept

`tools/meshy_ingest.py` (meshy2) and `tools/meshy3_ingest.py` (meshy3) are different files with different code. Both
stay, each with its own builder modules, tests (`tests/test_meshy2.py`, `tests/test_meshy3.py`) and docs. meshy3
does not carry `tools/meshy_fusion.py`; the meshy2 copy is kept as added. MESHY3-INGEST.md section "comparison with
meshy2-lane's meshy_ingest.py" describes the overlap; nothing was folded together here.

## Conflict

| file:lines | class | kept | why |
|---|---|---|---|
| `runtime/godot/actors/assets.gd:45-58` | disjoint intent | both | CHARBIND added `cast_character(id)` (a scene actor's project cast row); chars5 added `locomotion_block(path)` (the baked base_v1 block from the file's root extras, read by `actor.set_locomotion` at line 38). Two separate functions at the same insertion point: CHARBIND's first, then chars5's, each unchanged |

## Changed on both sides, merged automatically (each checked for both intents)

| file | charbind side | slide side | merged |
|---|---|---|---|
| `adventure_maker/character_tools.py` | bind holds a file to its own clips, `plain_reason`, `used_by` | `locomotion` action, `bind legacy`, `waive_flight` for run flight keys, style lock fix | both present (bind keeps CHARBIND's checks, then chars5's flight split) |
| `adventure_maker/wire.py` | scaffold / audio copy (earlier integrations) | `hermes64_character` description gains "locomotion = bake run + walk" | both present; WAIVER later shortened the character copy (TOKEN-DIET.md) |
| `runtime/godot/actors/bridge.gd` | `rest_clip()`: authored room clip (seated captive) | baked locomotion `drive()` for the player and followers | both present (lines 23-29 and 43-55) |
| `tests/test_schema_budget.py` | validation pin after FIRSTRUN/AUDIOPIPE | character pin after chars5 | both present; WAIVER then moved the character and hub pins deliberately |

## Semantic interaction found by the focused tests (no text conflict)

charbind-lane `673de3de` (in this branch's base `82bca4bd`) made the rig kit validator read the run's flight keys from
the base_v1 locomotion block (`declared_flight`). The validator no longer reports those keys as
`mesh.silhouette.floor` errors. meshy1, meshy2-lane, meshy3-lane and chars5 (via slide-lane) pinned the older result,
in which the six flight keys of the base_v1 run failed the floor check and the locomotion check then waived them.
On the merged tree, 4 focused tests failed. They fail the same way at the merge commit `cad7eba3`, before any WAIVER
code: a scratch export of that commit ran them with the same private and promo folders linked.

| test | failure at `cad7eba3` | change here |
|---|---|---|
| `test_locomotion.Rollout.test_baked_cast_meets_the_rig_contract` | `0 != 6` waived flight keys (tavi) | counts the six keys as waived (old validator) or declared (merged validator); the block-less source must have neither |
| `test_meshy3.PrivateModel.test_the_rig_validator_does_not_pass_this_character` | errors `['mesh.deformation']`, pin had `+ mesh.silhouette.floor` | pin is `['mesh.deformation']`; the docstring says why |
| `test_meshy2.PrivateModel.test_committed_measurements_are_this_build` | `clips` differ | `docs/measurements/meshy2_teknium_convert.json` re-pinned |
| `test_meshy1.PrivateModel.test_committed_measurements_are_this_build` | `clips` differ | `docs/measurements/meshy1_convert.json` re-pinned |

The re-pin is made by `tools/waiver_repin_validator.py RECORD FRESH`. FRESH is the same tool's output on this tree:
- MESHY1: a fresh `tools/meshy1_build.py --targets 698 1200` run;
- MESHY2 and MESHY3: the ingest reruns in `docs/measurements/waiver/`.

For each target it replaces only `clips/validator`, and it refuses if anything else in `clips` differs. In all
three records, per target (698 and 1200), exactly three fields changed:
- `checks_ok.silhouette` false -> true;
- the `mesh.silhouette.floor` entry (count 6, first `run@5`) removed.

All GLB hashes in the records are unchanged: the fresh MESHY1 build and the MESHY2/MESHY3 reruns reproduce them. The
MESHY3 record is re-pinned the same way for consistency; its committed-measurement test does not compare `clips`.

`test_nbchars.Selection.test_committed_verdict_is_current` (STALE) fails at `cad7eba3` and here (run in this lane).
CHARBIND traced it to the chars6 merge `24a6a977`. It needs the published oracle to re-run, so it is not changed.

The prose in MESHY1/2/3-RESULT.md (written by those lanes) still describes the flight-key floor failure. It is not
edited here.

## Verified after the merges

- `tests.test_schema_budget`: 8 OK at `cad7eba3` (27 tools, 5,984 tokens).
- `tests.test_charbind_validator` + `tests.test_character_bind`: 11 OK at `cad7eba3`.
- The base_v1 bake in this branch equals the pinned tool: `git diff be767f1c HEAD -- adventure_maker/locomotion
  tools/locomotion_bake.py rigs` is empty. slide-lane changed only the runtime, its tests and tools around the bake.
