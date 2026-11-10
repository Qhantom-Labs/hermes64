# Proof badge

A one-line, deterministic summary of the reports a game already has:

```text
proof-checked · 2 bots played · style gate not run · 0 softlocks · PLAYABLE (headless)
```

`/hermes64 new` prints it, `hermes64_demo(premise=...)` returns it (`badge`, `proof_badge`), and it is stored in the new game's `project.json` under `proof_badge`. The code is `adventure_maker/badge.py`; tests are `tests/test_badge.py`.

## Fields and sources

| Part | Source report | Possible values |
|---|---|---|
| proof | checker `proof.json` (`status`) | `proof-checked` (proved), `proof conditional`, `proof inconclusive`, `proof FAILED (rejected/invalid)`, `proof not run` |
| bots | playtest `report.json`: `paths` (one winning-path bot per reachable ending) plus the explorer bot when `explorer.h64movie.json` was recorded | `N bots played`, with `(K winning paths FAILED)` and `(K STUCK)` when the report shows them, or `bots not run` |
| assets (MERGE5; only when supplied, by `/hermes64 new`) | its `build_assets` stage: `hermes64_build_assets` (seed 7) with the configured builder, `.maker/runs/assets-…/assets/report.json` | `assets built`, `assets build FAILED`, `assets NOT BUILT (<reason>)`, e.g. `(Blender not found; install Blender or set builder to auto with a numpy Python)` |
| style gate | measured room-look gate `style-gate.json` from `hermes64_open(screenshots=true)` | `style gate pass`, `style gate FAILED (k/n rooms)`, `style gate not run` |
| style audit (replaces the style-gate slot when supplied) | `audit.json` from `hermes64_check(action="audit")` (docs/STYLE-AUDIT.md) | `style audit PASS/WARN N/100`, `style audit FAIL N/100 (k/n rooms)`, `style audit not run (no display)`, `style audit FAIL (static check; render not run)` |
| softlocks | checker `softlock_count` | `0 softlocks`, `N SOFTLOCKS`, `softlocks unknown (search incomplete)`, `softlocks not checked` |
| tier | playtest `verdict`, plus `display`/`render_verified` | `SOLID`, `PLAYABLE`, `ROUGH` or `BROKEN`, then `(headless)` or `(rendered)`, or `tier not run` |

If the proof and playtest name different `game_hash` values the badge adds `REPORTS FROM DIFFERENT BUILDS`.

## Honesty rules

- AUDIT lane: `/hermes64 new` now runs the style audit after the playtest when a window can open and passes it to the badge; without a window the slot reads `style audit not run (no display)`. A FAILED audit keeps `ok` false, exactly like a failed style gate. `from_paths(..., audit=<path or dict>)`.
- MERGE5: `/hermes64 new` builds the room assets (`build_assets` stage, after `check`, before the playtest, play runtime and audit), so a fresh game is no longer audited as unbuilt cutaway rooms. The badge carries an `assets` slot just before the style slot, and `ok` stays false unless the assets were built. The configured builder is kept (Blender unless `builder` is set): with no usable builder the stage reads `not_run`, the slot reads `assets NOT BUILT (...)` and `next` starts with `hermes64_build_assets`. A failed build reads `assets build FAILED` with the error in `assets.reason`. `from_paths(..., assets={'status', 'builder', 'reason', 'report_path'})`; other callers pass no assets row and their badge text is unchanged. An audit FAIL after a successful build is a real finding (for example `pack n64_v0 builds no room shells`), not a missing build.
- It never claims more than its inputs show: a missing report reads "not run", a failed gate is printed in capitals, and the tier is copied from the playtest, never raised.
- `ok` is true only when the proof is `proved` with exactly 0 softlocks, the tier is `SOLID` or `PLAYABLE`, every winning-path bot passed, no bot got stuck, the style gate and style audit did not fail, the assets (when supplied) were built and the reports name one build.
- `PLAYABLE (headless)` means bounded headless bots finished, not that rendering, performance, fun or human winnability were checked. `/hermes64 new` runs headless only, so its badge says `style gate not run`; the gate needs a rendered `hermes64_open` with `screenshots:true` (it writes `style-gate.json`). The badge in `project.json` is a snapshot from creation and is not updated afterwards; `badge.from_paths(proof=…, playtest=…, style=…, base=project_dir)` recomputes it from later reports.
- Same inputs give the same badge: there are no clocks or random values in it.

## JSON shape

```json
{
  "format": "hermes64-proof-badge/1",
  "text": "proof-checked · 2 bots played · style gate not run · 0 softlocks · PLAYABLE (headless)",
  "ok": true,
  "proof": {"status": "proved", "complete": true, "softlock_count": 0},
  "bots": {"played": 2, "winning_paths": 1, "winning_passed": 1, "explorer": true},
  "style_gate": {"status": "not_run"},
  "softlocks": "0 softlocks",
  "tier": {"verdict": "PLAYABLE", "headless": true},
  "game_hashes": ["<64 hex>"],
  "sources": {"proof": ".maker/runs/check-…/proof.json", "playtest": ".maker/runs/playtest-…/report.json"}
}
```

`project.json` at a new game's root is the game card written by `/hermes64 new` (premise, style, badge, report paths, play command, doctor findings). It is not the portable source-project manifest (`contracts/project/1.0.0.json`), and no tool reads it: the current build pointer stays `.maker/current.json`.
