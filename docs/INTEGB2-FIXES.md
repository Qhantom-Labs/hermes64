# INTEG-B2 mechanical fixes

Main commissioned these corrections at `c9d2e5ee`; no checker, threshold, scanner rule or allowlist was changed. Historical S1 failure receipts remain intact.

| Defect / before | Minimal correction / after evidence |
|---|---|
| `wizard-purple` names `apprentice`, but `court.character_ids` only contains `archivist`. Reproduced by the unchanged every-example cast invariant (10-test red run, two failures). | Add `room: court` to the apprentice in **world DATA** and regenerate its authored spec exactly (start placement `[2,0,2]`, cast membership apprentice + archivist). Compiler/checker untouched. Additive compiled game, proof (`proved`), start save and spec under `merge6/integb2/wizard-start/`; prior AUTHOR receipts remain historical, not overwritten or recertified as native runs. |
| `audio_import.py:87` unconditionally probes three POSIX ffmpeg paths, including on Windows. | Move platform candidate construction into `platforms.ffmpeg_candidates`: only Windows paths on win32, same three POSIX fallbacks in the same order on macOS/Linux. Configured/bundled/PATH precedence unchanged. Regression red: helper absent (two failures); configured-path and no-window controls already pass on baseline. |
| `audio_import.py:511` uses positional UTF-8 `write_text`; Windows translates LF to CRLF. | `write_bytes(...encode('utf-8'))` gives explicit encoding and LF bytes on both platforms, identical macOS JSON output. |
| `taxonomy.py:325,521` rely on locale for JSON reads. | Explicit `encoding="utf-8"` for cached tags and `--brief` input; classification semantics/data untouched. |
| Harness names nonexistent `tests.test_templates`. | Resolve real modules: `test_templates_arena`, `test_templates_combat2`, `test_templates_driver`, `test_templates_premise`, `test_templates_prompt`. Expanded focused set also includes taxonomy, audiopipe and four portability regressions. Initial corrected focused run: **197 tests, exit 0**; complete final-tree rerun follows in verification index. |

## Evidence and re-pins

- Red source/data run: `merge6/runs/20261110T225432926201Z--integb2-s1-red/`: 10 tests, two failures. The earlier argparse invocation failed before launching tests (`--timeout` must precede name); that is harness error, not product RED.
- Helper API regression red: `merge6/runs/20261110T225519866232Z--integb2-portability-red/`: four tests, two failures, two baseline-passing preservation controls.
- Corrected focused selection: `merge6/runs/20261110T225615862159Z--integb2-s1-focused/`: 197 tests, exit 0. The authored DATA was subsequently normalized to exact world-compiler output; the acceptance run repeats the whole selection.
- Unmodified Windows source gate after correction: **149 runtime files, zero hits, zero stale allow rows**. Seven existing parity-frozen findings remain under the gate's original policy; no waiver added.
- Additive identity ledger: `merge6/integb2/wizard-start/REPINS.json`. Wizard spec hash `4a284c8b…` → `13519301…`; game hash `019d51fb…` → `9f7d2cc1…`. These are regenerated identities caused only by the commissioned DATA placement. No input/movie/state expected hash changes. Historical WIN2 four-example re-pins remain in `INTEGB-S1-REPINS.json`.
- Audio CREATE_NO_WINDOW patch was already applied in the resumed checkpoint; explicit four-subcase test covers Windows/POSIX × piped/no-input calls. Locomotion target absent here; patch remains unapplied for stack A composition.

## First full-run harness corrections

The first resumed full plugin run collected **990 tests**, with two failures, three errors and four skips (receipt in the index as `s1`). Three new package errors/failures correctly refused the integrator's newly written fixture-custody ledger because its absolute provenance paths were placed in shipped docs. All internal receipts were moved to the **already-excluded** `docs/merge6/integb2/` namespace; privacy rules were not changed. The AUTHOR native test also used system Python without isolated numpy: the existing M9 test already accepts `HERMES64_TEST_PYTHON`, so the rerun supplies the pre-existing Hermes venv (Python with numpy 2.4.3 / Pillow 12.3.0, verified using `-I`). No install, test edit or production builder change. The inherited missing MERGE3 receipt remains separate. Full rerun follows, not a selective-green substitution.

Final per-step counts, replay comparisons, schema and packaged-host gates are recorded in `INTEGB-VERIFICATION.json`. No native-Windows, human art/feel, dependency installation or real Godot-download acceptance is inferred from Mac simulation.
