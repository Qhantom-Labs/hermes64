"""Overlay-only IMAGE slot values (lane SLOTS2).

An overlay (never a project value, never a premise) may fill a sheet slot that declares `"image"` in its pack's
slots.json with a local picture inside the overlay folder:

    overlay.json  "textures": {"emblem_sky": {
        "kind": "image", "file": "images/face.jpeg", "sha256": "<file sha256>",
        "licence": "...", "source": "...", "permission": "who allowed this use, as reported by the user",
        "crop": [x, y, w, h],          # source pixels, square, inside the image
        "grid": 64,                    # output size: 32, 64 or 128 (and listed in the slot's image.grids)
        "mask": "disc",                # "disc" (alpha 0 outside the inscribed circle) or "none"
        "mode": "direct",              # "direct": crop + resize, full colour; "ramp": palette of `colours` colours
        "filter": "box",               # resize filter: nearest, box, bilinear, lanczos
        "colours": 16,                 # ramp mode only: 2..64
        "alpha_threshold": 128,        # optional (lane SLOTS3): source alpha >= t -> opaque, else clear, BEFORE the
                                       # resize (pictures with a soft or near-opaque cut-out edge: no fringe)
        "pad": "clear",                # optional: the crop may extend past the image edges; outside is transparent
        "gray": true}}                 # optional: luminance (R=G=B) before the resize; grayscale stays grayscale

Both modes end with the N64 16-bit texel limit the sheet consumer gets: RGBA5551 (5 bits per colour channel,
1-bit alpha at 128). Sheets get no soften/dither in the pack's normal path (`mask_recipe.bake_sheet`), so none here.

Refused (stable codes): URLs and data: values (`overlay_url`), paths outside the folder (`overlay_path`), symlinks
anywhere on the path (`overlay_symlink`), other extensions or file signatures (`image_format`), files over
MAX_FILE_BYTES or images over MAX_DIM / MAX_PIXELS (`image_size`), animated PNG/GIF/MPO (`image_animated`),
unknown fields or bad parameters (`image_field` / `image_range`), crop outside the image or not square
(`image_crop`). The file checks use no Pillow; Pillow is imported only by `bake`, i.e. only in an overlay-applied
build. Neutral builds and the neutral leak check never import it.

Determinism: decoding is Pillow's (JPEG/PNG), the resize filter is Pillow's, the palette is a fixed median cut in
numpy (ties broken by index), no clock, no randomness, no EXIF rotation (pixels as stored).
"""
import hashlib
import json
from pathlib import Path

import numpy as np

IMAGE_KEYS = {'kind', 'file', 'sha256', 'licence', 'source', 'permission', 'crop', 'grid', 'mask', 'mode',
              'filter', 'colours', 'name', 'alpha_threshold', 'pad', 'gray'}
PADS = ('none', 'clear')
REQUIRED = {'kind', 'file', 'sha256', 'licence', 'source', 'permission', 'crop', 'grid', 'mode'}
GRIDS = (32, 64, 128)
MODES = ('direct', 'ramp')
MASKS = ('none', 'disc')
FILTERS = ('nearest', 'box', 'bilinear', 'lanczos')
EXTS = ('.png', '.jpg', '.jpeg')
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_DIM = 4096
MAX_PIXELS = 16 * 1024 * 1024
MIN_CROP = 8
MAX_COLOURS = 64
MAX_TEXT = 600


class ImageSlotError(ValueError):
    def __init__(self, code, message):
        super().__init__('%s: %s' % (code, message))
        self.code = code


def _fail(code, message):
    raise ImageSlotError(code, message)


def is_image_row(row):
    return isinstance(row, dict) and row.get('kind') == 'image'


