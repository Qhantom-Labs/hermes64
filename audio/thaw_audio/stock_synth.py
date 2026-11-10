"""Hermes64 generic low-fi synthesis primitives, never selected by pack ID.

Original procedural models only. Shares the frozen, approved kit's gentle
filter/quantization/envelope finishing path without changing its source.
"""
import copy
import math
import random

from . import SAMPLE_RATE as SR
from .synth import TAU, delay, finish, lowpass, midi, strike

COMMON = {"seed": 90517, "duration": 0.5, "gain": 0.28, "lowpass_hz": 2600.0,
          "bits": 14, "rate_divisor": 1, "loop": False}
DEFAULTS = {
    "step": {"duration": 0.32, "pitch": 94.0, "grit": 0.5, "body": 0.35,
             "wet": 0.0, "ring": 0.1, "decay": 0.065, "texture_hz": 1500.0},
    "mechanism": {"duration": 0.75, "pitch": 110.0, "sweep": -0.2, "noise": 0.25,
                  "creak": 0.2, "latch": 0.65, "latch_at": 0.76, "rattles": 2},
    "sequence": {"duration": 0.6, "pitch": 440.0, "notes": [0, 7, 12],
                 "decay": 0.16, "shine": 0.18, "body": 0.15, "spread": 0.5},
    "tool": {"duration": 0.8, "pitch": 140.0, "mode": "hammer", "rate": 4.0,
             "noise": 0.25, "ring": 0.12, "decay": 0.045},
    "voice": {"duration": 0.12, "pitch": 180.0, "brightness": 0.3, "breath": 0.025,
              "formant": 850.0, "vibrato": 0.015, "flutter": 7.0, "robot": 0.0,
              "glide": 0.04, "pulse": 0.08, "gain": 0.22},
    "creature": {"duration": 0.65, "pitch": 360.0, "contour": [0.75, 1.25, 0.8],
                 "brightness": 0.3, "noise": 0.08, "flutter": 9.0, "pulse": 0.15,
                 "formant": 900.0, "bouts": 1, "gain": 0.28},
    "environment": {"duration": 4.0, "loop": True, "gain": 0.17, "lowpass_hz": 1600.0,
                    "noise": 0.65, "rumble": 0.5, "texture_hz": 900.0, "pitch": 48.0,
                    "tone": 0.05, "swells": 1, "density": 5.0, "event": "drop",
                    "event_mix": 0.16, "event_pitch": 600.0, "echo": 0.08},
    "machine": {"duration": 1.2, "pitch": 90.0, "mode": "motor", "noise": 0.12,
                "pulse": 0.2, "rate": 7.0, "sweep": -0.2, "ring": 0.15, "gain": 0.25},
    "impact": {"duration": 0.45, "pitch": 95.0, "mode": "strike", "noise": 0.45,
               "body": 0.6, "ring": 0.08, "decay": 0.075, "sweep": -0.6, "gain": 0.33},
    "magic": {"duration": 1.3, "pitch": 390.0, "mode": "shimmer", "noise": 0.05,
              "shine": 0.2, "sweep": 0.6, "rate": 7.0, "gain": 0.27},
    "score": {"duration": 12.0, "loop": True, "gain": 0.25, "bits": 12, "rate_divisor": 2,
              "lowpass_hz": 2500.0, "root": 50, "beats": 16,
              "scale": [0, 2, 4, 7, 9], "chords": [[0, 7, 16], [9, 16, 24], [4, 11, 19], [7, 14, 21]],
              "motif": [0, 2, -1, 4, 1, -1, 3, 2, 0, -1, 1, 4, 3, -1, 2, 0],
              "pad": 0.55, "bell": 0.5, "wood": 0.2, "reed": 0.1,
              "decay": 0.6, "echo": 0.22, "rest_chance": 0.12},
}
DURATIONS = {"step": (0.14, 0.65), "mechanism": (0.18, 1.5), "sequence": (0.07, 2.5),
             "tool": (0.12, 2.0), "voice": (0.07, 0.22), "creature": (0.18, 1.8),
             "environment": (0.35, 8.0), "machine": (0.15, 4.0), "impact": (0.12, 1.8),
             "magic": (0.4, 2.6), "score": (8.0, 24.0)}
