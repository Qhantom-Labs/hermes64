# LIVEFIX screenshot review

Assistant visual review, not human art approval. All retained task captures were opened through the image tool, using labelled contact sheets; selected final and defect images were also opened individually.

## Coverage

- Set A: `evidence/livefix/review-sheets/index.json`, sheets `review-01.png` through `review-38.png`: 238 raw PNG paths / 228 unique SHA-256s.
- Set B: `evidence/livefix/review-delta/index.json`, sheets `review-01.png` through `review-15.png`: the 90 additional unique images after final HUD/export verification.
- Combined: 364 captured PNG files / 318 unique hashes. Identical-byte duplicates are associated with their inspected image in the indexes. Original user reference image was inspected during diagnosis; it is not copied into this gallery.
- Scope is captured case screenshots, low-resolution world counterparts, retained audit-diagnostic views and rendered replay views, not source asset textures or copied app icons. No new screenshot jobs ran after the delta index was collected.

## Final exemplars

| Purpose | Raw capture(s), relative to `evidence/livefix/` | Review |
|---|---|---|
| Default follow / empty-panel contrast | `baseline-chrome/01-E.png` versus `web-combat-final-03/boot.png` | Old titled blank panel and poor player visibility; fixed view shows player, nonempty prose and prompt. |
| Actual active combat | `web-combat-final-03/combat-swing.png`, `combat-close.png` | Feet/head and opponent visible; short-range attack/telegraph views are more useful than distant opening engagement. |
| Combat HUD at all ratios | `web-combat-final-03/combat-1280x720-menu.png`, `combat-1280x800-menu.png`, `combat-960x720-menu.png` | Health pips are below, not painted over, the location header. Panel remains inside edges. Lower scene occlusion by an open modal is intentional. |
| NPC repeat / close | `web-thaw-final-03/talk-0-last-page.png`, `talk-0-closed.png`, `talk-1-last-page.png`, `talk-1-closed.png`; corresponding Relay files in `web-relay-final-03/` | Actual choice pages, closed box, second interaction. Text/choice panel fits; see silhouette overlap limitation below. |
| Thaw dialogue matrix | `web-thaw-final-03/talk-1280x720*.png`, `talk-1280x800*.png`, `talk-960x720*.png` | Counter/header and wrapped choices fit; no horizontal stretching or clipped choice text seen. |
| Puzzle movement | `web-puzzle-final-04/00-before.png`, `01-after-W.png` | Player emerges from the near wall into the board. This is stronger movement evidence than boot alone. |
| Puzzle matrix | `web-puzzle-final-05/aspect-*.png` | Board and menus fit each ratio. Brown clear colour around the board is scene background, not a retained 4:3 black-bar canvas. |
| Relay matrix | `web-relay-final-04/aspect-*.png` | Window-filling world; edge-anchored text and action panel fit. |
| Exact native exports | `native-combat-v3/`, `native-relay-v3/`, `native-thaw-v3/`, `native-puzzle-v3-02/`: `native-1280x720.png`, `native-1280x800.png`, `native-960x720.png` and world counterparts | Rendered app frames, correct dimensions/low-res ratios; not proof of native OS-key handling. |
| All puzzle rooms/course | `rendered-final/puzzle_hall/puzzle_*`, `rendered-final/reedland_relay/course.png` | Puzzle-owned framing retained across rooms. Course view has a significant low-occluder weakness below. |

## Weak / superseded / limited images

1. **Baseline failures are negative controls, not delivery screenshots.** `baseline-chrome/*`, `original-smoke/first_interaction.png`, `city-original-chrome/*`, successful old talk-loop reproductions `browser-thaw-baseline-06/*` and `browser-relay-baseline-07/*` deliberately show empty panels, off-frame/cropped players or cancelled/repeated talks.
2. **Failed instrumentation exports are unusable playability evidence.** `browser-relay-baseline-01` through `-06`, `browser-thaw-baseline-01` and early `baseline-web-*` attempts include unavailable diagnostics or missing/incorrectly imported media. Some images show blank/flat/incorrect actors. They are retained to explain the debugging path, excluded from final pass claims. The successful original-code reproductions are the specifically named later folders.
3. **Cropped pre-correction combat:** `web-combat-final-01/combat-swing.png`, `web-relay-final-01/combat-swing.png` and early source aspect/combat attempts lose feet/lower body. These prompted the full-body camera regression and are superseded by final-03 web and `combat-hud-attempt-03` source captures.
4. **HUD overlap before final correction:** `combat-hud-attempt-01/*-menu*.png` and `combat-hud-attempt-02/*-menu*.png` (and earlier menu matrices) superimpose health pips and room text. Failed pixel assertions are retained. Only `-03` and final export-03 prove the correction.
5. **Partially typed frames are weak text evidence.** `boot.png`, `npc-approach.png`, `talk-*-open.png` and quick `aspect-*.png` captures sometimes stop mid-typewriter line. They establish layout/transition, not a complete readable transcript. Native `native-*` layout frames wait for typing; `talk-*-last-page` and choice/menu captures are better text/closure evidence. A page ending mid-sentence with `1/2` is a page boundary, not necessarily a failed typewriter.
6. **Puzzle spawn occlusion remains:** most Puzzle Hall boot and entry captures show only the player's head above the near wall. Later W/solved views show movement/body. Grid framing is readable, but the boot image is weak player-visibility evidence; no claim of universal mesh-occlusion elimination.
7. **Close NPC silhouettes overlap:** Relay's Iri approach under the tree and Thaw's desk/Neri approach can overlap the player with an NPC, prop or trunk. The data/positions are unchanged. These are valid receiving-state/input tests but weak character-separation shots.
8. **Low boulder occlusion remains:** `rendered-final/reedland_relay/course.png` hides much of the player behind a boulder. Static camera collision pull-in is not a transparency/fade system or exhaustive body-visibility guarantee. Course timer/progress remains readable.
9. **Frame-exact scripted region captures can be visually empty:** `rendered-final/reedland_relay/region_arena.png` and `region_field.png` show blank-looking narration during their capture timing. They are not used to certify complete narration readthrough or to replace final real-key tests. No blanket claim that every prose/capture sequence is fixed.
10. **Audit masks are diagnostics, not beauty shots:** `audit-diagnose/**/screens/*-key.png`, `*-mask.png`, `*-depth.png`, extreme `*-closeup.png` and sparse keeper-room renders are for measured art diagnostics. Magenta key regions/black masks are deliberate; sparse geometry or poor authored framing is not approved by this lane. FAIL/manual guidance is retained.
11. **Native failed attempt:** `native-puzzle-v3/` stopped at an incomplete request-JSON read; its boot frame is not a completed aspect matrix. Atomic runner requests and successful `native-puzzle-v3-02/` supersede that test attempt, not the app binary.

No screenshots alone prove focus/input delivery, frame rate, replay state equality, saves, completion of a whole game or human quality approval. Those claims require the separate receiving-game, hash and process receipts described in `LIVEFIX-RESULT.md`.
