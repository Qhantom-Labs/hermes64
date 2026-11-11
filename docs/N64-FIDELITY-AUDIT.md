# N64-FIDELITY audit (round 0, "before")

Lane N64-FIDELITY, 2026-11-08. Base commit `80d5236` (real cast active by default). Question asked of every frame:
*what about this would not have shipped on an N64 in 1998?* Measured numbers below come from the commands listed;
judgements are marked as such. Private study references (14 original-N64 screenshots plus the style images listed in
STYLE-BIBLE-v0) were viewed beside every capture; they live outside the repository and are never copied, traced, sampled
or named here. Only aggregate calibration numbers derived from them appear in this file.

## How the "before" set was captured

```
python3 -m tools.roomlook capture --round 0 --games thaw,last_light --actors --out-root evidence/n64fidelity \
    --refs <private refs.json> --private-out <private folder outside the repo>
python3 -m adventure_maker.n64_gate frames evidence/n64fidelity/round-0/<game> --json .../n64-gate.json
python3 -m adventure_maker.n64_gate library --json evidence/n64fidelity/round-0/library.json
python3 -m tools.n64_table frames evidence/n64fidelity/round-0      # the table below
```

All 10 rooms (6 Thaw: pod_bay, workstation, conversation_pit, curved_corridor, dome_shelter, snow_field; 4 Last
Light: boathouse, fog_street, keepers_cottage, lamp_room), both exterior yards (snow_field, fog_street) and one
character close-up per room (new harness pass, `<room>-closeup.png`) were captured with the real cast staged.
`evidence/` is gitignored; the before frames used as committed known-bad controls are copied into
`tests/fixtures/n64fidelity/` (our own renders only).

The capture harness gained two evidence passes for this audit (UI hidden, actors visible, not inputs of the defect
gate): `<room>-noglow.png` (glow/halo cards hidden) and `<room>-classic.png` (shader global `n64_classic = 0`:
per-pixel point lights, specular glints, fresnel rims and per-pixel gloss off). Static scenery in the default frame is
byte-identical with and without the new passes (verified with a pixel diff before/after adding them: only animated
actors/particles differ).

## Per-scene findings (judgement, cross-checked with the metrics)

### Thaw interiors (pod_bay, workstation, conversation_pit, curved_corridor, dome_shelter): blue futuristic

- **Modern lighting.** Per-pixel point lights (`pixel_lights`) paint crisp round lamp pools; per-pixel Blinn
  specular glints on floors and furniture; a fresnel rim on every static surface lights ceilings at grazing angles and
  outlines furniture. Modern light energy (mean luma the classic pass removes): 0.043-0.089.
- **Bloom-like halos.** Lamp halos 1.5 m at strength 0.85 (mix) plus additive floor pools at 0.42-0.45 read as bloom
  around every warm practical; pod_bay blows out 12.2% of its pixels to luma >= 0.97.
- **PBR-ish chrome.** env-map metal with gamma 1.7, white-hot boost 1.0 from 0.88 and a 1.6 rim catch: polished modern
  metal with dashed white streaks along edges (thin white bands in the env map sampled per vertex).
- **Saturated neon blue.** Cyan screens and halo rims: 2.5% neon pixels (saturation >= 0.6, value >= 0.92) in
  workstation and conversation_pit. Grade contrast 1.2 / saturation 1.08 pushes it further.
- **Hard pixel crispness.** 320x240 shown with a nearest-neighbour 3x upscale (100% of textured 3x3 output cells
  uniform), no polygon-edge antialiasing (50-61% of strong edges step in one pixel), three-point filtering on
  un-mipmapped textures (distant sparkle).
- **High-frequency texture noise.** Fields are quantized with ordered dither: wall and floor tiles show per-texel
  speckle; the tile grid is a fine high-contrast pattern. Library: polar_pod median per-texel energy 0.030, screen 0.153.
- **Inconsistent texel density.** Furnishing roles range 8-64 texels/m (hull 16 px over 2 m beside leather 32 px over
  0.5 m); floors 32 texels/m against walls 16.
- **Different character vs world shading.** Actors sample nearest (crisp texels, pixel-edged faces) while the world is
  filtered, and get their own white rim (0.3) and kicker (0.4) on top of the world rim: they pop like modern renders.

### snow_field (Thaw exterior)