RANGES = {"gain": (0.035, 0.5), "lowpass_hz": (300, 4000), "pitch": (30, 1800),
          "texture_hz": (100, 4000), "event_pitch": (70, 1600), "formant": (200, 2000),
          "decay": (0.015, 1.2), "sweep": (-0.9, 1.5), "glide": (-0.5, 0.5),
          "vibrato": (0, 0.12), "flutter": (0.2, 50), "rate": (0.5, 45), "density": (0, 35),
          "latch_at": (0.05, 0.9), "spread": (0, 0.75)}
UNIT_FIELDS = ("grit", "body", "wet", "ring", "noise", "creak", "latch", "shine", "brightness", "breath",
               "robot", "pulse", "rumble", "tone", "event_mix", "echo", "pad", "bell", "wood", "reed", "rest_chance")
MODES = {"tool": ("hammer", "saw", "weld", "assemble"),
         "machine": ("motor", "servo", "beep", "typing", "steam", "teleport"),
         "impact": ("strike", "swing", "hurt", "blast", "projectile", "shield"),
         "magic": ("chime", "shimmer", "charge", "portal")}


def number(value, low, high, name):
    if type(value) not in (float, int) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("{} must be a finite number in [{}, {}]".format(name, low, high))


def integer_list(values, low, high, maximum, name):
    if not isinstance(values, list) or not 1 <= len(values) <= maximum:
        raise ValueError("invalid " + name)
    if any(type(v) is not int or not low <= v <= high for v in values):
        raise ValueError("invalid " + name + " values")


def resolve(generator, params):
    if generator not in DEFAULTS or not isinstance(params, dict):
        raise ValueError("unknown generator or invalid parameter object")
    p = copy.deepcopy(dict(COMMON, **DEFAULTS[generator]))
    for key, value in params.items():
        if key not in p:
            raise ValueError("unknown parameter: " + str(key))
        p[key] = copy.deepcopy(value)
    if type(p["seed"]) is not int or not 0 <= p["seed"] < 2**32:
        raise ValueError("seed must be uint32")
    number(p["duration"], *DURATIONS[generator], "duration")
    if type(p["loop"]) is not bool or (p["loop"] and generator not in ("environment", "machine", "score")):
        raise ValueError("invalid loop mode")
    if generator == "score" and not p["loop"]:
        raise ValueError("score requires circular loop mode")
    for key, bounds in RANGES.items():
        if key in p:
            number(p[key], *bounds, key)
    for key in UNIT_FIELDS:
        if key in p:
            number(p[key], 0, 1, key)
    for key, low, high in (("bits", 10, 16), ("rate_divisor", 1, 4), ("rattles", 0, 12),
                           ("bouts", 1, 6), ("swells", 1, 6), ("root", 36, 64), ("beats", 8, 32)):
        if key in p and (type(p[key]) is not int or not low <= p[key] <= high):
            raise ValueError("invalid " + key)
    if generator in MODES and p["mode"] not in MODES[generator]:
        raise ValueError("invalid mode")
    if generator == "environment" and p["event"] not in ("drop", "crackle", "chirp", "rustle"):
        raise ValueError("invalid event")
    if "notes" in p:
        integer_list(p["notes"], -24, 24, 8, "notes")
    if "contour" in p:
        if not isinstance(p["contour"], list) or len(p["contour"]) != 3:
            raise ValueError("contour needs three values")
        for value in p["contour"]:
            number(value, 0.3, 2.0, "contour")
    if generator == "score":
        integer_list(p["scale"], 0, 12, 8, "scale")
        integer_list(p["motif"], -1, len(p["scale"])-1, 32, "motif")
        if not isinstance(p["chords"], list) or not 2 <= len(p["chords"]) <= 8:
            raise ValueError("invalid chords")
        for chord in p["chords"]:
            integer_list(chord, -12, 24, 4, "chord")
    return p


def smooth_noise(rng, count, cutoff, loop=False):
    return lowpass([rng.uniform(-1, 1) for _ in range(count)], cutoff, loop)


def transient(t, pitch, decay, noise, ring=0.1):
    if t < 0:
        return 0.0
    envelope = (1-math.exp(-t/0.003))*math.exp(-t/decay)
    return envelope*(math.sin(TAU*pitch*t)+ring*math.sin(TAU*pitch*2.73*t)+noise)


