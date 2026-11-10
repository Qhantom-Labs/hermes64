# Module proofs and evidence (STORY 1.2.0)

## Honest public wording

> Hermes64 includes a data-only prototype for bounded arena-combat contracts, finite ability/key gates, connected outdoor-region graphs and timed on-foot courses. The checker explores finite progression and recovery states. Combat/course success remains conditional on named assumptions. Godot execution, combat feel and human playability are not verified by this phase.

Do not replace this with “combat is proved winnable”, “open-world runtime”, “verified racing”, “physically tested” or “ready to ship”. This lane does not change the existing README or silently widen release claims.

## What the checker establishes

The normal compiler performs closed structural admission, module/version/dependency checks, uniqueness, exact cross-references, exclusive challenge/region ownership, spatial data bounds, ability prerequisite acyclicity, fixed resource policy, finite state bounds and exact compiled metadata validation. Those checks do not simulate gameplay.

For a valid 1.2 game, `story.modules.analysis.check` explores the complete reachable **abstract** graph, including both success and failure branches for every reachable challenge. Ordinary legacy transitions retain their existing semantics. It checks:

- Every declared ending is reachable, terminal results are unambiguous, and every reachable nonterminal state has an ending route under the model's assumptions.
- Challenge entry and guaranteed one-shot rewards are reachable, including gate prerequisites; no reward may be required to enter its own otherwise inaccessible challenge.
- Every reachable failed attempt has a route back to that challenge's entry, not merely some ending. Abort uses the same recovery branch. Ending detection is disabled for active/failed attempts so a terminal flag cannot hide a failed retry.
- Every ability has a reachable producer, every region is reachable, every declared door gate is usable, and inherited 1.1 collectible/threshold/non-missability obligations still hold.
- Required resource policy is bounded: free entry/retry, replenished transient health, no scarce ammunition, unique permanent reward items, deterministic grants, no required random drops or repeat farming.
- Course time limits meet a **necessary lower bound**: sum the nonnegative distance between successive checkpoint spheres (start radius zero), divide by the admitted maximum speed, multiply by 60, and ceil with a tiny numerical tolerance. Failure means physically impossible even with ideal movement; passing is **not** a steering, collision, jump, acceleration or human feasibility proof.

The engine/analysis code uses finite IDs and monotonic sets, not a collision solver or damage simulation. Returning a witness that contains `assume:complete:*` is not a gameplay recording. `AnalysisEngine` can replay those witnesses to reproduce the abstract final state; ordinary `Engine` rejects them.

## Named assumptions and separate dimensions

Every report lists `spatial_access`: logically available room doors, interactions, checkpoint anchors and challenge entry anchors can actually be reached in physical space. Each challenge also declares `<kind>_<challenge_id>_completable`, such as `combat_gate_trial_completable` and `course_relay_trial_completable`.

`evidence` has separate fields:

| Dimension | Meaning in this phase |
|---|---|
| `logical_proof` | `proved` only for the finite macro graph and admitted resource/ownership rules, or rejected/invalid/inconclusive. It is not a physical result. |
| `conditional_on_assumptions` | `conditional` for a passing challenge game, listing named assumptions. `logical_only` policy refuses required challenge assumptions. Region/ability-only graphs can be logically `proved`; spatial geometry is still outside the claim. |
| `physically_tested_by_bot` | Always `not_run`; receipt null. A later real production-input run must bind exact build, runtime and resource hashes. |
| `human_tested` | Always `not_run`; receipt null. An author/model cannot manufacture Dylan's playability/feel approval. |

Overall successful challenge reports are `conditional`, not `proved`. The facade accepts them only if the source explicitly declares `verification_policy: conditional`. `rejected` means an actual failed obligation, `invalid` means unsupported/malformed input, and `inconclusive` means bounded exploration stopped. CLI `story check` returns 0 for logical proved, **4 for conditional**, 3 for inconclusive, 2 for rejected/invalid. These are not interchangeable success codes for runtime verification.

## Work limits and explanations

State cap is at most 100000 and transition cap at most 1000000; both fail closed. An incomplete graph has no softlock count/completeness assertion. No collectible symbolic BDD solver is used for 1.2; explicitly requesting it rejects. The direct exhaustive API also dispatches to module analysis so it cannot falsely reuse the old unconditional label.

Reports contain per-obligation plain-English explanations, missing prerequisite diagnostics, and concrete counterexample states plus shortest discovered entry traces for failed obligations. Unsatisfiable existential targets do not have a success witness; their diagnostic starts from an actual reachable state and names the unmet gate/reward/region. Counts describe the full graph; displayed softlock/dead-end/ambiguity samples are bounded to ten, with total counts separate. A counterexample is a logical diagnostic, never a synthetic physical trace.

`story.modules.reference.check_reference` is a slow concrete oracle. It independently reduces module transitions and independently performs graph reachability (per-source forward searches rather than the optimized reverse pass). It shares admission, legacy transition templates and obligation definitions; **it is not an independent proof of the schema or every obligation predicate**. The seeded differential test compares status, state count, softlocks, ambiguity, ending reachability and obligation statuses on 256 varied games. Adversarial controls independently cover missing producers/keys, a self-reward gate, an unreachable region, impossible course timing, retry dead ends, malformed schemas/state, invalid saves and stale transactions.

## Reproducible evidence

From the repository root, Python 3.9 stdlib only:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m adventure_modules.export_contracts
PYTHONDONTWRITEBYTECODE=1 python3 -B -m adventure_modules.examples examples-authoring-NEW
PYTHONDONTWRITEBYTECODE=1 python3 -B -m adventure_modules.verify regression-NEW
```

Use a new evidence directory per run; failed receipts remain. The fixture exporter goes through `ModuleService.handle`, captures actual compiler/checker results and measures three sequential typed edits (enemy recovery, course checkpoint placement, region gate). It writes four standalone `examples/gameplay-*/{spec,game,proof,save}.json` sets and `contracts/gameplay/evidence/{examples,module-benchmark,module-benchmark-operations}.json`. It checks toolkit source stayed unchanged across fixture creation; the examples contain only JSON. Managed temporary authoring projects retain immutable candidate payloads for receipt inspection. The fixture factory itself is shared test infrastructure, not an authored per-game script.

The benchmark reports the actual denominator and `data_verified_passed`; `fully_verified_passed` remains zero. Each measured row includes explicit expected locality, compiler/game hashes, source/build revision paths, save migration and separate unrun runtime/bot/human dimensions. It never adopts a live or data pointer. A missing save or locality expectation cannot count as a complete data benchmark pass.

The scoped verifier runs **all story tests** and **all plugin fast test modules**, retaining argv, stderr/stdout, counts and exit codes. Native suites (`test_real_build`, `test_characters_runtime`, `test_characters_default`, `test_roomlook_kits`) remain explicitly excluded here; no full `verify_all` or native acceptance claim is made. Baseline receipts capture canonical game/proof/save and room hashes for both example and published Last Light/Thaw sources; post-change receipts compare exact bytes/digests. The original 256-game legacy differential test remains in the story suite as well.

## Explicitly NOT verified

Godot reducers or execution; physical combat win/loss; attack windows/LOS/hitboxes/iframes; real controller portal/collision traversal; real timed checkpoint crossings; cadence independence; animation/audio/style or visual approval; performance; human balance/accessibility/feel; installed Hermes tool loading; full native release/package gate; independent reviewer acceptance. Native input traces, screenshots and successful playtests have **not** been fabricated as substitutes. No remote operation, install or publication belongs to this phase.
