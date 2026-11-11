# CYBERKIT

**Candidate / NOT VERIFIED for art release.** Main owns acceptance. Numeric gate passes are not human art approval. See [results](CYBERKIT-RESULT.md), [checkpoint](../CYBERKIT-CHECKPOINT.md), and the retained rejected rounds.

## What is shipped

An original late-1990s 3D console adventure cyber-city kit: painted code-generated textures, beveled/tapered geometry, baked vertex lighting/AO, restrained emissive glyph signage, soft runtime filtering, and layered rain-haze skyline cards. No borrowed franchise assets or branding. Private study pixels are not shipped.

| Family | Generators | Keys including presets | Triangle range |
|---|---:|---:|---:|
| `cytower.` | 14 | 20 | 124–578 |
| `cystreet.` | 15 | 17 | 20–310 |
| `cysign.` | 14 | 16 | 40–414 |
| `cytech.` | 16 | 19 | 14–402 |
| `cyroom.` | 17 | 18 | 32–706 |
| `cydress.` | 14 | 14 | 32–148 |
| `cysky.` | 14 | 21 | 2–184 |

104 generators, 125 cyber piece keys. Each key has all three palette-role variants. Including the separate `sky.backdrop` support asset, the library has 378 GLBs. The complete per-piece table is [INVENTORY.md](cyberkit/INVENTORY.md); machine counts are in [inventory.json](cyberkit/inventory.json).

## Profiles and palette roles

- `neon_city_night`: shadow blue-violet, steel/concrete, cyan, magenta, amber, violet holograms, restricted light cores, wet pavement and violet rain haze.
- `cyber_blue_grid`: navy/blue steel, cyan light, amber windows, blue haze and thin holographic line/network cards. Darkest steel was lifted to keep real surfaces distinct from interior fog.
- `neon_dawn`: the night palette with a different painted sky, window-light mix, warm key, dawn city sky/fill balance and haze distance. It is not an unrelated recolour of geometry.

Palette names and role membership live in `tools/cyberkit_packs.py`. Materials, texture ramps, environment maps and bake ramps use those roles. Slots a/b/c/d select the original cyan/magenta/amber/violet-or-blue atlases. Broad painted fields are filtered before palette quantisation; glyph, tube, banner and window atlases are not blurred across slot boundaries.

`kits/packs/<id>/pack.json` is build/bake data. `packs/<id>/{pack,view,bindings}.json` is the regular plugin/runtime style path. The view factories import the dungeon `STYLE_GATE` unchanged and do not override the shared N64 convention. City, roof and interior lighting are separately authored profiles; no runtime or contract changes are needed.

## Geometry and sockets

The classic generators use the existing validated Python builder. Custom relief-sheet interiors and skyline silhouettes did not require a dependency on the unfinished recipe lane. They introduce no plugin tool or schema.

The city uses 4 m cells, 12 m street frontage and 90-degree snapping. Read `kits/library/cyberkit-sockets.json` rather than guessing placement offsets. Positions in exported metadata are Godot Y-up; construction helpers use Blender-style Z-up internally.

- Street endpoints pair at the same world point with opposite facing and the same width/datum.
- Facades and shopfronts are frontage-anchored; signs can be explicitly mounted.
- Shell door openings match the normal room doorway anchors, including even-width shells. A ray regression checks the rooftop south opening.
- A reusable transition frame is open. Only closed interior shells own the dark tunnel backing; exterior transitions must not become opaque black rectangles in the road.
- Roof/ground anchors and free skyline dressing are explicit. Skyline cards have a below-deck skirt. The demo tiles narrower cards and tags them as vistas so the existing horizon fitting can see their true extent.

The compiler in `tools/cyberkit_rooms.py` consumes the manifest and refuses off-grid rotations, unpaired sockets and over-budget plans. It uses a conservative people-inclusive estimate; the actual runtime triangle counts are also checked.

## Demo

`examples/cyberkit-demo/spec.json` is generated through the normal region/room contract. The four linked regions are street canyon, rooftop, club and subway. The real Service scaffold/compile/check/build_assets/open path is exercised, not a separate mock renderer.

The two people are explicitly named placeholder courier/operator and reuse the existing public `fv_scribe` / `fv_warden` selectors. No character geometry, textures or rig art is changed.

## Reproduce

Use the existing Python 3.9 + numpy and installed Godot. No installation or network is required. Pin the executable: background shells on the authoring host selected a different bare `python3` than foreground commands. The verified host route is `/usr/bin/python3` (3.9.6, numpy 2.0.2); choose an equivalent installed 3.9 executable elsewhere.

```sh
PY39=/usr/bin/python3
export HERMES64_NUMPY_PYTHON="$PY39"
"$PY39" --version
"$PY39" -B -m tools.cyberkit_packs write
"$PY39" -B -m tools.cyberkit_style write
"$PY39" -B -m tools.cyberkit_library all
"$PY39" -B -m tools.cyberkit_library verify
"$PY39" -B -m tools.cyberkit_handoff inventory
"$PY39" -B -m tools.cyberkit_demo write
"$PY39" -B -m tools.cyberkit_demo plan
"$PY39" -B -m tools.cyberkit_demo check
```

Choose a fresh numeric round; immutable capture folders are never overwritten. A matrix resumes only if its source/data pins are identical. It appends a journal per capture, then deduplicates and counts the read-back evidence.

```sh
"$PY39" -B -m tools.cyberkit_matrix --round 101
"$PY39" -B -m tools.cyberkit_overview --round 101
```

The matrix covers three profiles, four bearings, four rooms and clean/close-up frames, checks both gates, image coverage, input stability and the people-inclusive 6,000-triangle cap. Any failure is a failing exit code. Every render still needs actual visual review.

The style factory, direct capture and matrix validate all shared environment setting ranges before rendering. Image-gate passes alone do not excuse illegal contrast, ambient or fill values. Published refpack receipts use repo-relative paths; raw execution receipts stay in ignored evidence. The packaging privacy scan must remain clean.

```sh
"$PY39" -B -m tools.cyberkit_controls
"$PY39" -B -m tools.cyberkit_library determinism
"$PY39" -B -m unittest tests.test_cyberkit tests.test_cyberkit_rooms
```

The main-regression helper builds every pre-existing default in its two native profiles in independent Python processes, comparing with an exact local `main` archive. Its evidence folder is intentionally immutable; use a fresh checkout for a new baseline rather than deleting the old receipt.

```sh
"$PY39" -B -m tools.cyberkit_regression
"$PY39" -B -m tools.cyberkit_moods paint
"$PY39" -B -m tools.cyberkit_moods check
```

The reference-to-pack images are original independent paintings, not screenshots or samples from authored pack colours. Its real draft/proxy proof is a diagnostic, not accepted cyber artwork.

Before `sh tools/verify_all.sh`, check `ps` and confirm the cwd of any other verifier. Do not start a second verifier in this worktree. Keep the actual run log and its `evidence/verify-*/results.json`. Run `hermes plugins validate .` on the exact production tree; document timeouts and the validated tree scope. Main must repeat the render matrix after integration if shared runtime behaviour changes.

The rooftop is a dark painted service deck, not the luminous interior floor. Dawn exposes purpose-painted lapped membrane seams rather than added random noise. The optional overlapping tower and oversized foreground antenna instances were removed from the demo, not from the reusable library. The four authored views remain different real camera positions; no private reference pixels or post-edited screenshots are used as acceptance evidence.

See [reproduction lessons](cyberkit/WORKFLOW.md) for diagnostics versus real proof, immutable rounds, profile preflight, warning auditing and the unrelated missing historical full-suite fixture.
