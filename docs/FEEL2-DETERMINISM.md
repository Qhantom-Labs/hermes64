# FEEL2 render-rate regression and deliberate replay pins

## Observed failure, not an edited expected hash

Candidate `1fe68be` completed all five physical bots and six cold strict movies
twice at 60. Thaw also passed 30/144 and Relay passed 30. Relay at 144 failed its
unchanged checkpoint at 1080, reproducibly. Per-tick traces locate the first
physical difference at 1031: the prior canonical state and fixed delta were
identical, but native **flat-floor** capsule recovery produced different X/Z
velocity and a 0.1 mm Z step. It subsequently changed enemy aim, roll direction
and player motion. This was not a camera transform or a changed input frame.

Evidence: `evidence/feel2/replay-final-02/`, `trace2-60.jsonl`,
`trace2-144.jsonl`, `contact-probes.log`. Both deltas are exactly 1/60; the contact
lists identify the same flat floor with upward normals, not a decorative prop.
Forcing Node/PhysicsServer transform synchronization did not fix it. Removing
collision bodies from the presentation ghost also did not fix this rate failure;
that separately enforces a genuinely render-only exit copy.

## Physical fix

On exact flat support, use the existing `floor_snap_length` for adhesion rather
than sweeping `ground_pull_mps` diagonally down into the floor every move. Ground
pull remains on slopes, and airborne gravity is unchanged. Native horizontal
collision/sliding against props and the existing 0.1 mm authoritative position
quantum remain. No state-hash rounding, replay-loader waiver, collider exemption,
engine time-scale change or changed course/combat/puzzle rule was introduced.

A confined one-variable probe re-recorded the **same complete Relay input** once
with this physical change and then passed strict 30/60/144 playback. See
`flat-probe-01/` beneath the FEEL2 evidence folder. The durable regression is
`tests/fixtures/feel2_floor_rate_input.json`: an exact 1,120-frame prefix of the
previous completed bot, losslessly RLE encoded into 71 runs with source SHA and
initial state. `tools/feel2_replays.py` records those unchanged frames on current
source and requires identical strict results at 30, 60 and 144. Reverting the
flat-floor change re-exposes the retained divergence.

Source-focused post-fix gates: fourteen controls suites pass; native footprint,
edge, navigation, orbit and integrated suites pass; transition controller passes;
all five-game connectivity cases pass. Proper COMBAT fixtures pass 67 checks.
The first wider wrapper accidentally ran that COMBAT suite on Thaw fixtures and
correctly failed; its receipt is retained rather than counted as green.

## Pin policy

No stored historical M5/LIVEFIX movie files were supplied in this worktree. Do
not pretend unavailable bytes were compared. The final ledger separately lists:

- Six newly recorded full physical goal movies and their earlier FEEL2 receipts,
  including changed frames/checkpoint fields and exact hashes.
- The actual pre-FEEL2 `7edc26fd` controls movie retained by the run-input lane.
  Compare its old expected checkpoints unchanged first; deliberately re-record
  the same physical frames and strictly verify the new pin. Preserve old bytes.
- The fixed-input flat-floor witness above, not a claimed winning path itself.

Collision, safe reciprocal entries, deterministic transition input-latch resets,
modern orbit-input exclusion and flat-floor adhesion are intentional simulation
or input-snapshot changes. The final `FEEL2-REPLAYS.json` names every adopted pin
and why. Production movies still require their exact game/build header; only
explicit cross-build **test helpers** rebind a build header in memory.
