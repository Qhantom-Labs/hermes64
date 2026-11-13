---
name: hermes64-playtest-and-ship
description: "Use when testing or shipping Hermes64. Keep proof gates."
version: 0.1.0
author: Qhantom Labs, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [Hermes64, Playtest, Export]
    related_skills: []
---

# Hermes64 physical playtest and local shipping

## When to use

Use for proof-backed physical testing, local export acceptance or a reproducible demo in the assembled Hermes64 repository. Do not use to grant human artistic approval, change story/visuals or publish. This skill's native developer commands are macOS-specific (Seatbelt, Godot.app and codesign). Common web/Windows exports also use the configured Windows/Linux runner; those platforms remain Not verified. Read `docs/PLATFORM-EVIDENCE.md` rather than inferring acceptance from a built artifact.

## Prerequisites and boundaries

Use this with the assembled Hermes64 repository and its existing owner-chosen projects root. Read `docs/PLAYTEST.md`, `docs/EXPORT.md`, `docs/DISCLOSURE-SHIP.md` and the exact result receipts. Main applies `docs/SHIP-INTEGRATION.md` before the three tools become available; a source file or successful recording-context test is not live plugin activation.

Never install/enable a profile, download templates, change visuals/cast/story semantics, use private/cameo assets, upload, sign with an identity, notarize or publish without separate authority. Do not treat an internal source reference as public merely because a scanner can remove it. Exports remain local.

## Workflow

1. Establish an existing project root and a fresh project ID. For a complete bundled example use `hermes64_demo` with `project`, optional `example` (`last_light`, `thaw`, `starter`) and `seed`. CLI via `terminal(command="python3 -m adventure_maker.demo --projects-root /absolute/existing/root --project demo", timeout=600)`. Bare CLI deliberately uses cwd as root. Do not reset an existing edited/unowned demo to make idempotency succeed.
2. For existing authored games, compile/check and build assets with the existing tools first. `hermes64_playtest` accepts `mode=both`, `seconds=30`, `seed=7`, `drought_seconds=20`, `render=false`. Retain reports and process exit diagnostics. Repeat the same host/version/seed/mode when checking deterministic hashes.
3. Read **all** reasons, not just the rating. The proof badge from `/hermes64 new` (also in that game's `project.json`) is a summary of these reports: quote it verbatim; it copies the tier, prints failed gates in capitals and says "not run" for anything missing (`docs/PROOF-BADGE.md`). Logical proof rejection, timeouts, crashes and script errors are BROKEN even if a witness completes. Physical failures are separate from logical softlocks. Location-scoped interactions without anchors remain explicit; never modify production story behavior to make a bot's assumptions true.
4. Use `render=true` for actual screenshots/draw/engine timing. Headless heatmaps are maps, not rendered screenshots; dummy render throughput is not display FPS. Check PNG contact sheets alongside measured room budgets. Reports cannot judge fun or grant artistic approval. `hermes64_check(action="audit")` scores rendered rooms against the style lock (docs/STYLE-AUDIT.md). A failed playtest or audit returns `next`: run those exact calls in order and re-read the new result (docs/AUTOREPAIR.md); `manual` items need a decision.
5. Run `hermes64_export` with selected `targets`. Verify current proof, character admission (frozen public hash or evidenced project-local generation/owner rights, never merely a rig waiver), media hashes, portable resource bindings, privacy scans, license inclusion, sorted file inventories and actual target results. Missing/mismatched templates/assets fail closed. Do not add a downloader or lower a gate.
6. Run the explicit developer smoke via `terminal(command="python3 -m tools.ship_web_smoke /absolute/share/web evidence/ship/new-smoke-label", timeout=180)`. Inspect its **receiving game event**, page console receipt and real first-interaction screenshot with `read_file` and `vision_analyze`. Build success does not imply browser success. macOS headless boot is required by the exporter; Windows stays UNVERIFIED until a real recipient test.
7. Deliver paths, timings, SHA256 inventory, real test outputs and limits. Never imply that local artifacts were uploaded. Run owned tests and `terminal(command="sh tools/verify_all.sh", timeout=600)` on the exact merged source before a release claim. A timed-out original verifier stays failed; a separately disclosed `tools.ship_verify` extended-suite result cannot rewrite it.

## Proven pitfalls

- Preserve the complete installed Godot.app for self-contained export staging; a copied Mach-O alone fails macOS signature enforcement. `_sc_` and selected template cache stay inside the project, preserving the existing write sandbox.
- Keep template changes narrowly scoped and hash-pinned. Official Emscripten virtual HOME and Rust panic source-root strings are not user secrets; known same-length relocations and explicit modification notices avoid absolute-home strings without masking actual source leaks. Ad-hoc re-sign modified macOS output; do not claim Developer ID/Gatekeeper acceptance.
- Distinguish OpenXR `/input/home/click` from a `/home/` filesystem root. Test both the harmless component and actual home references; never exempt an entire executable from scanning.
- Use a fresh **explicit Hermes scratch** profile for Chrome, with `MAC_CHROMIUM_TMPDIR` and `CFFIXED_USER_HOME`; inherited TMPDIR can resolve to a system temporary directory. Keep the outer loopback/write sandbox when disabling Chrome's unsupported nested Seatbelt setup. Stop the browser before cleaning its profile. Never reuse the user's browser.
- Preserve page console errors; fix missing export resources rather than suppressing them. A favicon 404 can fail an otherwise rendered browser smoke.
- Keep wall/allocator/render samples outside deterministic trace hashing; deep-copy before dropping nondeterministic fields so report metrics are not accidentally deleted.
- Sample geometry at room entry, after actions and periodically, rather than calling `Mesh.get_faces()` on every rendered frame. GPU readback can dominate the harness and cause artificial timeouts. Keep engine monitor percentiles labeled as sampled values, not device-certified frame distributions.
- Preserve partial negative evidence on timeout. A rendered probe can hit the bounded wall cap even when the headless physical witness succeeds. Do not raise permissions or call the bounded failure a pass.
- Keep audio test evidence under `audio/evidence/` to satisfy the existing lane path guard. If frozen-audio SHA256 values match but checkout mtimes differ from the preservation baseline, retain both identities and report the gate as blocked; do not rewrite files, timestamps or baseline records to make it green.

## Verification

`terminal(command="python3 -B -m unittest tests.test_ship tests.test_ship_native -v", timeout=180)` exercises verdict/schema/report/privacy/ZIP behavior, recording-context additive registration, native repeated traces, unreachable-key/collision/script-error/softlock controls and rejection of bound internal-only data. Separate real export/browser receipts and full verifier output are required; unit fixtures are not recipient execution.
