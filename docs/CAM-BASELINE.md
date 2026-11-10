# CAM baseline diagnosis / RED

Runtime baseline `f0d69244`, old camera preserved verbatim as `runtime/godot/tests/cam_old.gd` (test-only negative control).

The production script was exercised with a synthetic exact 60 Hz physics / 30, 60, 144 Hz render scheduler. This is a reproducible presentation metric, NOT achieved hardware FPS. `tools/cam_metrics.py` was fixed before implementation: ≤0.32 m/frame, ≤100°/s combined yaw/pitch, ≤1800 m/s³ finite-difference position jerk, ≤90°/s FOV. Only fully masked doorway frames and adjacent derivative history are excluded.

Observed RED: 10/21 cases fail. Straight at 144: 0.033334 m jumps alternating with unchanged poses; peak jerk 199068 m/s³. Hard reversal at 60: 2.243610 m/frame, 1728°/s, 629169 m/s³; at 144: 4147°/s. Orbit/recenter at 60: 1.564349 m/frame, 1201°/s. Raw traces/process logs: `evidence/cam/baseline/`.

Source confirms no render interpolation; a 0.8 m hard lag clamp; fixed-tick angular lerp plus idle return directly to player facing; immediate reduced-motion assignment; physics-only collision shoulder selection; authored entry reset. These are mechanisms, not all independently isolated causes. Look-at already reads root +0.8 m, NOT the animated head: bob hypothesis is not supported. Combat already smoothsteps its blend weight but target eye/FOV can change per tick; puzzle uses authored framing. The initial framing/reduced stationary fixtures are controls, not behavioral RED.

Existing historical full-goal movie bytes were not present in this new worktree. Before any camera change, the existing production goal runners and exact stored 1120-frame floor input fixture were executed to retain baseline movies/checkpoints under `evidence/cam/baseline-replays/`. No historical receipt is relabelled as a newly replayed movie.
