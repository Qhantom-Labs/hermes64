"""Read-back audit, known-bad validator controls and byte determinism evidence."""

import argparse
import hashlib
import json
import math
import struct

from . import GENERATOR_VERSION, SAMPLE_RATE
from .build import LANE, json_bytes, lane_path, write_bytes
from .catalog import catalog
from .validate import (ValidationError, validate_samples, validate_wav,
                       validate_determinism)
from .wavio import encode


def audit_data(manifest, reader):
    required = {"schema_version": 1, "kit": "thaw", "generator_version": GENERATOR_VERSION,
                "sample_rate": SAMPLE_RATE, "channels": 1, "sample_width": 2}
    for key, value in required.items():
        if manifest.get(key) != value:
            raise ValidationError("manifest", "wrong " + key)
    try:
        expected = catalog(manifest["seed"])
    except (KeyError, ValueError) as error:
        raise ValidationError("manifest", "invalid seed") from error
    records = manifest.get("assets", [])
    if [record.get("id") for record in records] != [entry["id"] for entry in expected]:
        raise ValidationError("manifest", "missing, duplicate, unknown or unordered IDs")
    checked = []
    for record, definition in zip(records, expected):
        identity = definition["id"]
        for key in ("params", "loop", "kind", "synth", "review_flags"):
            if record.get(key) != definition[key]:
                raise ValidationError("manifest", identity + " inconsistent " + key)
        filename = "wav/" + identity + ".wav"
        if record.get("file") != filename:
            raise ValidationError("manifest", identity + " unsafe/unexpected file path")
        data = reader(filename)
        duration = definition["params"]["duration"]
        tolerance = 0.51 / SAMPLE_RATE
        actual = validate_wav(data, loop=definition["loop"], min_duration=duration-tolerance,
                              max_duration=duration+tolerance)
        for key, value in actual.items():
            if record.get(key) != value:
                raise ValidationError("manifest", identity + " differs from WAV: " + key)
        checked.append(dict(id=identity, **actual))
    return {"asset_count": len(checked), "loop_count": sum(r["seam"] is not None for r in checked),
            "wav_bytes": sum(r["bytes"] for r in checked), "assets": checked,
            "max_peak": max(r["peak"] for r in checked),
            "min_rms": min(r["rms"] for r in checked),
            "max_abs_dc": max(abs(r["dc"]) for r in checked)}


def audit_manifest(root):
    root = lane_path(root)
    manifest_data = lane_path(root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
    def reader(filename):
        target = lane_path(root / filename)
        if root not in target.parents:
            raise ValidationError("manifest", "asset resolves outside package")
        return target.read_bytes()
    report = audit_data(manifest, reader)
    report["manifest_sha256"] = hashlib.sha256(manifest_data).hexdigest()
    return report


def run_controls():
    tone = [0.08*math.sin(2*math.pi*55*i/SAMPLE_RATE) for i in range(8820)]
    jump = list(tone)
    jump[-1] = 0.21
    slope = list(tone)
    slope[0] = slope[-1] = 0
    slope[-2] = 0.1
    silent_edges = list(tone)
    for i in range(661):
        silent_edges[i] = silent_edges[-1-i] = 0
    wrong_rate = bytearray(encode(tone))
    struct.pack_into("<I", wrong_rate, 24, 32000)
    struct.pack_into("<I", wrong_rate, 28, 64000)
    calls = []
    def varying(seed):
        calls.append(seed)
        return b"A" if len(calls) == 1 else b"B"
    controls = [
        ("over-range float", "peak", lambda: validate_samples([x*15 for x in tone])),
        ("PCM full-scale peak", "peak", lambda: validate_wav(encode([x*12.49 for x in tone]))),
        ("zero buffer", "silence", lambda: validate_samples([0.0]*8820)),
        ("DC +0.025", "dc_offset", lambda: validate_samples([x+0.025 for x in tone])),
        ("last-sample discontinuity", "loop_seam", lambda: validate_samples(jump, loop=True)),
        ("slope discontinuity", "loop_seam", lambda: validate_samples(slope, loop=True)),
        ("silent loop boundary", "loop_seam", lambda: validate_samples(silent_edges, loop=True)),
        ("short duration", "duration", lambda: validate_samples(tone[:100])),
        ("long duration", "duration", lambda: validate_samples(tone, max_duration=0.3)),
        ("32000 Hz format", "format", lambda: validate_wav(bytes(wrong_rate))),
        ("truncated PCM", "format", lambda: validate_wav(encode(tone)[:-6])),
        ("changing same-seed producer", "non_determinism", lambda: validate_determinism(varying, 73)),
    ]
    results = []
    for label, expected, probe in controls:
        try:
            probe()
        except ValidationError as error:
            if error.code != expected:
                raise AssertionError("wrong rejection for {}: {}".format(label, error)) from error
            results.append({"control": label, "expected": expected, "actual": error.code,
                            "rejected": True, "reason": str(error)})
        else:
            raise AssertionError("KNOWN-BAD CONTROL ACCEPTED: " + label)
    return results


def compare_builds(first, second):
    first, second = lane_path(first), lane_path(second)
    one = lane_path(first / "manifest.json").read_bytes()
    two = lane_path(second / "manifest.json").read_bytes()
    if one != two:
        raise ValidationError("non_determinism", "manifest bytes differ")
    manifest = json.loads(one)
    hashes = []
    for record in manifest["assets"]:
        # Validate the exact path spelling before reading it.
        path = record["file"]
        if path != "wav/" + record["id"] + ".wav" or "/" in record["id"] or "\\" in record["id"]:
            raise ValidationError("manifest", "unsafe comparison path")
        a = lane_path(first / path).read_bytes()
        b = lane_path(second / path).read_bytes()
        if a != b:
            raise ValidationError("non_determinism", record["id"] + " WAV bytes differ")
        hashes.append({"id": record["id"], "sha256_first": hashlib.sha256(a).hexdigest(),
                       "sha256_second": hashlib.sha256(b).hexdigest()})
    aggregate = hashlib.sha256(json_bytes(hashes)).hexdigest()
    return {"identical_wavs": len(hashes), "manifest_identical": True,
            "manifest_sha256": hashlib.sha256(one).hexdigest(),
            "hash_report_sha256": aggregate, "assets": hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(LANE))
    parser.add_argument("--compare")
    parser.add_argument("--report", default=str(LANE / "evidence/audit.json"))
    args = parser.parse_args()
    report = audit_manifest(args.root)
    report["controls"] = run_controls()
    if args.compare:
        report["determinism"] = compare_builds(args.root, args.compare)
    write_bytes(args.report, json_bytes(report))
    print("AUDIT assets={} loops={} wav_bytes={} max_peak={:.8f} min_rms={:.8f} max_abs_dc={:.10f}".format(
        report["asset_count"], report["loop_count"], report["wav_bytes"], report["max_peak"],
        report["min_rms"], report["max_abs_dc"]))
    for control in report["controls"]:
        print("REJECT {}: {}".format(control["control"], control["reason"]))
    for record in report["assets"]:
        if record["seam"] is not None:
            print("SEAM {} {}".format(record["id"], json.dumps(record["seam"], sort_keys=True)))
    print("MANIFEST sha256=" + report["manifest_sha256"])
    if "determinism" in report:
        print("DETERMINISM identical_wavs={} manifest_identical={} hash_report_sha256={}".format(
            report["determinism"]["identical_wavs"], report["determinism"]["manifest_identical"],
            report["determinism"]["hash_report_sha256"]))
    print("REPORT " + str(lane_path(args.report)))


if __name__ == "__main__":
    main()
