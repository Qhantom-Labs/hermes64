# Builder API (hermes64 style engine)

You design; the plugin conforms (palette, triangle budget, texture energy, baked light) and gates. A builder script
is plain Python run once in a sandbox: no imports, files, attributes or dunder names; `math`, `pi`, `sin`, `cos`,
`tan`, `sqrt`, `atan2`, `radians`, `rand(i)` (deterministic) and safe builtins (`range`, `len`, `min`, `max`,
`abs`, `round`, `list`, `zip`, `enumerate`, ...). Loops, functions and list comprehensions work.

Units: metres. Axes: +Z up, the FRONT faces -Y, ground at z = 0. Roles are pack palette roles (the pack picks the
colour): `body body_alt trim frame wood bark stone wall wall_alt metal chrome glass light screen fabric rope foliage
cap flower fur hull hull_alt band leather paper cushion roof rock sand water ice`. `light` and `screen` glow: use
them small.

## Parts (each returns a part; `at` = centre, except cylinder/cone = base centre)

| Call | Makes |
|---|---|
| `box(sx, sy, sz, at, role)` | box (12 tris) |
| `chamfer_box(sx, sy, sz, c=0.04, at, role)` | box with cut edges (44 tris): cabinets, TVs, machines |
| `beam(sx, sy, sz, n=6, at, axis='x', role)` | box cut into n segments: bend/twist/taper it |
| `cylinder(r, h, at, sides=8, role)` / `cone(r, h, at, sides=8, role)` | posts, legs, spikes |
| `sphere(r, at, segs=8, rings=6, role)` / `blob(rx, ry, rz, at, segs, rings, squash, role)` | heads, bodies, lumps |
| `torus(R, r, at, segs=12, sides=6, role)` | rings, rims (lies flat; rotate 90 on x to stand) |
| `lathe([(r, z), ...], segs=8, role)` | anything round: vases, lamps, bells, domes (r=0 closes a pole) |
| `tube(path, r, sides=6, role)` = `sweep(path, radii, ...)` | pipes, horns, tentacles; `radii` = one per point (taper) |
| `loft([[(x,y,z), ...], ...], role)` | hulls, wings (rings of points, same count each) |
| `extrude([(x, y), ...], z0, z1, role)` | flat outlines with thickness: gears, signs, blades |
| `heightfield(rows, width, depth, role)` / `card(w, h, role)` | ground patches / flat single-sided cards (sails, flags) |

## Operations (change parts in place and return them)

| Call | Does |
|---|---|
| `move(p, x, y, z)` / `rotate(p, rx, ry, rz)` (degrees, around the origin) / `scale(p, sx, sy, sz)` | place |
| `mirror(p, 'x')` | returns `[p, mirrored copy]`: model one side only |
| `array(p, n, step=(x,y,z), turn=(rx,ry,rz))` | n copies, each shifted/turned once more |
| `polar(p, n, radius, axis='z')` | n copies around an axis (cabins on a wheel, legs, petals) |
| `along(p, path, n, turn=True)` | n copies spaced along a path (teeth, rivets, fence posts) |
| `taper(p, top=0.5, axis='z')` / `twist(p, deg, axis='z')` / `bend(p, deg, along='x', up='z')` | shape (needs segments: beam, lathe, sweep); bend deg > 0 lifts both ends |
| `displace(p, amount=0.03, seed=0, scale=0.25)` | deterministic lumps (rock, bone, bark); stays closed |
| `paint(p, role)` / `paint_band(p, role, axis='z', lo, hi)` | colour a part / faces in a band (stripes on segmented parts) |
| `union(*parts)` / `group('name', *parts)` | merge / its own node `kit_<id>_<name>` (a pendulum, a lid; static today) |
| `emit(*parts)` | the result (call it at the end; lists are fine) |

## Submit, look, revise

1. Write `assets/scripts/<name>.py` inside the game folder.
2. `hermes64_character action=make project=<game> recipe=assets/scripts/<name>.py id=<needs_design id> render=true`
3. Open the returned `preview.sheet_path` image (top: front, side, back; bottom: top, three-quarter, game
   distance). Compare with what you meant. Read the numbers: triangles (budget), `size_m`, texture energy, gates.
4. Fix the script and make again with the SAME id: a new version (the last 5 kept; roll back with
   `recipe=assets/designs/<id>/v<N>.json`). `make id=<id> render=true` alone re-renders without rebuilding.
5. In a create-flow game the design replaces its placeholder on the next `create_flow run --name <game>`.

Limits: 64 KiB script, 2,000,000 steps, recursion 40, 200,000 raw triangles in (decimated to the class budget out:
prop 150, furniture 300, furniture_large 400, structure 500, building 900). Open parts (cards, heightfields,
uncapped shapes) become their own shell/card node automatically.

## Example: a grandfather clock (about 150 tris)

```python
case = chamfer_box(0.55, 0.38, 1.7, c=0.03, at=(0, 0, 0.95), role='wood')
foot = box(0.65, 0.46, 0.1, at=(0, 0, 0.05), role='wood')
hood = chamfer_box(0.62, 0.42, 0.34, c=0.04, at=(0, 0, 1.97), role='wood')
face = move(rotate(cylinder(0.2, 0.02, sides=12, role='paper'), 90, 0, 0), 0, -0.21, 1.97)
window = box(0.3, 0.02, 0.7, at=(0, -0.2, 0.95), role='glass')
rod = tube([(0, -0.215, 1.6), (0, -0.215, 0.85)], 0.012, sides=4, role='chrome')
disc = move(rotate(cylinder(0.07, 0.02, sides=10, role='chrome'), 90, 0, 0), 0, -0.205, 0.82)
emit(case, foot, hood, face, window, group('pendulum', rod, disc))
```
