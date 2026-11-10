"""Canonical PCM encoder. Refuse overflow instead of silently clipping."""

import io
import math
import struct
import wave

from . import SAMPLE_RATE
from .validate import ValidationError


def encode(samples):
    pcm = bytearray()
    for sample in samples:
        if not math.isfinite(sample):
            raise ValidationError("numeric", "non-finite encoder input")
        if abs(sample) >= 1.0:
            raise ValidationError("peak", "encoder will not clamp overflow")
        value = round(sample * 32767)
        pcm.extend(struct.pack("<h", value))
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return stream.getvalue()
