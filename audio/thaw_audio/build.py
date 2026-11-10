"""Build the full original Thaw kit, validating BEFORE each WAV is written."""

import argparse
import hashlib
import json
from pathlib import Path

from . import GENERATOR_VERSION, SAMPLE_RATE
from .catalog import catalog
from .synth import render
from .validate import validate_samples, validate_wav
from .wavio import encode

LANE = Path(__file__).resolve().parents[1]


def lane_path(value):
    path = Path(value).resolve()
    if path != LANE and LANE not in path.parents:
        raise ValueError("write/read root must stay inside lane-audio")
    return path


def write_bytes(target, data):
    target = lane_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def build_kit(output, seed=73021):
    output = lane_path(output)
    definitions = catalog(seed)
    assets = []
    for definition in definitions:
        params = definition["params"]
        samples = render(definition["synth"], params)
        tolerance = 0.51 / SAMPLE_RATE
        bounds = {"min_duration": params["duration"]-tolerance,
                  "max_duration": params["duration"]+tolerance}
        validate_samples(samples, loop=definition["loop"], **bounds)
        data = encode(samples)
        report = validate_wav(data, loop=definition["loop"], **bounds)
        filename = "wav/" + definition["id"] + ".wav"
        record = dict(definition, file=filename, **report)
        write_bytes(output / filename, data)
        assets.append(record)
    manifest = {"schema_version": 1, "kit": "thaw", "generator_version": GENERATOR_VERSION,
                "sample_rate": SAMPLE_RATE, "channels": 1, "sample_width": 2,
                "seed": seed, "assets": assets}
    write_bytes(output / "manifest.json", json_bytes(manifest))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=73021)
    parser.add_argument("--output", default=str(LANE))
    args = parser.parse_args()
    manifest = build_kit(args.output, args.seed)
    for record in manifest["assets"]:
        print("WROTE {} frames={} peak={:.6f} rms={:.6f} sha256={}".format(
            record["file"], record["frames"], record["peak"], record["rms"], record["sha256"]))
    encoded_manifest = json_bytes(manifest)
    print("BUILD assets={} wav_bytes={} manifest_sha256={}".format(
        len(manifest["assets"]), sum(r["bytes"] for r in manifest["assets"]),
        hashlib.sha256(encoded_manifest).hexdigest()))


if __name__ == "__main__":
    main()
