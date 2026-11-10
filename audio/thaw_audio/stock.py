"""Offline stock authoring commands. Uses only Python 3.9 standard library."""
import argparse
from collections import Counter
import hashlib
import json

from .audit import run_controls
from .build import LANE, json_bytes, lane_path, write_bytes
from .stock_build import build_catalog, audit_catalog, compare_catalogs, preserve_originals, asset_controls
from .stock_media import create_samplers, create_spectra, prove_palettes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    build = commands.add_parser("build")
    build.add_argument("--output",default=str(LANE))
    build.add_argument("--seed",type=int,default=90517)
    audit = commands.add_parser("audit")
    audit.add_argument("--root",default=str(LANE))
    audit.add_argument("--compare")
    audit.add_argument("--report",default=str(LANE/"evidence/wave2/audit.json"))
    media = commands.add_parser("media")
    media.add_argument("--root",default=str(LANE))
    media.add_argument("--palette",action="append",default=[],help="Additional proof palette; default packs are also resolved")
    args = parser.parse_args(argv)
    if args.command == "build":
        index = build_catalog(args.output,args.seed)
        for row in index["assets"]:
            if row["provenance"] == "core_generated":
                print("GENERATED {file} frames={frames} sha256={sha256}".format(**row))
        print("STOCK_BUILD assets={} new={} wav_bytes={} catalog_sha256={}".format(
            len(index["assets"]),sum(r["provenance"] == "core_generated" for r in index["assets"]),
            sum(r["bytes"] for r in index["assets"]),hashlib.sha256(json_bytes(index)).hexdigest()))
    elif args.command == "audit":
        root = lane_path(args.root)
        report = audit_catalog(root)
        report["preservation"] = preserve_originals()
        report["controls"] = run_controls()
        per_asset = []
        index = json.loads((root/"catalog.json").read_text())
        for row in index["assets"]:
            if row["provenance"] == "core_generated":
                per_asset.extend(asset_controls(row,lane_path(root/row["file"]).read_bytes()))
        report["per_asset_controls"] = per_asset
        report["per_asset_control_rejections"] = len(per_asset)
        if args.compare:
            # Independently audit the second bundle as well as comparing exact bytes.
            audit_catalog(args.compare)
            report["determinism"] = compare_catalogs(root,args.compare)
        write_bytes(args.report,json_bytes(report))
        print("STOCK_AUDIT assets={asset_count} new={new_count} loops={loop_count} wav_bytes={wav_bytes} max_peak={max_peak:.8f} min_rms={min_rms:.8f} max_abs_dc={max_abs_dc:.12f}".format(**report))
        print("PRESERVATION "+json.dumps(report["preservation"],sort_keys=True))
        for control in report["controls"]:
            print("REJECT {}: {}".format(control["control"],control["reason"]))
        print("PER_ASSET_REJECT total={} by_code={}".format(len(per_asset),json.dumps(dict(Counter(c["actual"] for c in per_asset)),sort_keys=True)))
        for row in report["assets"]:
            if row["seam"] is not None:
                print("SEAM "+row["id"]+" "+json.dumps(row["seam"],sort_keys=True))
        print("CATALOG sha256="+report["catalog_sha256"])
        if "determinism" in report:
            d = report["determinism"]
            print("DETERMINISM identical_wavs={identical_wavs} regenerated={regenerated_wavs} frozen_byte_copies={frozen_byte_copies} catalog_identical={catalog_identical} hash_report_sha256={hash_report_sha256}".format(**d))
    else:
        root = lane_path(args.root)
        samplers = create_samplers(root,root/"samplers")
        spectra = create_spectra(root,root/"stock/spectra")
        index = json.loads((root/"catalog.json").read_text())
        paths = sorted((LANE/"packs").glob("*/audio.json"))+[lane_path(path) for path in args.palette]
        proof = prove_palettes(index,paths)
        write_bytes(root/"stock/palette-proof.json",json_bytes(proof))
        print("STOCK_MEDIA spectra_assets={} sheets={} samplers={} covered_unique_assets={}".format(
            len(spectra["assets"]),len(spectra["sheets"]),len(samplers["samplers"]),samplers["covered_unique_assets"]))
        for sampler in samplers["samplers"]:
            print("SAMPLER {file} duration={duration:.6f} bytes={bytes} sha256={sha256}".format(**sampler))
        print("WAV_SIZE catalog={} samplers={} combined={} combined_mib={:.6f}".format(
            samplers["catalog_wav_bytes"],samplers["sampler_wav_bytes"],samplers["combined_wav_bytes"],samplers["combined_wav_bytes"]/1024**2))
        print("PACK_PROOF packs={} rendered_presets={} core_changed_files={}".format(len(proof["packs"]),sum(len(p["presets"]) for p in proof["packs"]),proof["core_changed_files"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