def validate_spec(row, where='image'):
    """Closed-field check of an overlay image row. Returns the normalised parameters (canonical order)."""
    if not isinstance(row, dict):
        _fail('image_field', '%s must be an object' % where)
    extra = set(row) - IMAGE_KEYS
    missing = REQUIRED - set(row)
    if extra or missing:
        _fail('image_field', '%s: missing %s, unknown %s' % (where, sorted(missing), sorted(extra)))
    for k in ('licence', 'source', 'permission'):
        if not isinstance(row[k], str) or not row[k].strip() or len(row[k]) > MAX_TEXT:
            _fail('overlay_licence', '%s.%s must be a short non-empty note (who made it, under what permission)' % (where, k))
    sha = row['sha256']
    if not isinstance(sha, str) or len(sha) != 64 or any(ch not in '0123456789abcdef' for ch in sha):
        _fail('image_field', '%s.sha256 must be the file\'s lowercase hex sha256' % where)
    crop = row['crop']
    if not (isinstance(crop, list) and len(crop) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in crop)):
        _fail('image_crop', '%s.crop must be [x, y, w, h] integer source pixels' % where)
    pad = row.get('pad', 'none')
    if pad not in PADS:
        _fail('image_range', '%s.pad must be one of %s' % (where, list(PADS)))
    x, y, w, h = crop
    lo = -MAX_DIM if pad == 'clear' else 0
    if x < lo or y < lo or w < MIN_CROP or h < MIN_CROP or w != h or x + w > MAX_DIM or y + h > MAX_DIM \
            or w > MAX_DIM:
        _fail('image_crop', '%s.crop %s: square, at least %d px, inside the image (or overlapping it with pad '
                            '"clear")' % (where, crop, MIN_CROP))
    grid = row['grid']
    if isinstance(grid, bool) or grid not in GRIDS:
        _fail('image_range', '%s.grid must be one of %s' % (where, list(GRIDS)))
    mode = row['mode']
    if mode not in MODES:
        _fail('image_range', '%s.mode must be one of %s' % (where, list(MODES)))
    mask = row.get('mask', 'none')
    if mask not in MASKS:
        _fail('image_range', '%s.mask must be one of %s' % (where, list(MASKS)))
    filt = row.get('filter', 'box')
    if filt not in FILTERS:
        _fail('image_range', '%s.filter must be one of %s' % (where, list(FILTERS)))
    out = {'kind': 'image', 'file': row['file'], 'sha256': sha, 'crop': list(crop), 'grid': grid, 'mask': mask,
           'mode': mode, 'filter': filt}
    if mode == 'ramp':
        n = row.get('colours', 16)
        if isinstance(n, bool) or not isinstance(n, int) or not 2 <= n <= MAX_COLOURS:
            _fail('image_range', '%s.colours must be an integer 2..%d' % (where, MAX_COLOURS))
        out['colours'] = n
    elif 'colours' in row:
        _fail('image_field', '%s.colours applies to mode "ramp" only' % where)
    if 'alpha_threshold' in row:
        t = row['alpha_threshold']
        if isinstance(t, bool) or not isinstance(t, int) or not 1 <= t <= 255:
            _fail('image_range', '%s.alpha_threshold must be an integer 1..255' % where)
        out['alpha_threshold'] = t
    if pad != 'none':
        out['pad'] = pad
    if 'gray' in row:
        if not isinstance(row['gray'], bool):
            _fail('image_range', '%s.gray must be true or false' % where)
        if row['gray']:
            out['gray'] = True
    name = row.get('name', '')
    if not isinstance(name, str) or len(name) > 64 or '/' in name or '\\' in name:
        _fail('image_field', '%s.name must be a short label' % where)
    return out


def spec_sha256(spec):
    """Value hash of an image slot: the conversion parameters + the source file's sha256."""
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def resolve_file(base, rel, where='image'):
    """Resolve an image file inside `base` with no Pillow: refuses URLs, escapes, symlinks, wrong extensions or
    signatures, oversized files/dimensions and animated PNGs. Returns (path, raw bytes, (width, height))."""
    if not isinstance(rel, str) or not rel:
        _fail('overlay_path', '%s.file must be a relative path' % where)
    low = rel.strip().lower()
    if '://' in low or low.startswith(('data:', 'http:', 'https:', 'file:', 'ftp:', '//')):
        _fail('overlay_url', '%s.file is a URL; overlay images are local files inside the overlay folder' % where)
    if rel.startswith(('/', '\\')) or ':' in rel or '\\' in rel or '..' in Path(rel).parts:
        _fail('overlay_path', '%s.file must be a relative path inside the overlay folder' % where)
    if not low.endswith(EXTS):
        _fail('image_format', '%s.file must be .png, .jpg or .jpeg' % where)
    base = Path(base)
    cur = base
    for part in Path(rel).parts:
        cur = cur / part
        if cur.is_symlink():
            _fail('overlay_symlink', '%s.file: %s is a symlink' % (where, cur.relative_to(base).as_posix()))
    if not cur.is_file():
        _fail('overlay_missing', '%s.file not found: %s' % (where, rel))
    if base.resolve() not in cur.resolve().parents:
        _fail('overlay_path', '%s.file escapes the overlay folder' % where)
    size = cur.stat().st_size
    if size > MAX_FILE_BYTES:
        _fail('image_size', '%s.file is %d bytes (limit %d)' % (where, size, MAX_FILE_BYTES))
    raw = cur.read_bytes()
    dims = header_dims(raw, where)
    if dims[0] > MAX_DIM or dims[1] > MAX_DIM or dims[0] * dims[1] > MAX_PIXELS:
        _fail('image_size', '%s.file is %dx%d (limit %d per side, %d pixels)' % (where, dims[0], dims[1], MAX_DIM, MAX_PIXELS))
    return cur, raw, dims


