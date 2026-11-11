"""Additive catalog build/audit; never regenerate the approved originals."""
import argparse
import hashlib
import json
import struct

from . import SAMPLE_RATE as SR
from .build import LANE, json_bytes, lane_path, write_bytes
from .stock_catalog import definitions, frozen_records
from .stock_synth import render
from .validate import ValidationError, decode_wav, validate_samples, validate_wav, validate_determinism
from .wavio import encode

VERSION = "1.1.0"


def preserve_originals():
    baseline = json.loads((LANE/"evidence/wave2/baseline.json").read_text(encoding='utf-8'))
    for entry in baseline["assets"]+baseline["protected"]:
        path = lane_path(LANE/entry["file"])
        # Git records bytes, not filesystem timestamps. A fresh checkout must pass.
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValidationError("preservation", "frozen bytes changed: "+entry["file"])
    prefix = (LANE/"evidence/wave2/RESULT.md.wave1").read_bytes()
    if not (LANE/"RESULT.md").read_bytes().startswith(prefix):
        raise ValidationError("preservation", "historical RESULT prefix changed")
    return {"unchanged_wavs":len(baseline["assets"]), "hashes_unchanged":True,
            "protected_files":len(baseline["protected"]), "result_prefix_unchanged":True,
            "original_manifest_sha256":baseline["protected"][0]["sha256"]}


def build_catalog(output, seed=90517):
    output = lane_path(output)
    preserve_originals()
    assets = []
    for definition in definitions(seed):
        params = definition["params"]
        tolerance = .51/SR
        bounds = {"min_duration":params["duration"]-tolerance,"max_duration":params["duration"]+tolerance}
        samples = render(definition["generator"], params)
        validate_samples(samples,loop=definition["loop"],**bounds)
        data = encode(samples)
        metrics = validate_wav(data,loop=definition["loop"],**bounds)
        filename = "stock/wav/"+definition["id"]+".wav"
        write_bytes(output/filename,data)
        assets.append(dict(definition,file=filename,**metrics))
    for original in frozen_records():
        # Byte-copy into isolated comparison bundles, never rewrite originals at lane root.
        if output != LANE:
            write_bytes(output/original["file"],(LANE/original["file"]).read_bytes())
        assets.append(original)
    index = {"schema_version":"1.1","catalog":"hermes64.core","generator_version":VERSION,
             "seed":seed,"sample_rate":SR,"channels":1,"sample_width":2,
             "assets":sorted(assets,key=lambda r:r["id"])}
    write_bytes(output/"catalog.json",json_bytes(index))
    preserve_originals()
    return index


def audit_catalog(root):
    root = lane_path(root)
    raw = lane_path(root/"catalog.json").read_bytes()
    index = json.loads(raw)
    def reader(filename):
        path = lane_path(root/filename)
        if root not in path.parents:
            raise ValidationError("catalog", "file escapes package root")
        return path.read_bytes()
    report = audit_data(index,reader)
    report["catalog_sha256"] = hashlib.sha256(raw).hexdigest()
    return report


def audit_data(index, reader):
    for key,value in (("schema_version","1.1"),("catalog","hermes64.core"),("generator_version",VERSION),
                       ("sample_rate",SR),("channels",1),("sample_width",2)):
        if type(index.get(key)) is not type(value) or index.get(key) != value:
            raise ValidationError("catalog", "wrong "+key)
    try:
        expected = sorted(definitions(index["seed"])+frozen_records(),key=lambda r:r["id"])
    except (KeyError,ValueError) as error:
        raise ValidationError("catalog", "invalid seed") from error
    assets = index.get("assets",[])
    if not isinstance(assets,list) or [r.get("id") for r in assets] != [r["id"] for r in expected]:
        raise ValidationError("catalog", "missing, extra, duplicate or unordered IDs")
    checked = []
    for row, definition in zip(assets,expected):
        identity = definition["id"]
        if type(row.get("loop")) is not bool:
            raise ValidationError("catalog", "loop must be a strict boolean")
        for key,value in definition.items():
            if row.get(key) != value:
                raise ValidationError("catalog", identity+" inconsistent "+key)
        filename = definition.get("file","stock/wav/"+identity+".wav")
        if row.get("file") != filename:
            raise ValidationError("catalog", "unsafe/unexpected file path")
        duration = definition["params"]["duration"]
        metrics = validate_wav(reader(filename),loop=definition["loop"],min_duration=duration-.51/SR,max_duration=duration+.51/SR)
        for key,value in metrics.items():
            if row.get(key) != value:
                raise ValidationError("catalog", identity+" differs from WAV: "+key)
        checked.append(dict(id=identity,provenance=definition["provenance"],**metrics))
    return {"asset_count":len(checked),"new_count":sum(r["provenance"] == "core_generated" for r in checked),
            "loop_count":sum(r["seam"] is not None for r in checked),"wav_bytes":sum(r["bytes"] for r in checked),
            "max_peak":max(r["peak"] for r in checked),"min_rms":min(r["rms"] for r in checked),
            "max_abs_dc":max(abs(r["dc"]) for r in checked),"assets":checked}


