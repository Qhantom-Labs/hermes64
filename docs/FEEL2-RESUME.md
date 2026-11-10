# FEEL2 resumed acceptance stages

## 1. Live Neri regression

Resumed from `0d386fa4`; runtime feature commits are retained unchanged. All three dirty tools were reviewed and kept. `feel2_review.py`'s SHA-based delta catalogue is useful and retained for the visual-review stage. `feel2_verify.py` was pointing at known failed `chrome-talk-v2-02`, not the later passing attempt; its final talk receipt now points at this session's real run.

Observed RED: `evidence/feel2/chrome-talk-resume-01/result.json` reached and closed the first conversation, then stalled by the quilt chair on the second approach. The planner re-ranked an NPC **moving nearest-edge target** against moving pickup edges. This is a harness route defect, not a missing dialogue implementation; no gameplay source was changed.

Fix: plan from Neri's immutable native footprint, require the exact `interact:talk_neri` candidate, retain the successful capsule-clear **grid cell** for the return, and capture both approaches. Do not target a point inside the desk or reuse an arbitrary sub-cell location beside curved collision. Inputs remain actual Chrome CDP keyboard events; no teleport, action-frame or story injection.

GREEN: `chrome-talk-resume-02/result.json`: two real E-open conversations, each closed in two page/choice advances, physical walk-away distances 1.556908m and 1.595394m; no console errors. Other existing feature receipts include actual Chrome mouse drag and simultaneous keyboard movement. Failed attempts remain intact. Final exact-delivery verification and visual inspection are separate stages below.

## 2. Existing physical bots and strict replay suite

One fresh run: `replay-resume-01`, exit 0. Five physical bots, six movies, 12 cold strict playbacks, 12 additional cap runs, three unchanged-input floor-regression runs and two legacy strict runs pass. All six full-goal movie bytes match pre-resume `replay-final-03` exactly. `FEEL2-REPLAY-NOTES.md` separates new collision-aware routes, integrated input/entry pins, proven old blocked-route regression and unproved collision attributions. No monolithic verify_all/full Python rerun was used.

## 3. Every-room connectivity

Fresh `solids/connectivity-resume-01`, exit 0: all five games (Thaw, Reedland Relay, Reedland Combat, Puzzle Hall, City Arena), 16 rooms / 32 resident-and-collected states, 154 required-target checks, 14 detected bad controls, 302 puzzle cells and 464 adjacent grid segments pass; zero failures. The four native solids/geometry/edge/navigation suites pass too, including the old crossed-prop route assertion. Full per-room JSON and exact runtime source SHA-256 inputs are retained in that folder.

## 4. Exact delivery rebuilt and exercised (RESUME2)

`final-export-resume2-01`, exit 0: the entire stale `play-fix2` was replaced first, then all four games were exported for web and macOS from `8e03543d451d0a9456b73620726211aa9bcd30e6`. Eight ZIPs plus expanded folders, `FIX2.md`, `SHA256SUMS`, `MANIFEST.json`. Exact readback checks ZIP/folder bytes, all four signatures, universal slices, unchanged shipped game/media data and all 18 original `play` / `play-fix` archives.

Fresh Chrome `*-resume2-03`: six passing cases cover all four exact web PCKs (hash-bound receipts), actual mouse drag plus simultaneous WASD, run/precision speeds, collision pressure, settings, both transition modes, combat and puzzle input. `native-*-resume2-01`: four exact executable/PCK pairs booted normally with an onscreen OS window and captured all three aspect sizes; native OS input remains unverified. No runtime change, replay rerun or full-suite rerun was needed.

Retained browser failures `chrome-relay-resume2-01/-02` exposed a harness-only contact assumption: a glancing column contact allows sliding, and an earlier incidental rock probe is not the currently pressured column. The corrected harness continually re-aims at the selected prop and requires its native contact/probe plus the original <0.35m pressure-displacement bound. Saved traces show the selected column stops motion. It does not disable collision, lower run speed, teleport, or accept a different obstacle as success.

The delivery-stage verifier passed and explicitly labelled visual review pending.

## 5. Feature strips actually viewed

Seven curated strips / 35 source PNGs were loaded with `vision_analyze`: orbit, actual Shift-held run, two prop pressure/release pairs, normal doorway, reduced-motion doorway, four native scenes and module support. `FEEL2-SCREENREVIEW.md` records the specific weak frames. The 423 retained captures are inventory only, not a claim they were all viewed. The final readback hashes all seven strips and 35 sources, then records this narrower review scope. No runtime or asset change was introduced.

## 6. Final closeout

`FEEL2-RESULT.md` now records root causes, exact delivery/source identities, real fresh and retained results, every deliberate replay adoption, specific weak frames and NOT-verified limits. Read-only native permission preflight is still false; zero events posted and no prompt. Final `tools.feel2_verify` is the readback-only closeout gate (not a full-suite rerun); source remains `8e03543d`. The closeout commit is reported by Git after this document is committed. No next lane, push or publication is implied.
