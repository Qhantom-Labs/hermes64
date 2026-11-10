"""Original deterministic sound design; no samples or borrowed melodies.

All RNGs are local. Loops use circular DSP, not silent endpoint fades.
Float synthesis is intentionally band-limited, then stored as 16-bit PCM.
"""

import math
import random

from . import SAMPLE_RATE as SR

TAU = 2.0 * math.pi
COMMON = {"seed": 73021, "duration": 1.0, "gain": 0.36,
          "lowpass_hz": 2800.0, "bits": 14, "rate_divisor": 1}
DEFAULTS = {
    "footstep": {"duration": 0.32, "surface": "snow", "weight": 1.0},
    "hatch": {"duration": 1.2, "weight": 1.0},
    "ui": {"duration": 0.12, "action": "move", "pitch": 620.0, "gain": 0.22},
    "dialogue": {"duration": 0.10, "pitch": 165.0, "brightness": 0.3,
                 "breath": 0.025, "formant": 800.0, "gain": 0.23},
    "cat": {"duration": 0.8, "mode": "meow", "pitch": 390.0,
            "roughness": 0.12, "gain": 0.30},
    "sphere": {"duration": 1.3, "collected": 1, "base_hz": 440.0, "gain": 0.30},
    "keycard": {"duration": 0.35, "pitch": 740.0, "gain": 0.22},
    "gust": {"duration": 2.8, "strength": 0.7, "gain": 0.29, "lowpass_hz": 1700.0},
    "hum": {"duration": 2.0, "pitch": 54.0, "gain": 0.19, "lowpass_hz": 850.0},
    "saucer": {"duration": 3.5, "pitch": 170.0, "gain": 0.29},
    "save": {"duration": 1.8, "pitch": 392.0, "gain": 0.30},
    "ambience": {"duration": 8.0, "scene": "habitat", "gain": 0.18,
                 "lowpass_hz": 800.0, "bits": 14},
    "music": {"duration": 24.0, "mood": "hub", "gain": 0.26,
              "lowpass_hz": 2600.0, "bits": 12, "rate_divisor": 2},
}
CHOICES = {"surface": ("snow", "floor"), "action": ("move", "select", "back"),
           "mode": ("meow", "purr", "chirp"), "scene": ("habitat", "outside", "storm"),
           "mood": ("hub", "explore")}
RANGES = {"gain": (0.02, 0.65), "lowpass_hz": (150.0, 4500.0),
          "pitch": (35.0, 1600.0), "base_hz": (220.0, 600.0),
          "brightness": (0.0, 0.9), "breath": (0.0, 0.2),
          "formant": (250.0, 1800.0), "roughness": (0.0, 0.5),
          "weight": (0.5, 1.5), "strength": (0.1, 1.0)}


def pickup_frequency(collected, base_hz=440.0):
    if type(collected) is not int or not 1 <= collected <= 8:
        raise ValueError("collected must be an integer 1..8")
    return base_hz * 2.0 ** ((collected - 1) / 6.0)


def resolve(kind, params):
    if kind not in DEFAULTS:
        raise ValueError("unknown synthesis kind: " + str(kind))
    resolved = dict(COMMON, **DEFAULTS[kind])
    for key, value in params.items():
        if key not in resolved:
            raise ValueError("unknown parameter: " + key)
        resolved[key] = value
    if type(resolved["seed"]) is not int or not 0 <= resolved["seed"] < 2**32:
        raise ValueError("seed must be an unsigned 32-bit integer")
    duration = resolved["duration"]
    bounds = (8.0, 40.0) if kind == "music" else ((2.0, 16.0) if kind == "ambience" else (0.05, 6.0))
    if (type(duration) not in (int, float) or not math.isfinite(duration)
            or not bounds[0] <= duration <= bounds[1]):
        raise ValueError("duration outside {} seconds".format(bounds))
    for key, values in CHOICES.items():
        if key in resolved and resolved[key] not in values:
            raise ValueError("invalid " + key)
    for key, bounds in RANGES.items():
        if key in resolved:
            value = resolved[key]
            if (type(value) not in (int, float) or not math.isfinite(value)
                    or not bounds[0] <= value <= bounds[1]):
                raise ValueError("{} outside {}".format(key, bounds))
    for key, bounds in (("bits", (10, 16)), ("rate_divisor", (1, 4))):
        if type(resolved[key]) is not int or not bounds[0] <= resolved[key] <= bounds[1]:
            raise ValueError("invalid " + key)
    if "collected" in resolved:
        pickup_frequency(resolved["collected"], resolved["base_hz"])
    return resolved


