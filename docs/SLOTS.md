# Texture slots and overlays

Put your own crest, shop sign, team mark or poster on a kit's signs and banners. You don't need an image file. A
texture slot is filled by a small JSON drawing (a **mask recipe**). The build paints it into the kit's atlas, using
the pack's own colours and filtering, so it matches the rest of the kit.

## 1. Slots a pack offers

Each kit pack lists its slots in `kits/packs/<pack>/slots.json` (`hermes64-texture-slots/1`).

| Pack | Slot | Where it shows | Cell |
|---|---|---|---|
| `neon_city_night`, `neon_dawn`, `cyber_blue_grid` | `emblem_tower` | blade signs: `cysign.roof` (four 13x9 glyph boxes from rows 11-47), `cysign.blade`, `cysign.hotel`, `cytower.annex`, `cytower.arch` | paper atlas, 16x64 |
| | `emblem_screen` | monitors: `cytech.terminal`, `cytech.charger`, `cyroom.desk`, `cyroom.turnstile`, `cysign.arcade`, `cysign.clinic` | book atlas, 32x32 |
| | `poster_mascot` | billboards: `cysign.billboard`, `cysign.adpanel`, `cytower.wedge` | book atlas, 64x32 |
| | `emblem_sky` | the room presentation `sky_signal` (disc emblem) | sheet, 64x64 with a transparent tone; an overlay may give a picture instead (32/64/128, section 3b) |
| | `emblem_jacket` | declared only: no character consumer in this build | sheet, 32x32 |
| `castle_keep`, `medieval_village` (+ dusk/night/snow) | `banner_crest` | `cst.banner` cloth | band atlas, 32x32 |
| | `banner_crest_cross` | `cst.banner__cross` cloth | band atlas, 32x32 |

**Unfilled slots.** An atlas slot keeps the pack's own painting, byte for byte. A sheet slot uses the pack's
`default`: for `emblem_sky` that is an empty halo, and it is baked only when a room actually has a `sky_signal`.

**Adding slots to another pack.** Write its `slots.json`. Each slot names:
- the material role (`"role"`) and the cell in texels (`"cell": [x, y, w, h]`, row 0 at the top);
- `"tones"`: the names a recipe may use, each mapped to a step of that role's ramp;
- `"pieces"`: the pieces that show the slot. The tests check that each listed piece has UVs inside the cell.

No kit code changes.

## 2. Writing a mask recipe (`hermes64-mask/1`)

```json
{"format": "hermes64-mask/1", "name": "open sign", "grid": 32, "rows": 16,
 "tones": ["dark", "white", "a"], "background": 0,
 "prims": [{"op": "text5x7", "text": "OPEN", "at": [4, 4], "tone": 1},
           {"op": "rect", "at": [1, 13], "size": [30, 1], "tone": 2}]}
```

**Grid.** `grid` is the number of columns: 16, 32 or 64. `rows` is 8 to 64 and defaults to `grid`. The grid must
fit the slot's cell at a whole-number scale with the same aspect. For example, a 32x16 grid fits the 64x32
billboard at 2x.

**Tones.** List one to three names from the slot's `tones`. Primitives refer to a tone by its index in that list.
`background` is the tone index that fills the cell first.

**Primitives** are drawn in order; later ones paint over earlier ones.

| Primitive | Fields |
|---|---|
| `rect` | `at`, `size` |
| `disc` | `at`, `r` |
| `poly` | `points`, 3 to 32 points |
| `stroke` | `points`, 2 to 32 points, optional `width` 0.5-8 |
| `text5x7` | `text` (A-Z, 0-9 and space, up to 12 characters), `at`, optional `scale` 1-4 |

**Coordinates** are grid units. A pixel is drawn when its centre is inside the shape, so there is no smoothing.

**Limits.** At most 64 primitives and 8 KB of JSON. Fields are closed (unknown fields are rejected).

**What is refused.** A recipe is never an image and never a path. Any of these is rejected with a stable error code:
- a file name or path given as a slot value: `slot_value_path`
- a field the format doesn't define: `mask_field`
- an unknown primitive: `mask_unknown_op`
- a tone the slot doesn't offer: `mask_off_ramp`
- a grid that doesn't fit the cell: `mask_cell_fit`

**Preview** a recipe before building:

```sh
python3 -B -m tools.mask_preview my.mask.json --pack neon_city_night --slot poster_mascot --out preview.png --zoom 8
```

## 3. Filling slots in a game

**Project values** go in the project file `textures/slots.json`:

```json
{"format": "hermes64-texture-values/1", "slots": {"banner_crest": {...recipe...}}}
```

They are part of the game and ship in every export.

**Overlay.** The project folder `overlay/` holds content you can remove without changing the game, such as a
sponsor mark or event branding:

```
overlay/overlay.json                 {"format": "hermes64-overlay/1", "name", "enabled": true,
                                      "licence": "...", "source": "...",
                                      "textures": {"<slot>": {"file": "textures/<slot>.mask.json", "sha256": "...",
                                                              "licence": "...", "source": "..."}},
                                      "audio": {"slots": "audio/slots.json", "import": "audio/import"}}
overlay/textures/<slot>.mask.json    mask recipes only (*.mask.json)
overlay/images/*.png|jpg|jpeg        pictures for sheet slots that accept them (section 3b)
overlay/audio/                       AUDIOPIPE's own slots.json + import folder (docs/AUDIO-IMPORT.md);
                                     import into it with tools/audio_import.py --out overlay/audio/import
```

The `licence` and `source` fields are required. Overlay values replace project values.

