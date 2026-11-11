# MERGE HANDOFF (MERGEPREP to the final integrator)

**Branch:** `mergeprep-lane` (worktree `wt-mergeprep`), started from tag `rc3-m15` (`803dfa54`).
**Product head:** `42a8b371`; the commits after it change only this file and the ledger.
**Records:** model header `docs/MERGEPREP-MODEL.md`; every merge, conflict and rule in `docs/MERGE-LEDGER.md`.
**Harness:** `docs/merge6/mergeprep/` (repository-only). **Evidence:** `evidence/mergeprep/` (git-ignored).

## What is in

The commissioned lanes are merged in order. Each is a normal `--no-ff` merge with its own ledger row:

| Merge | Lane | Head | Note |
|---|---|---|---|
| M1 | rc3b | `546d92a5` | |
| M2 | bfix | `aa569b4f` | |
| M3 | reuse | `7e635d7d` | |
| M4 | win3 | `5d71ede0` | |
| M5 | ui5 | `09e6a0e8` | |
| M6 | scale | `4d839a77` | still running |
| M7 | chars4 | `be767f1c` | |
| M8 | slide | `0b2a808f` | |
| M9 | charbind | `82bca4bd` | |
| M10 | gaps2 | `c6607b1b` | |
| M11 | feel4 | `0ac0e315` | |
| M12 | ceofix | `4ba9792f` | |
| M13 | waiver | `23a34774` | |
| M14 | detail | `bacf2dfc` | brings orch2 and orch |
| M15 | tiers | `3384280a` | |
| M16 | orch2 | `fcf5c40f` | skipped: detail already contains it |

M17 merges INTEG6's final `rc3-lane` `32e87ff5`, recorded as complete. It holds `rc3-m16` (`a05d18e9`), `rc3-export` (`b13aca5b`) and INTEG6's record, so this branch contains `rc3-m16`.

## Commands (in `wt-rc3`, branch `rc3-lane`, local only)

```
git rev-parse --short rc3-lane                     # 32e87ff5 = INTEG6's final record
git merge-base --is-ancestor rc3-lane mergeprep-lane && git merge --ff-only mergeprep-lane
```

That is a fast-forward, with no merge commit and no conflict. Against `rc3-m16` itself it is also a fast-forward. If `rc3-lane` has moved, run `git merge --no-ff mergeprep-lane`.

These files are touched both by INTEG6's M16 (and later) commits and by this branch. All are already reconciled here (rows M14-owner and M17):

- `adventure_maker/newgame.py`: `split_create` and the `--create` branch are byte-identical to INTEG6's.
- `__init__.py`: `hermes64-create` sits after `hermes64-places`.
- `docs/PACKAGE-CONTENTS.md`: the ORCH row plus stack B's studio row.
- `tests/test_create_flow.py`, `tests/test_schema_budget.py`: INTEG6's fixes are applied.
- `adventure_maker/export.py`: INTEG6's text-resource setting plus stack B's UTF-8 I/O.

## Re-verify

```
MERGEPREP_TMP=<real dir outside the tree, not /var> /usr/bin/python3 -B docs/merge6/mergeprep/suite.py LABEL
MERGEPREP_TMP=... /usr/bin/python3 -B docs/merge6/mergeprep/step.py LABEL test_schema_budget
MERGEPREP_TMP=... /usr/bin/python3 -B docs/merge6/mergeprep/fox.py LABEL
```

What each one does:

- `suite.py`: the sharded plugin suite. It runs a partition proof first, uses the unchanged 1,800 s guard, then runs `tests_story`.
- `step.py`: the schema budget and the 15 legacy replays.
- `fox.py`: builds the package, runs `check_install`, then the Blender-hidden fox flow.

## Re-merge rows (lanes still being written)