def one_shot(g, p, rng, count):
    noise = smooth_noise(rng, count, p.get("texture_hz", 1900.0))
    soft = lowpass(noise, 180.0)
    phase = rng.uniform(0, 0.6)
    jitter = rng.uniform(0.985, 1.015)
    output = []
    texture = [rng.uniform(0.65, 1.15) for _ in range(16)]
    for i in range(count):
        t, x = i/SR, i/max(1, count-1)
        pitch = p.get("pitch", 100)*jitter
        if g == "step":
            env = (1-math.exp(-t/0.004))*math.exp(-t/p["decay"])
            grains = 0.55+0.45*math.sin(TAU*(28*t+0.4*x))**2
            value = env*(p["grit"]*noise[i]*grains + p["body"]*math.sin(TAU*pitch*t))
            value += env*p["ring"]*0.3*math.sin(TAU*pitch*3.71*t)
            value += p["wet"]*env*(soft[i]*2+0.2*math.sin(TAU*(190*t-80*t*t)))
        elif g == "mechanism":
            env = math.sin(math.pi*x)**1.4
            phase += TAU*pitch*(1+p["sweep"]*x)/SR
            friction = (math.sin(phase+0.4*math.sin(phase*0.47)) + 0.12*math.sin(phase*3))
            value = env*(p["noise"]*noise[i]+p["creak"]*friction*0.25)
            value += p["latch"]*transient(t-p["duration"]*p["latch_at"], pitch*0.68, 0.05, noise[i]*0.15)
            for j in range(p["rattles"]):
                local = t-p["duration"]*(0.12+0.5*j/max(1, p["rattles"]))
                if 0 <= local < 0.1:
                    value += 0.12*transient(local, pitch*2.8, 0.018, noise[i], 0.3)
        elif g == "sequence":
            value = 0.0
            for j, note in enumerate(p["notes"]):
                local = t-j*p["duration"]*p["spread"]/max(1, len(p["notes"])-1)
                if local >= 0:
                    f = pitch*2**(note/12)
                    env = (1-math.exp(-local/0.009))*math.exp(-local/p["decay"])
                    value += env*(math.sin(TAU*f*local+phase)+p["shine"]*math.sin(TAU*f*2.01*local))
                    value += env*p["body"]*0.2*math.sin(TAU*f*0.5*local)
        elif g == "tool":
            if p["mode"] in ("hammer", "assemble"):
                local = (t+0.03) % (1/p["rate"])
                note = texture[min(15, int(t*p["rate"]))]
                value = transient(local, pitch*note, p["decay"], noise[i]*p["noise"], p["ring"])
            elif p["mode"] == "saw":
                teeth = (0.55+0.45*math.sin(TAU*p["rate"]*t))
                value = teeth*(noise[i]*p["noise"]+0.12*math.sin(TAU*pitch*t))
                value *= math.sin(math.pi*x)**0.6
            else:
                value = (0.65+0.35*math.sin(TAU*p["rate"]*t)**2)*(noise[i]*p["noise"]+0.15*math.sin(TAU*pitch*t+math.sin(TAU*42*t)))
                value *= math.sin(math.pi*x)**0.8
        elif g == "voice":
            f = pitch*(1+p["glide"]*(2*x-1)+p["vibrato"]*math.sin(TAU*p["flutter"]*t))
            phase += TAU*f/SR
            value = math.sin(phase)
            for h in range(2, 7):
                weight = p["brightness"]/h*math.exp(-((h*f-p["formant"])/600)**2)
                value += weight*math.sin(phase*h)
            value *= 1-p["robot"]*0.5+p["robot"]*0.5*math.cos(phase*0.5)
            value = (value+noise[i]*p["breath"])*(1-p["pulse"]+p["pulse"]*math.sin(TAU*p["flutter"]*t)**2)
            value *= math.sin(math.pi*x)**1.3
        elif g == "creature":
            a,b,c = p["contour"]
            shape = a+(b-a)*x*2 if x < 0.5 else b+(c-b)*(x-0.5)*2
            phase += TAU*pitch*shape*(1+0.016*math.sin(TAU*p["flutter"]*t))/SR
            value = math.sin(phase)
            for h in (2, 3, 4):
                value += p["brightness"]/h*math.exp(-((h*pitch-p["formant"])/700)**2)*math.sin(phase*h)
            value = value*(1-p["pulse"]+p["pulse"]*math.sin(TAU*p["flutter"]*t)**2)+noise[i]*p["noise"]
            value *= abs(math.sin(math.pi*p["bouts"]*x))**1.3
        elif g == "impact":
            phase += TAU*pitch*(1+p["sweep"]*x)/SR
            if p["mode"] in ("swing", "projectile"):
                env = math.sin(math.pi*x)**1.8
            elif p["mode"] == "hurt":
                env = math.sin(math.pi*x)**1.1
            else:
                env = (1-math.exp(-t/0.004))*math.exp(-t/p["decay"])
            value = env*(p["body"]*math.sin(phase)+p["noise"]*(noise[i] if p["mode"] != "blast" else soft[i]*3))
            value += env*p["ring"]*math.sin(phase*2.91)
        else:  # generic magic/sci-fi gesture, not a theme or game-mechanics branch
            phase += TAU*pitch*(1+p["sweep"]*x)/SR
            if p["mode"] == "charge":
                env = math.sin(math.pi*x/2)**2
            elif p["mode"] == "chime":
                env = (1-math.exp(-t/0.008))*math.exp(-t/0.3)
            else:
                env = math.sin(math.pi*x)**0.8
            value = env*(math.sin(phase)+p["shine"]*math.sin(phase*2.01)+p["noise"]*noise[i])
            value *= 0.75+0.25*math.sin(TAU*p["rate"]*t)**2
            if p["mode"] == "portal":
                value += env*0.25*math.sin(phase*0.5+0.5*math.sin(TAU*3*t))
        output.append(value)
    if g in ("sequence", "magic"):
        output = delay(output, ((0.073, 0.16), (0.151, 0.08)))
    return output


