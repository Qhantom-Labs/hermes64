"""Review-only excerpts and sparse spectral diagnostics; no listening claims."""
import hashlib
import json

from . import SAMPLE_RATE as SR
from .build import LANE, json_bytes, lane_path, write_bytes
from .stock_build import audit_catalog
from .stock_catalog import CATEGORIES, resolve_palette
from .stock_synth import render
from .diagnostics import analysis, sheet
from .validate import decode_wav, validate_wav
from .wavio import encode

GROUPS = (
    ("01_footsteps_mechanisms", ("footsteps", "mechanisms")),
    ("02_ui_rewards_stingers", ("ui", "rewards", "stingers")),
    ("03_dialogue_creatures", ("dialogue", "creatures")),
    ("04_weather_machines", ("weather", "machines")),
    ("05_craft_combat_magic", ("craft", "combat", "magic")),
    ("06_music", ("music",)),
)


def create_samplers(root, output):
    root,output = lane_path(root),lane_path(output)
    audit_catalog(root)
    index = json.loads((root/"catalog.json").read_text(encoding='utf-8'))
    rows = [r for r in index["assets"] if r["provenance"] == "core_generated"]
    target_frames = round(40.5*SR)
    gap = round(.15*SR)
    samplers = []
    readme = ["# Wave-2 audition samplers", "", "**I cannot listen. New sounds are perceptually unverified. Start quietly.**", "",
              "Six category-grouped WAVs, 40.5 seconds each. All 170 new assets occur exactly once in the timecode index; short sounds may repeat inside their slot.",
              "All preview audio is attenuated to 0.8 times source amplitude. Excerpts receive 12 ms end/start ramps and at least 150 ms slot-end silence; no source WAV is changed.",
              "Long music/ambience excerpts are not a full-loop playback test. Grouped categories are contiguous and listed below. Original approved 38 files are not duplicated in this new-sounds sampler.", ""]
    for name,categories in GROUPS:
        selected = sorted((r for r in rows if r["category"] in categories),key=lambda r:(categories.index(r["category"]),r["id"]))
        mixed = [0.0]*target_frames
        entries = []
        for ordinal,row in enumerate(selected):
            start = round(ordinal*target_frames/len(selected))
            end = round((ordinal+1)*target_frames/len(selected))
            source = decode_wav(lane_path(root/row["file"]).read_bytes())
            playable = end-start-gap
            length = min(len(source),playable)
            excerpt = [x*.8 for x in source[:length]]
            fade = min(round(.012*SR),length//3)
            for i in range(fade):
                amount = i/max(1,fade-1)
                excerpt[i] *= amount
                excerpt[-1-i] *= amount
            repetitions = 0
            cursor = start
            while cursor+length <= end-gap:
                mixed[cursor:cursor+length] = excerpt
                repetitions += 1
                cursor += length+gap
            entries.append({"id":row["id"],"category":row["category"],"source_sha256":row["sha256"],
                            "start_frame":start,"end_frame":end,"start_seconds":start/SR,"end_seconds":end/SR,
                            "source_duration":len(source)/SR,"excerpt_seconds":length/SR,
                            "excerpted":length < len(source),"repetitions":repetitions})
        data = encode(mixed)
        metrics = validate_wav(data,min_duration=40,max_duration=60)
        filename = name+".wav"
        write_bytes(output/filename,data)
        samplers.append(dict(file=filename,categories=list(categories),entries=entries,**metrics))
        readme += ["## "+filename, "", " | Start s | End s | ID | Repeats | Excerpted |", " |---:|---:|---|---:|---|"]
        for entry in entries:
            readme.append(" | {start_seconds:.3f} | {end_seconds:.3f} | `{id}` | {repetitions} | {excerpted} |".format(**entry))
        readme.append("")
    catalog_bytes = sum(r["bytes"] for r in index["assets"])
    sampler_bytes = sum(r["bytes"] for r in samplers)
    if catalog_bytes+sampler_bytes >= 25*1024*1024:
        raise ValueError("catalog plus review sampler WAVs exceed 25 MiB")
    report = {"schema_version":"1.1","sample_rate":SR,"gain":.8,"source":"new stock entries only",
              "covered_unique_assets":sum(len(r["entries"]) for r in samplers),
              "catalog_wav_bytes":catalog_bytes,"sampler_wav_bytes":sampler_bytes,
              "combined_wav_bytes":catalog_bytes+sampler_bytes,"samplers":samplers}
    write_bytes(output/"index.json",json_bytes(report))
    write_bytes(output/"README.md",("\n".join(readme)+"\n").encode())
    return report


def create_spectra(root, output):
    root,output = lane_path(root),lane_path(output)
    audit_catalog(root)
    index = json.loads((root/"catalog.json").read_text(encoding='utf-8'))
    rows = [r for r in index["assets"] if r["provenance"] == "core_generated"]
    summaries, sheets = [], []
    flags = ["# Review priorities: suspected harshness, NOT heard", "",
             "I cannot listen. These flags are conservative inferences from synthesis design, not a harshness classifier or owner approval.",
             "All new sounds need the owner's audition. Start with low playback gain. Bright ringing, animal likeness, noise/transient texture and repeated blips are separate risks.",
             "The spectral fraction is sampled energy above 4 kHz, NOT perceived harshness. Low values do not clear any flag.", "",
             "| ID | Sampled >4 kHz fraction | Design-based flags |", "|---|---:|---|"]
    for category in CATEGORIES:
        selected = [r for r in rows if r["category"] == category]
        columns_by_id = {}
        for row in selected:
            samples = decode_wav(lane_path(root/row["file"]).read_bytes())
            columns,metrics = analysis(samples,row["loop"])
            columns_by_id[row["id"]] = columns
            summaries.append(dict(id=row["id"],sha256=row["sha256"],review_flags=row["review_flags"],**metrics))
            flags.append("| `{}` | {:.8f} | {} |".format(row["id"],metrics["sampled_spectral_energy_above_4khz_fraction"],"; ".join(row["review_flags"])))
        data,width,height = sheet(selected,columns_by_id,"HERMES64 - "+category.upper())
        filename = category+".png"
        write_bytes(output/filename,data)
        sheets.append({"file":filename,"width":width,"height":height,"bytes":len(data),
                       "sha256":hashlib.sha256(data).hexdigest(),"ids":[r["id"] for r in selected]})
    report = {"fft_size":512,"window":"Hann","columns_per_clip":96,"frequency_axis":"linear 0..11025 Hz bottom-to-top",
              "magnitude_range_dbfs":[-80,-8],"assets":summaries,"sheets":sheets,
              "limitations":"Sparse spectral windows, not continuous STFT, true peak, LUFS or listening acceptance."}
    write_bytes(output/"numeric.json",json_bytes(report))
    write_bytes(output/"REVIEW-FLAGS.md",("\n".join(flags)+"\n").encode())
    return report


def prove_palettes(index, palette_paths=None):
    before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((LANE/"thaw_audio").glob("*.py"))}
    reports = []
    paths = palette_paths if palette_paths is not None else sorted((LANE/"packs").glob("*/audio.json"))+[LANE/"evidence/wave2/third_pack.json"]
    for path in paths:
        path = lane_path(path)
        filename = path.relative_to(LANE).as_posix()
        raw = path.read_bytes()
        resolved = resolve_palette(path,index)
        presets = []
        for name,recipe in sorted(resolved["presets"].items()):
            data = encode(render(recipe["generator"],recipe["params"]))
            repeat = encode(render(recipe["generator"],recipe["params"]))
            if data != repeat:
                raise ValueError("non-deterministic palette recipe "+name)
            metrics = validate_wav(data,loop=recipe["params"]["loop"])
            presets.append(dict(name=name,recipe=recipe,repeat_sha256=hashlib.sha256(repeat).hexdigest(),**metrics))
        reports.append({"file":filename,"id":resolved["id"],"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
                        "bindings":len(resolved["bindings"]),"presets":presets})
    after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((LANE/"thaw_audio").glob("*.py"))}
    changed = sorted(name for name in dict(list(before.items())+list(after.items())) if before.get(name) != after.get(name))
    if changed:
        raise ValueError("pack rendering changed core source: "+str(changed))
    return {"packs":reports,"core_hashes_before":before,"core_hashes_after":after,"core_changed_files":changed,
            "claim":"New pack selection and preset rendering require only JSON data, zero core edits; no runtime adoption claimed."}
