# FEEL2 mouse / keyboard orbit

Root cause: `Actions` bound J/K/L/right-stick camera input but the fixed-camera
reducer suppressed it and the follow presenter never consumed it. No mouse
orbit consumer existed. The follow camera now consumes recorded raw camera
keys/axes separately from the simulation reducer, plus live mouse deltas.

Left-button drag changes yaw/pitch, wheel clamps distance to 2–6 m, J/L yaw and
U/K pitch, V recenters. The 1.5-second idle return eases behind player facing.
Pitch is limited to 0.15–1.05 radians; indoor ceiling and static pull-in remain.
Reduced motion removes lag and animated recenter; no pointer lock or keyboard
capture is introduced. Canvas element pointer capture releases on up/cancel.

The authored movement basis and all movie/save hashes exclude orbit transforms.
Strict playback ignores physical mouse input; recorded camera key/pad frames
can still be shown without steering movement. Legacy full profiles retain old
snapshot shape and IDs; `camera_recenter` is appended, as was `run`. Modern
camera-up moves off inventory's I onto U.

The initial real Chrome drag screenshot exposed a 0.24 m obstacle pull-in that
put the camera inside a torso. A retained near-obstacle RED then passed after
the camera searches nearby swept shoulder angles before accepting that close-up.
Corrected Chrome orbit frames show complete player silhouettes; foreground poles
and legacy room-prose panels remain disclosed weak views, not new feature tips.

TDD: `evidence/feel2/solids/orbit-attempt-01` has six behavioral failures on the
old camera, including live mouse drag, J, K, V and idle return. `-02` has all
13 checks passing but the generic runner rejected the unregistered receipt
prefix; `-03` fixes only that harness registry and passes orbit (13 checks),
legacy input snapshots and input checks with empty stderr. Browser/native
rendered acceptance and full merged suites remain parent gates at this commit.