def environment(p, rng, count):
    air = smooth_noise(rng, count, p["texture_hz"], p["loop"])
    rumble = lowpass(air, 95.0, p["loop"])
    air = lowpass(air, p["texture_hz"], p["loop"])
    duration = count/SR
    phase = rng.uniform(0, TAU)
    cycles = round(p["pitch"]*duration)
    output = []
    for i in range(count):
        turn = i/count
        swell = 0.78+0.22*math.cos(TAU*p["swells"]*turn)
        value = (p["noise"]*air[i]+p["rumble"]*rumble[i]*2)*swell
        value += p["tone"]*math.cos(TAU*cycles*turn+phase)
        output.append(value)
    for event in range(round(p["density"]*duration)):
        start = rng.randrange(count)
        pitch = p["event_pitch"]*rng.uniform(0.75, 1.3)
        length = round(SR*rng.uniform(0.018, 0.14))
        amplitude = p["event_mix"]*rng.uniform(0.4, 1.0)
        for offset in range(length):
            index = start+offset
            if not p["loop"] and index >= count:
                break
            t = offset/SR
            env = math.sin(math.pi*offset/length)**1.5
            if p["event"] == "drop":
                signal = math.sin(TAU*(pitch*t-90*t*t))*math.exp(-t/0.025)
            elif p["event"] == "chirp":
                signal = math.sin(TAU*pitch*(t+2*t*t))*0.45
            elif p["event"] == "rustle":
                signal = air[index % count]*2
            else:
                signal = rng.uniform(-1, 1)*math.exp(-t/0.012)
            output[index % count] += amplitude*env*signal
    if p["echo"]:
        output = delay(output, ((0.113, p["echo"]), (0.251, p["echo"]*0.5)), p["loop"])
    if not p["loop"]:
        output = [value*math.sin(math.pi*i/(count-1))**0.7 for i,value in enumerate(output)]
    return output