def lowpass(samples, cutoff, circular=False):
    alpha = 1.0 - math.exp(-TAU * cutoff / SR)
    beta = 1.0 - alpha
    previous = 0.0
    if circular:
        for value in samples:
            previous = alpha * value + beta * previous
        previous /= 1.0 - beta ** len(samples)
    output = []
    for value in samples:
        previous = alpha * value + beta * previous
        output.append(previous)
    return output


def delay(samples, taps, circular=False):
    count = len(samples)
    output = list(samples)
    for seconds, gain in taps:
        lag = round(seconds * SR)
        for i in range(count):
            if circular or i >= lag:
                output[i] += gain * samples[(i - lag) % count]
    return output


def fade_curve(i, count, fade_frames):
    edge = min(i, count - 1 - i, fade_frames) / fade_frames
    return 0.5 - 0.5 * math.cos(math.pi * edge)


def finish(samples, params, loop):
    count = len(samples)
    # Gentle prefilter before rate reduction limits aliasing; intentional 12-bit texture.
    samples = lowpass(samples, min(params["lowpass_hz"], SR / (2.5 * params["rate_divisor"])), loop)
    step = params["rate_divisor"]
    quantizer = float(2 ** (params["bits"] - 1) - 1)
    samples = [round(samples[(i // step) * step] * quantizer) / quantizer for i in range(count)]
    samples = lowpass(samples, params["lowpass_hz"], loop)
    if loop:
        mean = sum(samples) / count
        samples = [value - mean for value in samples]
    else:
        fades = [fade_curve(i, count, min(round(0.02 * SR), max(2, count // 8))) for i in range(count)]
        samples = [value * edge for value, edge in zip(samples, fades)]
        bias = sum(samples) / sum(fades)
        samples = [value - bias * edge for value, edge in zip(samples, fades)]
    peak = max(abs(value) for value in samples)
    if peak < 1e-10:
        raise ValueError("synthesizer produced silence")
    scale = params["gain"] / peak
    samples = [value * scale for value in samples]
    return quiet_splice(samples) if loop else samples


def quiet_splice(samples):
    """Rotate an already-periodic buffer <=20 ms to a low-slope splice.

    No sample is faded, removed, duplicated or altered. This is not a repair
    for non-periodic source material. The WAV validator checks the result.
    """
    count = len(samples)
    window = round(0.02 * SR)
    total_energy = sum(value*value for value in samples) / count
    for origin in range(window):
        before2, before, after, after2 = [samples[(origin+k) % count]
                                        for k in (-2, -1, 0, 1)]
        jump = after - before
        slope = max(abs(jump-(before-before2)), abs((after2-after)-jump))
        if abs(jump) > 0.0025 or slope > 0.0025:
            continue
        head = sum(samples[(origin+k) % count]**2 for k in range(window)) / window
        tail = sum(samples[(origin-k-1) % count]**2 for k in range(window)) / window
        if min(head, tail) >= total_energy * 0.45**2:
            return samples[origin:] + samples[:origin]
    raise ValueError("no low-slope, non-silent splice within 20 ms")


def strike(t, pitch, decay, phase=0.0):
    if t < 0:
        return 0.0
    envelope = (1.0 - math.exp(-t / 0.008)) * math.exp(-t / decay)
    return envelope * (math.sin(TAU * pitch * t + phase)
                       + 0.20 * math.sin(TAU * pitch * 2.01 * t)
                       + 0.055 * math.sin(TAU * pitch * 3.98 * t))


def one_shot(kind, p, rng, count):
    noise = lowpass([rng.uniform(-1.0, 1.0) for _ in range(count)], 2000.0)
    soft = lowpass(noise, 160.0)
    phase = rng.uniform(0.0, 0.3)
    drift = rng.uniform(0.992, 1.008)
    samples = []
    for i in range(count):
        t = i / SR
        x = i / max(1, count - 1)
        if kind == "footstep":
            snow = p["surface"] == "snow"
            decay = (0.075 if snow else 0.045) * p["weight"]
            env = (1 - math.exp(-t / 0.003)) * math.exp(-t / decay)
            crunch = 0.55 + 0.25 * math.sin(TAU * 39 * t) ** 2
            value = env * ((0.85 if snow else 0.16) * noise[i] * crunch
                           + 0.30 * math.sin(TAU * (90 / p["weight"]) * drift * t)
                           + (0.1 if snow else 0.25) * soft[i])
        elif kind == "hatch":
            whoosh = math.sin(math.pi * min(1.0, x / 0.78)) ** 2
            thunk = t - p["duration"] * 0.78
            value = 0.45 * noise[i] * whoosh + 0.08 * math.sin(TAU * (130*t - 20*t*t)) * whoosh
            if thunk >= 0:
                value += 0.6 * strike(thunk, 74 / p["weight"], 0.06, phase)
        elif kind == "ui":
            motion = {"move": 0.03, "select": 0.45, "back": -0.35}[p["action"]]
            phase += TAU * p["pitch"] * drift * (1 + motion * x) / SR
            value = math.sin(phase) * math.sin(math.pi * x) ** 1.5
            value += 0.06 * math.sin(phase * 2) * math.sin(math.pi * x) ** 2
        elif kind == "dialogue":
            phase += TAU * p["pitch"] * drift * (0.96 + 0.08 * math.sin(math.pi*x)) / SR
            value = math.sin(phase)
            for harmonic in range(2, 6):
                weight = p["brightness"] / harmonic * math.exp(-((harmonic*p["pitch"]-p["formant"]) / 750)**2)
                value += weight * math.sin(harmonic * phase)
            value = (value + p["breath"] * noise[i]) * math.sin(math.pi*x) ** 1.3
        elif kind == "cat":
            if p["mode"] == "purr":
                pulse = 0.5 + 0.5 * math.sin(TAU * (24.0 * drift) * t)
                phase += TAU * (p["pitch"] * 0.22) / SR
                value = (0.42 * math.sin(phase) + noise[i] * (0.4 + p["roughness"])) * pulse
                value *= 0.78 + 0.22 * math.sin(TAU * 1.4 * t)
            else:
                curve = (0.83 + 0.55 * math.sin(math.pi*x) - 0.26*x) if p["mode"] == "meow" else (0.85 + 0.62*x)
                phase += TAU * p["pitch"] * drift * curve * (1 + 0.014*math.sin(TAU*21*t)) / SR
                value = (math.sin(phase) + 0.22*math.sin(2*phase) + p["roughness"]*noise[i])
                value *= math.sin(math.pi*x) ** (0.8 if p["mode"] == "meow" else 1.7)
        elif kind == "sphere":
            value = strike(t, pickup_frequency(p["collected"], p["base_hz"]), 0.29, phase)
        elif kind == "keycard":
            value = 0.0
            for start, pitch in ((0.02, p["pitch"]), (0.15, p["pitch"]*1.25)):
                local = t - start
                if 0 < local < 0.085:
                    value += math.sin(TAU*pitch*drift*local) * math.sin(math.pi*local/0.085)**2
        elif kind == "gust":
            env = math.sin(math.pi*x) ** 1.4
            value = env * (soft[i] * 3.0 + noise[i] * (0.12 + p["strength"]*0.22))
            value += env * 0.025 * math.sin(TAU*(41*t + 4*math.sin(TAU*x)))
        elif kind == "hum":
            value = 0.45*math.sin(TAU*p["pitch"]*t+phase) + 0.1*math.sin(TAU*p["pitch"]*2*t)
            value = value * (0.92+0.08*math.sin(TAU*0.8*t)) + 0.08*soft[i]
        elif kind == "saucer":
            phase += TAU * p["pitch"] * (1.25-0.6*x) * drift / SR
            value = (math.sin(phase + 0.9*math.sin(phase*0.5)) + 0.12*noise[i]) * math.sin(math.pi*x)**1.3
        elif kind == "save":
            value = sum(strike(t-start, p["pitch"]*ratio, 0.35, phase) * 0.45
                        for start, ratio in ((0.0, 1.0), (0.17, 1.5), (0.37, 2.0)))
        samples.append(value)
    if kind in ("sphere", "save", "saucer"):
        samples = delay(samples, ((0.079, 0.18), (0.151, 0.10)))
    return samples


def ambience(p, rng, count):
    duration = count / SR
    air = lowpass([rng.uniform(-1, 1) for _ in range(count)], 700.0, True)
    rumble = lowpass(air, 70.0, True)
    air = lowpass(air, 700.0, True)
    phase = rng.uniform(0.0, TAU)
    samples = []
    for i in range(count):
        turn = i / count
        swell = 0.7 + 0.18*math.sin(TAU*turn+phase) + 0.10*math.sin(TAU*3*turn)
        if p["scene"] == "habitat":
            value = 0.28*math.cos(TAU*round(49*duration)*turn)
            value += 0.10*math.cos(TAU*round(98*duration)*turn+phase)
            value += (air[i]*0.15 + rumble[i]*0.5) * swell
        elif p["scene"] == "outside":
            value = (rumble[i]*2.4 + air[i]*0.24) * swell
            value += 0.024*math.cos(TAU*round(43*duration)*turn+phase)
        else:
            value = (rumble[i]*3.0 + air[i]*0.40) * swell
            value += 0.035*math.cos(TAU*round(37*duration)*turn+phase)
        samples.append(value)
    return samples


def midi(note):
    return 440.0 * 2.0 ** ((note-69)/12.0)


def music(p, rng, count):
    # Original seeded score: D-major pentatonic vs E-minor pentatonic.
    # 32 beats / 8 four-beat bars, 80 BPM at the supplied 24-second duration.
    duration = count / SR
    beat = duration / 32.0
    hub = p["mood"] == "hub"
    root = 50 if hub else 52
    scale = (0, 2, 4, 7, 9) if hub else (0, 3, 5, 7, 10)
    pad_chords = ((0, 7, 16), (9, 16, 24), (4, 11, 19), (7, 14, 21)) if hub else ((0, 7, 15), (5, 12, 19), (3, 10, 17), (0, 7, 17))
    samples = [0.0] * count
    for bar, chord in enumerate(pad_chords):
        center = bar * count / 4.0
        for note in chord:
            frequency = midi(root + note - 12)
            cycles = round(frequency * duration)
            phase = rng.uniform(-0.4, 0.4)
            for i in range(count):
                distance = abs(((i-center+count/2) % count)-count/2) / (count/4)
                if distance < 1:
                    envelope = 0.5+0.5*math.cos(math.pi*distance)
                    carrier = math.cos(TAU*cycles*i/count+phase)
                    carrier += 0.08*math.cos(TAU*cycles*2*i/count+phase)
                    samples[i] += 0.11*envelope*carrier
    # Sparse arpeggio: rests and octave choices derive only from the local seed.
    for step in range(16):
        if step % 4 == 3 or (step % 4 == 1 and rng.random() < 0.45):
            continue
        note = root + 12 + scale[(step*2 + rng.randrange(3)) % len(scale)]
        start = round((step*2 + 0.25)*beat*SR)
        frequency = midi(note)
        length = round(min(3.4, duration/4)*SR)
        for offset in range(length):
            local = offset / SR
            envelope = math.sin(math.pi * offset / length) ** 0.25
            samples[(start+offset) % count] += 0.13*strike(local, frequency, 0.65)*envelope
    # Glass punctuation, always within the selected pentatonic collection.
    for beat_index in (7, 23):
        frequency = midi(root+24+scale[rng.randrange(len(scale))])
        length = round(3.5*SR)
        start = round(beat_index*beat*SR)
        for offset in range(length):
            edge = math.sin(math.pi*offset/length)**0.3
            samples[(start+offset) % count] += 0.06*strike(offset/SR, frequency, 0.8)*edge
    # Finite circular feed-forward delay taps: tails cross the loop, no feedback reset.
    samples = delay(samples, ((0.137, 0.24), (0.293, 0.16), (0.479, 0.11), (0.733, 0.065)), True)
    return samples


def render(kind, params):
    p = resolve(kind, params)
    rng = random.Random(p["seed"])
    count = round(p["duration"] * SR)
    loop = kind in ("ambience", "music")
    if kind == "ambience":
        samples = ambience(p, rng, count)
    elif kind == "music":
        samples = music(p, rng, count)
    else:
        samples = one_shot(kind, p, rng, count)
    return finish(samples, p, loop)