def check_crop(spec, dims, where='image'):
    if not crop_fits(spec, dims):
        _fail('image_crop', '%s.crop %s is outside the %dx%d image' % (where, spec['crop'], dims[0], dims[1]))


def crop_fits(spec, dims):
    """Inside the image; with pad "clear", overlapping it (the rest is transparent)."""
    x, y, w, h = spec['crop']
    if spec.get('pad') == 'clear':
        return x < dims[0] and y < dims[1] and x + w > 0 and y + h > 0
    return x >= 0 and y >= 0 and x + w <= dims[0] and y + h <= dims[1]


def alpha_bbox_square(alpha, threshold=128):
    """Helper for authors: the bounding box of alpha >= threshold, padded to a square around its centre.
    alpha: (h, w) uint8 array. Returns [x, y, side, side] (may extend past the image: use pad "clear")."""
    ys, xs = np.nonzero(np.asarray(alpha) >= threshold)
    if not len(xs):
        _fail('image_crop', 'no pixel has alpha >= %d' % threshold)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    side = max(x1 - x0, y1 - y0)
    return [x0 - (side - (x1 - x0)) // 2, y0 - (side - (y1 - y0)) // 2, side, side]


def header_dims(raw, where='image'):
    """(width, height) from the PNG IHDR / JPEG SOFn header, no decoding. Animated PNG (acTL) is refused."""
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        if raw[12:16] != b'IHDR':
            _fail('image_format', '%s: PNG without IHDR' % where)
        w, h = int.from_bytes(raw[16:20], 'big'), int.from_bytes(raw[20:24], 'big')
        i = 8
        while i + 8 <= len(raw):
            n = int.from_bytes(raw[i:i + 4], 'big')
            typ = raw[i + 4:i + 8]
            if typ == b'acTL':
                _fail('image_animated', '%s: animated PNG (APNG) is not accepted' % where)
            if typ in (b'IDAT', b'IEND'):
                break
            i += 12 + n
        return w, h
    if raw[:3] == b'\xff\xd8\xff':
        i = 2
        while i + 4 <= len(raw):
            if raw[i] != 0xFF:
                i += 1
                continue
            marker = raw[i + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                i += 2 if marker != 0xFF else 1
                continue
            seg = int.from_bytes(raw[i + 2:i + 4], 'big')
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = int.from_bytes(raw[i + 5:i + 7], 'big'), int.from_bytes(raw[i + 7:i + 9], 'big')
                return w, h
            i += 2 + seg
        _fail('image_format', '%s: JPEG without a frame header' % where)
    if raw[:6] in (b'GIF87a', b'GIF89a'):
        _fail('image_format', '%s: GIF is not accepted (PNG or JPEG only)' % where)
    _fail('image_format', '%s: not a PNG or JPEG file' % where)


# ---------------------------------------------------------------- conversion (Pillow lives only below)
def _median_cut(rgb, n):
    """Deterministic median cut: (k, 3) uint8 pixels -> (palette (m, 3) uint8, index per pixel). Splits the box with
    the widest channel range at its median; ties go to the lowest box index, then the lowest channel."""
    pix = rgb.astype(np.int64)
    boxes = [np.arange(len(pix))]
    while len(boxes) < n:
        best, best_rng, best_ch = -1, 0, 0
        for bi, idx in enumerate(boxes):
            if len(idx) < 2:
                continue
            p = pix[idx]
            rng = p.max(axis=0) - p.min(axis=0)
            ch = int(np.argmax(rng))
            if rng[ch] > best_rng:
                best, best_rng, best_ch = bi, int(rng[ch]), ch
        if best < 0:
            break
        idx = boxes[best]
        order = idx[np.lexsort((idx, pix[idx, best_ch]))]
        half = len(order) // 2
        boxes[best:best + 1] = [order[:half], order[half:]]
    pal = np.array([np.round(pix[idx].mean(axis=0)) for idx in boxes], dtype=np.int64)
    d = ((pix[:, None, :] - pal[None, :, :]) ** 2).sum(axis=2)
    return pal.astype(np.uint8), np.argmin(d, axis=1)


def to_5551(rgba):
    """N64 16-bit texel: 5 bits per colour channel (expanded back to 8 by bit replication), 1-bit alpha at 128."""
    out = rgba.copy()
    c = out[..., :3] >> 3
    out[..., :3] = (c << 3) | (c >> 2)
    out[..., 3] = np.where(out[..., 3] >= 128, 255, 0)
    return out


def disc_alpha(grid):
    yy, xx = np.mgrid[0:grid, 0:grid].astype(np.float64)
    c = grid / 2.0
    return ((xx + 0.5 - c) ** 2 + (yy + 0.5 - c) ** 2) <= c * c


def convert(raw, spec, where='image'):
    """Image bytes + validated spec -> (grid, grid, 4) uint8 RGBA. The only Pillow import in the slot code."""
    import io
    try:
        from PIL import Image
    except ImportError:
        _fail('image_pillow', 'overlay image slots need Pillow in the Python that runs Hermes (python3 -m pip install Pillow)')
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        im = Image.open(io.BytesIO(raw))
        fmt = im.format
        if fmt not in ('PNG', 'JPEG'):
            _fail('image_format', '%s: decoded as %s, not PNG or JPEG' % (where, fmt))
        if getattr(im, 'is_animated', False) or getattr(im, 'n_frames', 1) != 1:
            _fail('image_animated', '%s: animated or multi-frame image is not accepted' % where)
        if im.width > MAX_DIM or im.height > MAX_DIM:
            _fail('image_size', '%s: %dx%d' % (where, im.width, im.height))
        x, y, w, h = spec['crop']
        if not crop_fits(spec, (im.width, im.height)):
            _fail('image_crop', '%s.crop %s is outside the %dx%d image' % (where, spec['crop'], im.width, im.height))
        im = im.convert('RGBA')
    except ImageSlotError:
        raise
    except Exception as e:      # truncated / corrupt / bomb
        _fail('image_format', '%s: cannot decode (%s)' % (where, type(e).__name__))
    filt = {'nearest': Image.NEAREST, 'box': Image.BOX, 'bilinear': Image.BILINEAR, 'lanczos': Image.LANCZOS}[spec['filter']]
    g = spec['grid']
    src = prepare(np.asarray(im, dtype=np.uint8), spec)
    small = Image.fromarray(src).crop((x, y, x + w, y + h)).resize((g, g), resample=filt)   # outside -> (0,0,0,0)
    out = np.asarray(small, dtype=np.uint8).copy()
    if spec['mask'] == 'disc':
        out[..., 3] = np.where(disc_alpha(g), out[..., 3], 0)
    seen = out[..., 3] >= 128
    if spec['mode'] == 'ramp' and seen.any():      # palette from the visible texels only
        pal, idx = _median_cut(out[..., :3][seen], spec['colours'])
        out[..., :3][seen] = pal[idx]
    out[..., :3][~seen] = 0                         # hidden texels carry no picture data
    return to_5551(out)


def prepare(rgba, spec):
    """Source-resolution steps before crop + resize (numpy integer math): `gray` -> R=G=B = ITU-R 601 luma;
    `alpha_threshold` t -> alpha 255 where alpha >= t, else 0 with no colour (so a soft or dark cut-out edge cannot
    bleed into the resized texels). Without either field the pixels pass through unchanged."""
    out = np.array(rgba, dtype=np.uint8, copy=True)
    if spec.get('gray'):
        c = out[..., :3].astype(np.int64)
        y = (c[..., 0] * 299 + c[..., 1] * 587 + c[..., 2] * 114 + 500) // 1000
        out[..., :3] = y[..., None].astype(np.uint8)
    t = spec.get('alpha_threshold')
    if t is not None:
        keep = out[..., 3] >= t
        out[..., 3] = np.where(keep, 255, 0)
        out[..., :3][~keep] = 0
    return out


def bake(raw, spec, where='image'):
    """PNG bytes of the converted sheet (kits/core/png encoder, deterministic)."""
    try:
        from ..kits.core import png
    except ImportError:
        from kits.core import png
    return png.encode(convert(raw, spec, where))