def compare_catalogs(first, second):
    first,second = lane_path(first),lane_path(second)
    one,two = lane_path(first/"catalog.json").read_bytes(),lane_path(second/"catalog.json").read_bytes()
    if one != two:
        raise ValidationError("non_determinism","catalog bytes differ")
    index = json.loads(one)
    hashes = []
    for row in index["assets"]:
        prefix = "stock/wav/" if row["provenance"] == "core_generated" else "wav/"
        if "/" in row["id"] or "\\" in row["id"] or row["file"] != prefix+row["id"]+".wav":
            raise ValidationError("catalog","unsafe comparison path")
        a,b = lane_path(first/row["file"]).read_bytes(),lane_path(second/row["file"]).read_bytes()
        if a != b:
            raise ValidationError("non_determinism",row["id"]+" WAV bytes differ")
        hashes.append({"id":row["id"],"provenance":row["provenance"],
                       "sha256_first":hashlib.sha256(a).hexdigest(),"sha256_second":hashlib.sha256(b).hexdigest()})
    return {"identical_wavs":len(hashes),"regenerated_wavs":sum(r["provenance"] == "core_generated" for r in hashes),
            "frozen_byte_copies":sum(r["provenance"] == "wave1_frozen" for r in hashes),"catalog_identical":True,
            "catalog_sha256":hashlib.sha256(one).hexdigest(),"hash_report_sha256":hashlib.sha256(json_bytes(hashes)).hexdigest(),
            "assets":hashes}


def asset_controls(record, data):
    samples = decode_wav(data)
    peak = list(samples)
    peak[len(peak)//2] = .96
    seam = list(samples)
    seam[0],seam[1],seam[-2],seam[-1] = 0,0,0,.4
    wrong_rate = bytearray(data)
    struct.pack_into("<I",wrong_rate,24,32000)
    struct.pack_into("<I",wrong_rate,28,64000)
    calls = []
    def changing(seed):
        calls.append(seed)
        return data if len(calls) == 1 else data[:-2]+bytes((data[-2] ^ 1,data[-1]))
    probes = [
        ("peak",lambda:validate_wav(encode(peak))),
        ("silence",lambda:validate_wav(encode([0.0]*len(samples)))),
        ("dc_offset",lambda:validate_wav(encode([x+.025 for x in samples]))),
        ("loop_seam",lambda:validate_wav(encode(seam),loop=True)),
        ("duration",lambda:validate_wav(data,min_duration=len(samples)/SR+2/SR)),
        ("format",lambda:validate_wav(bytes(wrong_rate))),
        ("non_determinism",lambda:validate_determinism(changing,record["params"]["seed"])),
    ]
    result = []
    for expected,probe in probes:
        try:
            probe()
        except ValidationError as error:
            if error.code != expected:
                raise AssertionError("wrong rejection for "+record["id"]+": "+str(error)) from error
            result.append({"id":record["id"],"expected":expected,"actual":error.code,"rejected":True,"reason":str(error)})
        else:
            raise AssertionError("accepted bad "+expected+" input for "+record["id"])
    return result