- Boxed stepped terraces with straight edges and vertical risers (right-angle grid look).
- Jagged stair-step cloud bands in the painted sky (pixel-art steps, not soft painted clouds).
- Fog colour #d9defd does not meet the visible sky horizon (#b1cffc measured): the far terrain cuts out against a
  bluer sky (fog-horizon distance 0.082).
- Rim and specular on snow and props; characters rimmed.

### fog_street (Last Light exterior, village daylight/dusk)

- Cream fog (#e2d4ae) against a blue-grey horizon (#aec3cb measured): distance 0.171, the strongest mismatch.
- Cliff walls are planar slabs; the far hills read as striped bands.
- Rim (0.28) and specular on wood/stone outdoors.

### Last Light interiors (boathouse, keepers_cottage, lamp_room): cottage warm-natural

- Legacy cutaway dioramas: low walls, no ceiling, brown background fills 15-18% of the frame; windows float on the
  wall; free-standing door frames. These defect-gate failures pre-exist at `80d5236` (round-0 gate: void 15.3-17.7%,
  floating props, uncut doors) and are recorded, not introduced by this lane.
- Plank and plaster textures carry dense streak/wave noise (forest_village median per-texel energy 0.052; band 0.188,
  fabric 0.165).
- Baked-only light (no rig): flat, low contrast (p95-p5 0.27-0.29).

## Measured round-0 frame metrics (n64_fidelity section)

`modern` = mean |luma(clean) - luma(classic)|; `glow` = mean brightening by glow/halo cards (and share of pixels
brightened by > 0.04); `clip` = share of pixels at luma >= 0.97; `neon` = share with saturation >= 0.6 and value >= 0.92;
`crisp` = share of strong 4-pixel luma ramps stepping in one pixel; `nearest up` = share of textured 3x3 output cells
that are uniform; `fog-horizon` = RMS distance of the fog colour from the measured sky horizon colour (exteriors).
The "n64 gate" column shows the status under the thresholds at the time of the run (none were defined yet).

| round | game | room | modern | glow | glow cov | clip | neon | crisp | nearest up | fog-horizon | close-up crisp |
|---|---|---|---|---|---|---|---|---|---|---|---|
| round-0 | thaw | conversation_pit | 0.0886 | 0.0011 | 0.006 | 0.0181 | 0.0249 | 0.50 | 1.00 | - | 0.46 |
| round-0 | thaw | curved_corridor | 0.0850 | 0.0034 | 0.014 | 0.0032 | 0.0083 | 0.54 | 1.00 | - | 0.54 |
| round-0 | thaw | dome_shelter | 0.0432 | 0.0010 | 0.005 | 0.0067 | 0.0018 | 0.61 | 1.00 | - | 0.81 |
| round-0 | thaw | pod_bay | 0.0601 | 0.0066 | 0.035 | 0.1216 | 0.0062 | 0.50 | 1.00 | - | 0.65 |
| round-0 | thaw | snow_field | 0.0327 | 0.0001 | 0.000 | 0.0019 | 0.0009 | 0.79 | 1.00 | 0.082 | 0.71 |
| round-0 | thaw | workstation | 0.0537 | 0.0026 | 0.013 | 0.0563 | 0.0247 | 0.50 | 1.00 | - | 0.59 |
| round-0 | last_light | boathouse | 0.0005 | 0.0003 | 0.001 | 0.0000 | 0.0000 | 0.56 | 1.00 | - | 0.64 |
| round-0 | last_light | fog_street | 0.0283 | 0.0001 | 0.001 | 0.0000 | 0.0000 | 0.73 | 1.00 | 0.171 | 0.83 |
| round-0 | last_light | keepers_cottage | 0.0006 | 0.0003 | 0.002 | 0.0000 | 0.0000 | 0.53 | 1.00 | - | 0.68 |
| round-0 | last_light | lamp_room | 0.0010 | 0.0005 | 0.003 | 0.0000 | 0.0000 | 0.56 | 1.00 | - | 0.64 |

Defect gate (unchanged thresholds) at round 0: Thaw passed; Last Light failed (interiors: cutaway/void, floating
props, uncut doors, low contrast; pre-existing).

Animation noise floor: the clean/classic/noglow passes are separate frames, so idle animation and snow particles add
up to ~0.001 mean luma to `modern`/`glow` (measured on rooms where the passes are otherwise identical).

## Measured round-0 texture library (kit packs)

Texture sizes in use: 8, 16, 32, 64 px squares; 128x64 sky/view cards. Per-texel energy = mean |L - wrapped 3x3 box
blur(L)| (0 = smooth, ordered dither and speckle raise it).

**forest_village** (median per-texel energy 0.052)

| class | spread | roles (size px / tile m = texels per m) |
|---|---|---|
| architecture | 2.00x | ceiling 32/2=16, door 32/1=32, floor 32/2=16, frame 16/1=16, roof 32/1.5=21, step 32/1=32, stone 32/2=16, trim 16/1=16, wall 32/2=16, wall_alt 32/2=16 |
| detail | 1.33x | book 32/0.4=80, paper 32/0.3=107 |
| furnishing | 4.00x | band 16/0.5=32, bark 16/1=16, body 32/1=32, body_alt 32/1=32, cushion 16/0.6=27, fabric 16/1=16, flower 16/0.5=32, foliage 32/1=32, fur 32/0.8=40, hull 32/1=32, hull_alt 16/1=16, knit 32/0.6=53, leather 32/0.5=64, post 16/1=16, quilt 32/0.5=64, rail 16/1=16, rope 16/0.3=53, wood 32/1=32 |
| ground | 2.50x | cap 16/1=16, dirt 32/2=16, field 64/7=9, grass 32/2=16, ice 32/2=16, path 32/5=6, sand 32/3=11, snow 32/3=11, water 32/3=11 |
| rockface | 1.33x | cliff 64/4=16, rock 32/1.5=21 |

noisiest textures: band 0.188, fabric 0.165, paper 0.110, flower 0.107, fire 0.098, knit 0.085, foliage 0.082, stone 0.078, quilt 0.075, roof 0.073

**polar_pod** (median per-texel energy 0.030)

| class | spread | roles (size px / tile m = texels per m) |
|---|---|---|
| architecture | 2.00x | ceiling 32/2=16, door 32/1=32, floor 64/2=32, frame 16/1=16, roof 32/2=16, step 16/1=16, stone 32/2=16, wall 32/2=16, wall_alt 32/2=16 |
| detail | 1.33x | book 32/0.4=80, paper 32/0.3=107 |
| furnishing | 8.00x | bark 16/1=16, body 16/1.5=11, cushion 32/0.6=53, fabric 16/1=16, flower 16/0.5=32, foliage 32/1=32, fur 32/0.8=40, hull 16/2=8, knit 32/0.6=53, leather 32/0.5=64, quilt 32/0.5=64, rope 16/0.3=53, wood 16/1=16 |
| ground | 2.50x | cap 16/1.5=11, dirt 32/2=16, field 64/4=16, grass 32/3=11, ice 32/2=16, path 32/5=6, sand 32/3=11, snow 32/3=11, water 32/3=11 |
| rockface | 1.33x | cliff 64/4=16, rock 32/1.5=21 |

noisiest textures: screen 0.153, book 0.108, foliage 0.103, paper 0.081, fire 0.070, knit 0.067, view 0.053, ceiling 0.049, stone 0.046, light 0.043

## Calibration on the private references (aggregate numbers only)

Each private reference was centre-cropped to 4:3 and resized to 320x240 with bilinear filtering (a fair stand-in for a
soft N64 frame; sources are emulator/TV captures of different sizes, so these are indicative, not exact):

| metric | 14 references | round-0 renders |
|---|---|---|
| crisp edge fraction | 0.00-0.23 (median 0.07) | 0.50-0.79 |
| clip fraction (luma >= 0.97) | 0.0000-0.0016 | 0.0000-0.1216 |
| neon fraction (whole frame incl. sky) | 0.000-0.071 (vivid skies count) | interiors up to 0.025 (no sky) |

Triangle counts at round 0 (scene cap 6,000 incl. actors): Thaw 4,900-5,636; Last Light 1,814-5,442.

## What this audit does not establish

- It does not certify authenticity or beauty; the metrics catch specific modern tells only.
- The reference calibration compares frames of different provenance (different capture chains); thresholds keep a
  margin from our own before/after numbers rather than claiming parity with the references.
- Gameplay, layouts, story, bindings and tests are out of scope and unchanged.