- Overlay audio is checked by AUDIOPIPE's own verifier and lowered by AUDIOPIPE's own code. Overlay rows replace the
  project's rows for the same events.
- Set `"enabled": false` to switch the overlay off without deleting it.

**Build report.** `hermes64_build_assets`, `open`, `replay` and `export` all stage the slots. Each build writes
`<run>/slots-report.json`, which lists:
- every slot: `pack` (unfilled), `pack_default`, `project` or `overlay`, with the recipe sha256 and the baked PNG
  sha256;
- every overlay file, with its sha256, licence and source;
- the audio events the overlay filled.

The baked PNGs are hash-checked release media in an export.

**Neutral export.** Exporting with `overlay: "neutral"` ignores `overlay/` completely. This is an internal argument
for `adventure_maker.export.run`; the tool schema is unchanged. The export then runs a **leak check**. It scans every
file in the staged release, including zip members, for:
- any overlay file's sha256;
- any PNG baked from an overlay value;
- any overlay file's bytes embedded in a larger file.

Any hit fails the export with `overlay_leak`. The result is stored under `leak_check` in `slots-report.json`.

## 3b. Picture values (overlay only)

An overlay may fill a **sheet** slot that lists `"image"` in its `slots.json` with a local PNG or JPEG kept in the
overlay folder. Today that is `emblem_sky` on the cyber packs (`"image": {"grids": [32, 64, 128]}`). Atlas slots,
project values (`textures/slots.json`) and premises never take a picture: they keep using mask recipes, and a picture
there fails with `image_slot` / `image_overlay_only`.

```json
"textures": {"emblem_sky": {
  "kind": "image", "file": "images/club-logo.png", "sha256": "<sha256 of the file>",
  "licence": "who owns it", "source": "where it came from",
  "permission": "who allowed this use (as you know it)",
  "crop": [x, y, w, h],      // source pixels; square; inside the image
  "grid": 64,                // output size: one of the slot's image grids (32, 64, 128)
  "mask": "disc",            // "disc": transparent outside the inscribed circle; "none": the full square
  "mode": "direct",          // "direct": crop + resize, full colour; "ramp": palette of `colours` colours
  "filter": "box",           // resize filter: nearest, box, bilinear, lanczos
  "colours": 16,             // ramp only: 2-64
  "alpha_threshold": 128,    // optional: see "Cut-out pictures"
  "pad": "clear",            // optional
  "gray": true}}             // optional
```

**Cut-out pictures (optional fields).** For a figure on a transparent background (a PNG with alpha):
- `"alpha_threshold": 128` makes source pixels with alpha >= 128 fully opaque and the rest fully clear, with no
  colour, **before** the resize. A soft or dark anti-aliased edge then cannot mix into the edge texels, and a figure
  whose alpha is just under 255 counts as opaque.
- `"pad": "clear"` lets the crop extend past the image edges (x or y may be negative); the area outside is
  transparent. The crop must still overlap the image. Use it when the figure's square box is wider than the image.
- `"gray": true` turns the picture to luminance (R = G = B) before the resize, so a black-and-white picture stays
  gray after the 5-bit step.
- `overlay_image.alpha_bbox_square(alpha, 128)` returns the figure's bounding box padded to a square, as a crop.

Without these fields, the result is byte for byte what it was before.

**What the build does.** It crops, resizes with the chosen filter, applies the disc, and in `ramp` mode picks a
palette of `colours` colours from the visible texels (a fixed median cut). Both modes then apply the N64 16-bit
texel limit: 5 bits per colour channel and 1-bit alpha (RGBA5551). Hidden texels are stored as transparent black.
Sheets get no soften or dither in the pack's normal path, so pictures get none either. Same file + same parameters
give the same bytes.

**What is refused.** Each has a stable code:
- a URL or `data:` value: `overlay_url`;
- a path outside the overlay folder, an absolute path or a backslash: `overlay_path`;
- a symlink anywhere on the path, even one pointing inside the folder: `overlay_symlink`;
- a file over 4 MB, or an image over 4096 px a side or 16 M pixels: `image_size`;
- an animated PNG, or a multi-frame image: `image_animated`;
- GIF, WebP, anything that isn't PNG or JPEG by extension and by signature: `image_format`;
- a crop outside the image or not square: `image_crop`;
- a missing `licence`, `source` or `permission`: `overlay_licence`;
- an unknown field: `image_field`.

The file checks read only the file header. Pillow is used only when an overlay build actually bakes a picture. If
Pillow is missing, that build fails with `image_pillow`. Neutral builds and the neutral leak check never import
Pillow.

**Neutral export.** The leak check also looks for:
- the picture file's hash and its bytes, including inside zip members;
- the sheets that earlier overlay builds of the same project baked from the picture. These are read from their
  `slots-report.json`.

**Report.** The `emblem_sky` row in `slots-report.json` has `"kind": "image"` and the full parameters, plus
`source_file`, `dims`, `licence`, `source`, `permission` and the baked `png_sha256`. The overlay `files` list has the
picture with its sha256, licence and permission.

## 4. Runtime

`runtime/godot/view/slots.gd` is called once per room from `view/room.gd`. It checks the hash of each baked atlas,
then puts it on every surface of that material role, including surfaces added later. It also passes the emblem sheet
to the room's `sky_signal` as its `texture`, unless the room already sets its own. Games built without slots have no
`texture_slots` entry in `theme.json`, and nothing changes for them.

## 5. Example

`examples/slots-heraldry/` puts a crest on `banner_crest` (project value) and a guild mark on `banner_crest_cross`
(overlay), for the medieval packs.
