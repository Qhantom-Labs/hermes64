# BLOCKED: retained starter style lock needs an owned revision

Actual model: `gpt-6-astra`; provider: `openai-codex`. Observed 2026-11-08 09:38 EST.

The raw `adventure_modules.verify regression-01` run executed all 136 story tests (pass) and all 175 plugin fast tests (two errors). Existing canonical game/proof/save/room digests for four Last Light/Thaw sources remain byte-identical to `baseline-01`. Module data tests and the 3-edit benchmark pass, but the whole fast suite is **not green**.

Failing retained tests:
- `test_project_model.ProjectTests.test_copied_project_resolves_from_its_own_root`
- `test_project_model.ProjectTests.test_no_automatic_style_approval`

Both fail with `LOCK_MISMATCH: style/resource/toolchain/lock changed; explicit new revision required`. `adventure_maker/project_model.py:142-153` hashes all top-level `story/*.py` source bytes into the toolchain identity. The commissioned additive version dispatch necessarily changes those bytes. `projects/starter-sketch/style.lock` and its manifest still pin the baseline identity. `Project.verify_style` correctly refuses at lines 205-214.

The affected starter manifest/lock and project-model code are outside this lane's explicit write allowlist. This lane will not refresh them without the owner, monkeypatch away verification, skip the failing tests, forge the old source digest, weaken the retained lock gate, or claim a full regression pass. No user question is required: Main owns the follow-up integration decision.

Required owner action after composing the final source tree: explicitly issue a new **data-valid/runtime-pending** starter style lock and manifest hash using `make_style_lock(project.resolve_style())`; keep `approval: null` and `runtime_ready: false`; review the exact toolchain delta; rerun the unchanged tests and all retained gates. A proposed local handoff may be generated under `contracts/gameplay/integration/` for review, never automatically copied over the starter. Recompute after merge because source pins are exact bytes.

Raw failed evidence: `contracts/gameplay/evidence/regression-01/{summary.json,plugin-fast.stderr.txt,legacy-comparison.json}`. Earlier RED attempts remain as well. This is a genuine out-of-scope acceptance blocker, not permission to waive a style/runtime gate. All unimplemented Godot/physical/human/installed-loader dimensions remain not run.

Final rerun: `regression-03` executes 136 passing story tests and 177 plugin-fast
tests with exactly the same two errors. All 54 new module tests pass. The exact
aggregate is `contracts/gameplay/evidence/regression-03/acceptance.json`, with
status `blocked_style_lock` and nonzero exit. The disposable-copy lock-revision
control passes without modifying the retained starter or its approval state.
