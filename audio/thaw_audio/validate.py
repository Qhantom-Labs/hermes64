"""Fail-closed numeric WAV checks; no claim of perceptual quality."""

import hashlib
import io
import math
import struct
import wave

from . import SAMPLE_RATE


class ValidationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__("{}: {}".format(code, message))


def rms(samples):
    return math.sqrt(sum(x * x for x in samples) / len(samples))


def seam_metrics(samples, sample_rate):
    jump = samples[0] - samples[-1]
    before = samples[-1] - samples[-2]
    after = samples[1] - samples[0]
    window = min(len(samples) // 4, round(0.02 * sample_rate))
    whole_rms = rms(samples)
    return {
        "jump": abs(jump),
        "slope_mismatch": max(abs(jump - before), abs(after - jump)),
        "head_rms_ratio": rms(samples[:window]) / max(whole_rms, 1e-12),
        "tail_rms_ratio": rms(samples[-window:]) / max(whole_rms, 1e-12),
        "window_frames": window,
        "jump_limit": 0.003,
        "slope_limit": 0.003,
        "energy_ratio_min": 0.35,
    }


def validate_samples(samples, sample_rate=SAMPLE_RATE, loop=False,
                     min_duration=0.02, max_duration=60.0):
    if sample_rate != SAMPLE_RATE:
        raise ValidationError("format", "sample rate must be 22050 Hz")
    duration = len(samples) / sample_rate
    if not min_duration <= duration <= max_duration or len(samples) < 4:
        raise ValidationError("duration", "{:.6f}s outside [{}, {}]".format(
            duration, min_duration, max_duration))
    if not all(math.isfinite(x) for x in samples):
        raise ValidationError("numeric", "non-finite sample")
    peak = max(abs(x) for x in samples)
    if peak > 0.90:
        raise ValidationError("peak", "{:.6f} exceeds 0.90 FS".format(peak))
    level = rms(samples)
    if level < 0.0005:
        raise ValidationError("silence", "RMS {:.8f} below 0.0005 FS".format(level))
    dc = sum(samples) / len(samples)
    if abs(dc) > 0.002:
        raise ValidationError("dc_offset", "mean {:.8f} exceeds +/-0.002 FS".format(dc))
    seam = seam_metrics(samples, sample_rate) if loop else None
    if seam is not None:
        if (seam["jump"] > 0.003 or seam["slope_mismatch"] > 0.003
                or seam["head_rms_ratio"] < 0.35 or seam["tail_rms_ratio"] < 0.35):
            raise ValidationError("loop_seam", str(seam))
    return {"duration": duration, "frames": len(samples), "peak": peak,
            "rms": level, "dc": dc, "seam": seam}


def decode_wav(data):
    try:
        if (len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE"
                or struct.unpack("<I", data[4:8])[0] + 8 != len(data)):
            raise ValidationError("format", "invalid/truncated RIFF container")
        with wave.open(io.BytesIO(data), "rb") as wav:
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                    or wav.getframerate() != SAMPLE_RATE or wav.getcomptype() != "NONE"):
                raise ValidationError("format", "expected mono 16-bit PCM at 22050 Hz")
            count = wav.getnframes()
            raw = wav.readframes(count)
        if len(raw) != count * 2:
            raise ValidationError("format", "truncated PCM payload")
        return [value[0] / 32768.0 for value in struct.iter_unpack("<h", raw)]
    except (wave.Error, EOFError, struct.error) as error:
        raise ValidationError("format", str(error)) from error


def validate_wav(data, loop=False, min_duration=0.02, max_duration=60.0):
    report = validate_samples(decode_wav(data), loop=loop,
                              min_duration=min_duration, max_duration=max_duration)
    report.update({"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return report


def validate_determinism(producer, seed):
    first = producer(seed)
    second = producer(seed)
    hashes = {"sha256_first": hashlib.sha256(first).hexdigest(),
              "sha256_second": hashlib.sha256(second).hexdigest()}
    if first != second:
        raise ValidationError("non_determinism", str(hashes))
    return hashes