def machine(p, rng, count):
    duration = count/SR
    air = smooth_noise(rng, count, 900.0, p["loop"])
    pitch = round(p["pitch"]*duration)/duration if p["loop"] else p["pitch"]*rng.uniform(0.99, 1.01)
    rate = round(p["rate"]*duration)/duration if p["loop"] else p["rate"]
    phase = rng.uniform(0, TAU)
    accents = [rng.uniform(0.65, 1.1) for _ in range(math.ceil(duration*p["rate"])+2)]
    output = []
    for i in range(count):
        t, x = i/SR, i/max(1, count-1)
        angle = TAU*pitch*t+phase
        if p["mode"] == "motor":
            value = (math.sin(angle)+p["ring"]*math.sin(angle*2))*(1-p["pulse"]*0.5+p["pulse"]*0.5*math.cos(TAU*rate*t))
            value += p["noise"]*air[i]
        elif p["mode"] == "typing":
            local = t % (1/p["rate"])
            amplitude = accents[min(len(accents)-1, int(t*p["rate"]))]
            value = amplitude*transient(local, pitch*1.4, 0.014, air[i]*p["noise"], p["ring"])
        elif p["mode"] == "beep":
            gate = max(0, math.sin(TAU*rate*t))**4
            value = gate*(math.sin(angle)+p["ring"]*math.sin(2*angle))
        elif p["mode"] == "steam":
            value = air[i]*(0.6+0.4*math.sin(math.pi*x)**2)+0.05*math.sin(angle)
        else:
            sweep = 0 if p["loop"] else p["sweep"]
            angle = TAU*pitch*(t+0.5*sweep*t*t/duration)+phase
            value = (math.sin(angle+0.3*math.sin(TAU*rate*t))+p["noise"]*air[i])
            value *= 0.7+0.3*math.sin(math.pi*x)**2 if not p["loop"] else 1
            if p["mode"] == "teleport":
                value += 0.4*strike(t-duration*0.7, pitch*3, 0.2)
        output.append(value)
    return output


def score(p, rng, count):
    duration = count/SR
    output = [0.0]*count
    chord_span = count/len(p["chords"])
    for chord_number, chord in enumerate(p["chords"]):
        for note in chord:
            cycles = round(midi(p["root"]+note-12)*duration)
            phase = rng.uniform(-0.35, 0.35)
            for i in range(count):
                distance = abs(((i-chord_number*chord_span+count/2) % count)-count/2)/chord_span
                if distance < 1:
                    envelope = 0.5+0.5*math.cos(math.pi*distance)
                    angle = TAU*cycles*i/count+phase
                    output[i] += p["pad"]*0.17*envelope*(math.cos(angle)+p["reed"]*0.12*math.cos(3*angle))
    for event, degree in enumerate(p["motif"]):
        if degree < 0 or (event % 4 == 3 and rng.random() < p["rest_chance"]):
            continue
        note = p["root"]+12+p["scale"][degree]
        pitch = midi(note)
        start = round((event+0.18)*count/len(p["motif"]))
        length = round(min(2.4, duration/4)*SR)
        amplitude = rng.uniform(0.83, 1.05)
        for offset in range(length):
            t = offset/SR
            env = math.sin(math.pi*offset/length)**0.35
            bell = p["bell"]*strike(t, pitch, p["decay"])
            wood = p["wood"]*(1-math.exp(-t/0.004))*math.exp(-t/0.12)*(math.sin(TAU*pitch*t)+0.1*math.sin(TAU*pitch*3*t))
            reed = p["reed"]*math.sin(TAU*pitch*t)*math.sin(math.pi*offset/length)**2*math.exp(-t/0.7)
            output[(start+offset) % count] += 0.20*amplitude*env*(bell+wood+reed)
    # Sparse soft pulse accents; beat count changes their density independently of melody.
    for beat in range(0, p["beats"], 4):
        start = round((beat+0.5)*count/p["beats"])
        for offset in range(round(0.16*SR)):
            output[(start+offset) % count] += p["wood"]*0.025*transient(offset/SR, midi(p["root"]-12), 0.04, 0)
    return delay(output, ((0.137, p["echo"]), (0.293, p["echo"]*0.65),
                          (0.479, p["echo"]*0.4), (0.733, p["echo"]*0.2)), True)


def render(generator, params):
    p = resolve(generator, params)
    rng = random.Random(p["seed"])
    count = round(p["duration"]*SR)
    if generator == "environment":
        raw = environment(p, rng, count)
    elif generator == "machine":
        raw = machine(p, rng, count)
    elif generator == "score":
        raw = score(p, rng, count)
    else:
        raw = one_shot(generator, p, rng, count)
    return finish(raw, p, p["loop"])
