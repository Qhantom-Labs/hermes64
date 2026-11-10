"""Guarded display-space RGBA decode; no Blender or subprocesses.

8-bit noninterlaced PNG uses the kit zlib decoder. JPEG and other PNG formats
need Pillow. No EXIF rotation/ICC conversion: match Blender's raw image buffer.
16-bit PNG is refused rather than silently reducing precision through Pillow.
"""
from pathlib import Path
import sys
import numpy as np
from . import guard, imgsniff
from .measure_np import MeasureError


def load_rgba(path, want_w=None, want_h=None):
    checked = guard.check_reference(str(path))
    info = imgsniff.sniff(path)
    w,h = checked['width'],checked['height']
    if want_w is not None and (w,h)!=(want_w,want_h):
        raise MeasureError('decoded size differs from guarded header')
    raw = Path(path).read_bytes()
    if info['format']=='png' and info['bit_depth']==16:
        raise MeasureError('16-bit PNG reference decoding is not verified; convert to 8-bit PNG (no automatic lossy conversion)')
    if info['format']=='png' and info['bit_depth']==8 and raw[28]==0:
        sys.path.append(str(Path(__file__).resolve().parents[1]/'kits'))
        from core import png
        try:
            a = png.decode(raw)
        except (ValueError,IndexError,KeyError) as exc:
            raise MeasureError('cannot decode PNG: '+str(exc)) from exc
        decoder = 'stdlib-png'
    else:
        try:
            from PIL import Image
        except ImportError as exc:
            raise MeasureError('Choose python_path with Pillow for JPEG/interlaced/sub-8-bit PNG; nothing was installed') from exc
        try:
            with Image.open(path) as im:
                if im.size!=(w,h):
                    raise MeasureError('decoded size differs from guarded header')
                a = np.asarray(im.convert('RGBA'),dtype=np.uint8)
        except (OSError,ValueError) as exc:
            raise MeasureError('cannot decode reference: '+str(exc)) from exc
        decoder = 'Pillow'
    # bpy multiplies by a float32 reciprocal, not float32 division. The two
    # differ by one ULP and can flip a four-decimal measured highlight bin.
    a = (a.astype(np.float32)*np.float32(1/255)).astype(np.float64)
    if a.shape[2]==3:
        a = np.concatenate([a,np.ones((h,w,1))],2)
    return a, {'decoder':decoder,'channels':4,'is_float':False,'depth':32}
