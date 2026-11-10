# COMBAT2 screen review

Reviewed with the image tool: both 12-frame contact sheets, `evidence/combat2/chrome01/contact-sheet.png` and `evidence/combat2/chrome-final/contact-sheet.png`. Final captures come from the frozen-source local web export at b1762a92. Originals are 1280x720; the sheet is a downscaled index, not a replacement for originals. Each original's actual receiving tick is in `states.json`; capture calls advance time, so labels are requested inputs, NOT uniformly spaced keyframes or proof that a named hit landed.

## Observed

- The three outlined health blocks are plainly visible top left. Run digits are readable top right; a checkpoint diamond is visible in the final sheet's checkpoint frame.
- The playable guardian and stock creature art render without missing-media errors. Real keyboard movement, punching, hold/release and run+primary were captured. The measured receiving velocity before run+primary exceeds the 2 m/s threshold; native movie evidence, not these pictures, proves the five distinct damage transitions.
- No Chrome console errors in either run. These are SwiftShader/software-rendered Chrome captures, not hardware FPS measurements.

## Visible gaps / NOT accepted

- The example is mechanically a different theme, but its sparse brown grove floor is not a polished forest scene. There is no visual/style approval implied by the example.
- Several first-strip frames crop the player's left edge or make the actor small; some final-strip frames clip feet near the bottom. The movement/follow-camera sources remain byte-unchanged. This is a framing limitation observed in the larger arena, not a claimed camera fix or human acceptance. Do not silently retune MOVE's camera to hide it.
- Jab/cross/finisher/charge/running use optional-clip fallback on this cast. The pictures do not establish bespoke, visually distinct fist animations; CHARS3 owns those assets.
- The notices link remains bottom right, and the normal opening room text panel remains on boot. The link move is an owner handoff, not implemented here.
- This strip does not show the three-boss finale, penalty animation or rescue/results scenes. Boss budget and run arithmetic are native-tested; rendered finale/results acceptance remains open.
- No human controller feel, timing fairness, Windows or hardware performance acceptance.

See `docs/COMBAT2-RESULT.md` and the exact evidence receipts for passing and failing gates. A successful browser boot is not the definition of done for the whole product.
