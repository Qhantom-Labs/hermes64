# CAM final screenshot review

**Actually viewed with the image tool:** all four `evidence/cam/review-final/` strips below, containing **20 selected source PNGs** from the exact `export-05` / `d0d8e1a` web PCKs. Two of those same final source images were also viewed individually at full size; they are not additional unique images. **68 final-case PNGs** are retained as inventory, not 68 reviewed images.

`review-final/index.json` pins every source and strip SHA-256 plus receiving-state observations. Screenshot calls advance wall time. Receiving ticks are sampled after capture, stream phase labels are observations, and the selected images are not uniformly spaced. Continuous smoothness is established by the separate per-render traces, not inferred from these stills. This is assistant review, not the owner's art/play-feel approval.

## Final strips / weak frames

- **`reversal.png` — five frames.** Player remains inside the selected frames; the former right-edge clipping is gone. `reversal-02`, `-03` and `-04` remain weak silhouettes because fence rails overlap the legs/torso. Canopy posts and the roof edge remain foreground clutter. No character/rig/animation changes were made to hide that.
- **`circle.png` — five frames.** Player is visible in every selected frame, including `circle-06` (the corresponding intermediate view had lost the player entirely). `circle-00`/`-02` have nearby canopy-post interference; `circle-04` has fence overlap. `circle-06`/`-08` are closer boundary-side compositions, not a new first-person mode. E prompts can sit near the silhouette. These are retained weaknesses, not exhaustive occlusion approval.
- **`doorway.png` — seven frames.** Pod Bay source now shows the player and hatch rather than a blue-wall-only view. The selected dark destination frame already frames the player; arrival and settled views keep that composition. Workstation remains crowded with an NPC, desks and foreground plinths, and the ghost step is subtle. Sparse phase samples do not constitute a frame-complete visual inspection of the fade; the actual renderer log and input-release assertions cover its timing separately.
- **`modules.png` — three frames.** Combat keeps the tested player body in frame; the small opponent still has weak brown/ground contrast. Puzzle Hall's existing near wall hides most of the player at spawn (`00-before`); W movement reveals the player farther into the room (`01-after-W`). That authored puzzle-geometry occlusion was not fixed or relabelled a visibility success merely because a frustum check passes.

## Rejected intermediate views, preserved

`review-probe/` has two actually viewed strips (10 images) from the first browser attempt. `review-04-intermediate/` has four actually viewed strips (20 images) from `export-04`. The latter exposed a substantive failure despite green smoothness metrics: edge-clipped reversal, empty circle view and blue-wall source-door framing. That export was rejected and retained, not overlaid into the final delivery. A failing loaded-render visibility test preceded the corrected actual-eye/stabilized-point aim. The final strips above were newly captured and viewed after that correction.

## Not established by these images

No human playthrough/feel/art approval; no exhaustive prop, wall, weapon or NPC occlusion coverage; no native OS-input check; no claim of achieved 30/60/144 hardware FPS; no review of every retained image. Full motion metrics, requested caps, observed engine-delta rates, PCK identities and unchanged replay checkpoints are recorded separately in `CAM-RESULT.md` and `CAM-VERIFICATION.json`.
