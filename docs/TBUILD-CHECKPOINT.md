# L4 checkpoint

## P1

- P0 `template-lane` 79f8fb14 merged first; base remains `rc3-base-1`.
- Registry and arena generate five kit-dressed castle rooms, three arena challenges and one boss challenge on gameplay 1.1.0. Authored door positions retained; targets form a reversible chain; next door waits for challenge completion. >3 spawns split into groups; >8 groups/24 spawns refused.
- Pack runtime consumes precompiled `hermes64-pack-rooms/1` JSON. `tools.pack_rooms` is developer-only and checks regeneration against data plans. No shipped dependency on kit compilers.
- Conditional badge requires complete proof, matching game hashes, complete physical module bot, nonempty successful paths, all required modules and receipt. It says conditional, never proved. Audit and asset failures still prevent readiness.
- 20 focused tests passed (`p1-04-tests.log`). Real five-room create: compiled, conditional proof with zero softlocks, assets built, physical bot PLAYABLE and complete. Returned `new_game_needs_work`, not green: audit FAIL 9/100 in 37.388 seconds (`p1-keep-result.json`).
- Blocking audit findings include runtime flat-colour `gate` / `boss_gate` markers (unowned runtime code), plus courtyard landmark/depth/horizon composition. No gates weakened. Room art needs another pass before green acceptance.
- Windows preflight and command-line hunks are not on rc3-base-1; L4 leaves preflight and command construction untouched, and adopts its exact UTF-8 starter read. Integrator must union the remaining original Windows hunks at M9; do not take Windows' historical deletion of MOVE's audit next step.

## P2

- Closed premise 1.0.0 schema/validator and bounded loader; external games-folder lookup, exact title matching, explicit --story, ids/path/symlink/duplicate checks and SHA-256 provenance. Legacy parser callers retain three-tuples; the slash command uses the story-aware path. No tool-schema change.
- Neutral keep-under-siege story ships; showcase folder is explicitly excluded. Package docs updated. Package suite materialized and checked a real installed tree, including failure controls.
- 32 tests passed (`p2-03-tests.log`); schema regeneration checked. Real title-matched create completed physical combat with zero softlocks in 27.434 s; Story line and pending fields recorded. Audit remains FAIL 9/100, not green (`p2-siege-result.json`).
- Requested runtime-owned fields are reported as not applied, not silently ignored or claimed implemented.

## P3 — implemented portions; integration remains pending

- Adopted completed A1 brief branch and its create/card hook. Wizard-purple prompt routes via the brief fallback to castle_keep and says the requested purple assets/palette were not generated. Brief is saved as fallback intent, not custom-art proof.
- R10 display names landed. Tagged fox comparison shows exactly nine display-text changes, zero structural/progression changes; the old premise_spec function and preflight are unchanged.
- Actual COMBAT2 fields adopted behind the installed contract/runtime capability. Isolated committed L1 snapshot 780acce6: four completed challenges, three simultaneous bosses, conditional proof, zero softlocks, assets built, PLAYABLE. Full M1-M5 composition is not done.
- Neutral castle dressing improved without altering gates. Final native room geometry: 3,474–5,856 triangles. Real bot completes; audit stays FAIL 74/100 due four rooms' runtime gate placeholders, with fog warnings. New game honestly stays needs_work.
- Driver ran actual qualified local web exports. Two repeated builds: unchanged toolkit, equal game hashes, but four exported paths differ (PCK plus derived manifests/archive). A2 failed; no determinism claim.
- 84 focused tests passed. Story stage: 160 passed. Runtime stage: all five standard groups passed. Full plugin suite completed: 770 tests, 1 failure, 3 errors, 2 skipped. Failure attribution to the tagged baseline has not been independently re-run in another worktree. The earlier foreground full-suite attempt timed out; the completed rerun is retained separately.
- Excluded showcase data validates: 199-character prompt, 23 robots, three bosses, 11 cards. It is not a built showcase. Audio ids/media/overlay remain owner integration; no audio/image source was read.
- Remaining P3: cyber room bake/anchors, scene/results/slot/weather consumers, overlay/site-pack integration, explicit hero_start runtime consumer, green badges, and export determinism. See docs/TBUILD-INTEGRATION.md; the room-entry request is a source-only patch, not an unauthorized runtime edit.

Main must integrate the remaining owner inputs; this lane does not certify M7, M10 or the product definition of done. No push/network/install/reset/stash or other-worktree write was performed.