| Row | Lane, merged at | State when checked | Do |
|---|---|---|---|
| R1 | scale-lane `4d839a77` (model header only) | running, 10 uncommitted files | Merge with `git merge --no-ff scale-lane`. **Schema headroom is 0**, so any copy it adds goes into its skill or is trimmed (TOKEN-DIET.md, MERGEPREP section). |
| R2 | detail-lane `bacf2dfc` | no DETAIL-RESULT.md yet; `tools/detail_proof.py` uncommitted | Merge. If it edits `skills/hermes64-create/SKILL.md`, rebuild the tiers 2.1.0 candidate (TIERS-HUNKS.md). |
| R3 | feel4-lane `0ac0e315` | FEEL4-HUNKS.md and FEEL4-RESULT.md uncommitted | Merge. If `input/controls_hint.gd` changes, keep the M11-unify adapter: it draws through UI5's overlay only. |

## Not resolved here (owner decisions and findings)

Nothing is left conflicted in the tree.

1. **nbchars parity verdict reads STALE.** The merged generator bytes differ from every pinned fingerprint. `PARITY.json` carries INTEG6's M15b `404a94f6`. A parity run with `--write-verdict` is needed, which is a re-pin, so it was not done here. This is the only failing focused test.
2. **ORCH2's `room-keepsake-floor` hunk is applied (row M14-owner2).** Rendered goldens of games whose keepsake model has no authored position would move. Re-bless if wanted.
3. **UI5's pause menu does not list the camera keys** (FEEL4's own strip did). Adding them re-baselines UI5's pause golden.
4. **M14-fix (`e5d88e05`): with PLACEMAKER present, a brief that routes gameplay modules now keeps the create pattern.** Before this, ORCH's archetype took precedence and every module was refused. Revert that one commit to restore ORCH's precedence.
5. **The schema is at 27 tools / 6,000 tokens after same-facts copy trims (M15-fix).** The budget and validation pins are unchanged, but there is no headroom.
6. **`tools/merge6_run` puts TMPDIR inside the tree.** The meshy ingest tools refuse output inside a git tree, so four meshy1/2/3 tests fail under it by design. `suite.py` and `step.py` use `MERGEPREP_TMP` outside the tree instead.
7. **The fox flow ran headless** (`HERMES64_DISPLAY=0`, as in `test_bfix_host`'s smoke), so the style audit did not run. BFIX's windowed proof did run it.

## Measured

| Check | Result |
|---|---|
| Per-merge focused tests | 47 to 331 per step. Every failure is classified in the ledger and either fixed in its own commit or listed above. |
| Legacy replays | 15/15 identical to the `rc3-m15` rows at every step that ran them (M1 to M17 and the final step). |
| Schema budget | 5,952 (`rc3-m15`) -> 5,946 (M1) -> 5,978 (M7) -> 5,990 (M13) -> 6,010 (M15) -> **6,000** (M15-fix), 27 tools. |
| Full plugin suite at `ae99817d` | **1,627 tests** in 6 shards (215/270/201/258/270/413). Partition proof OK, counts match, no timeout, longest shard 311 s (guard 1,800 s). `tests_story`: 184 OK. |
| Full-suite failures (3) | `test_merge4_play...one_frame_time_line`: inherited from stack A, in every INTEG6 plugin stage. `test_nbchars...verdict_is_current`: finding 1. `test_merge4_windows_load.test_probe`: inherited from waiver-lane (the doctor imported numpy through `rigkit.waiver`), fixed in `42a8b371`. |
| After the fix (`42a8b371`) | 166 OK, including `test_merge4_windows_load` and the packaged-host BFIX smoke. Schema 27/6,000; replays 15/15. |
| Windows gate | windows_gate PASS (186 runtime files, 0 hits); win3 audit 0 findings. |
| Package | `tools.package` OK; `check_install` PASS: 5,978/5,978 files verified (sha256), cameo present, source `ae99817d` (clean tree). Not published. |
| Fox flow (Blender hidden, packaged plugin, real Hermes dispatcher) | Badge line, verbatim: `Badge: proof-checked · 2 bots played · assets built · style audit not run (no display) · 0 softlocks · PLAYABLE (headless)`. Play boot: `BOOT game=fox_searches_village_lost version=1.1.0 rooms=2 godot=4.6.2-stable (official) display=headless`, exit 0. |
