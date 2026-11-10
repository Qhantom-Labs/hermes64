# Hermes64 audio contract v1.1

## Additive stock catalog interface — wave 2

**INTERFACE READY / FROZEN; 208 assets AVAILABLE and numerically verified.** The v1 Thaw manifest and 38 WAV files remain byte-for-byte preserved, with unchanged mtimes. Dylan reports listening to and loving those originals; the 170 new sounds have no listening approval. Core synthesis is theme-agnostic; packs select sound IDs and parameter presets as JSON data. This contract does not install a plugin/runtime adapter.

Verified delivery: `../evidence/wave2/stage20-verify.log` (69 tests and full build/audit/media/query sequence). `../catalog.json` SHA-256: `81ab8380d25e1d5e3dd45a027a551ed18fd20ec4c76a546a98341b7ca3f53f80`. Catalog WAVs: 14,095,138 bytes; six 40.5-second review samplers: 10,716,564 bytes; combined: 23.662283 MiB. All 28 catalog loops pass the unchanged PCM seam gates. New-asset sweep: 220 cases across 11 families; 1,190 per-asset known-bad controls reject correctly.

### Catalog v1.1

`catalog.json` at lane root: `schema_version: "1.1"`, `catalog: "hermes64.core"`, `generator_version`, `seed` (uint32), `sample_rate: 22050`, `channels: 1`, `sample_width: 2`, `assets` array sorted by ID. Target 150–250 total records including the 38 frozen originals, no duplicate IDs/files.

Each record includes `id`, `tags` (lowercase string array), `category`, `generator`, fully resolved `params`, relative `file`, actual `duration`, `frames`, `bytes`, `peak`, `rms`, `dc`, whole-WAV `sha256`, `loop` (strict boolean), `seam` (loop metrics or null), `review_flags`, `provenance` (`wave1_frozen` or `core_generated`). Music additionally carries an explicit original-composition note.

- Original records keep their existing ID/path/params/hash; new IDs start `core.` and live at `stock/wav/<id>.wav`.
- The catalog has no theme-selected default. Resolve IDs to files relative to its directory. A distributable bundle includes both `wav/` and `stock/wav/`, not evidence/rebuild copies.
- Categories: `footsteps`, `mechanisms`, `ui`, `rewards`, `craft`, `dialogue`, `creatures`, `weather`, `machines`, `combat`, `magic`, `stingers`, `music`.
- Combat audio is optional stock content only. This lane does not enable health/combat mechanics or start the held combat runtime module.
- Same PCM format and numeric gates as v1. A new sound must not silently overwrite an approved one.

### Query interface

```sh
python3 -B -m thaw_audio.catalog list
python3 -B -m thaw_audio.catalog search wood --category footsteps
python3 -B -m thaw_audio.catalog list --tag soft --limit 5
```

`list`/`search` return JSON with `total` (entire index count), `matched` (all matching records), `returned`, `has_more`, and `assets`. Search terms are case-insensitive AND matches against ID/category/tags; repeated `--tag` filters are exact AND matches; `--category` is exact. `--limit` limits rows, never the matched count. Unknown commands/invalid arguments fail; there is no generated fallback or network request. `--catalog` can select another index within this lane. Python API: `thaw_audio.stock_catalog.query(index, terms=(), category=None, tags=(), limit=None)`.

### Pack palette as data

Files: `packs/<pack_id>/audio.json`. Required shape:

```json
{
  "schema_version": "1.1",
  "id": "example_pack",
  "bindings": {
    "walk": {"ids": ["core.footstep.wood.01"], "gain": 0.65},
    "room_music": {"ids": ["core.music.forest_day"], "gain": 0.35}
  },
  "presets": {
    "soft_walk": {"asset": "core.footstep.wood.01", "params": {"seed": 37, "gain": 0.22}}
  }
}
```

Bindings refer to supplied WAVs; their `gain` is runtime mix gain (0–1). Presets are **compile-time generator inputs**, not a promise that runtime audio changes automatically. `resolve_palette(path, index)` resolves base params + overrides, rejects unknown IDs/parameters/ranges, and returns the complete recipe. Presets may target new `core_generated` assets only; frozen originals can be selected but never regenerated/overridden by a palette. A new pack needs only this JSON file; no pack-ID branch is allowed in core code. `../stock/palette-proof.json` proves the two requested packs plus a 390-byte third palette: seven presets actually rendered twice, with identical hashes and zero core-file changes.

### Review deliverables

`samplers/`: category-ordered concatenated WAVs, each 40–60 seconds, with `index.json`/README timecodes and source IDs. Long loops may be excerpted and short blips repeated; these transformations are labeled and do not modify source assets. `stock/spectra/` provides sheets/numeric summaries for all new sounds; review flags stay until Dylan listens. Size reports distinguish canonical catalog WAVs, review sampler WAVs, and non-shipping rebuild evidence.

Implemented commands (from lane root):

```sh
sh verify_stock.sh
python3 -B -m thaw_audio.stock build --seed 90517
python3 -B -m thaw_audio.stock audit --compare evidence/wave2/repeat --report evidence/wave2/final-audit.json
python3 -B -m thaw_audio.stock media --palette evidence/wave2/third_pack.json
```

New Python synthesis API: `thaw_audio.stock_synth.resolve(generator, params)` / `render(generator, params)`; definitions from `thaw_audio.stock_catalog.definitions(seed=90517)`. `thaw_audio.wavio.encode` and `validate.validate_wav` remain the unchanged shared PCM path. Every recipe must pass output validation; parameter bounds alone are not an acoustic guarantee. Catalog `generator_version` is `1.1.0`; frozen original generator remains `1.0.0`.

The original v1 interface follows for backward compatibility. **Its build commands are historical: do not run `verify.sh`, old `thaw_audio.build` at lane root, or old `evidence.collect_receipts` during wave 2.** They rewrite protected originals or earlier reports. `README.md` is the current usage guide; `RESULT.md` appends final wave-2 receipts without changing its original prefix.

---

# Thaw audio contract v1 (preserved interface)

**Status: INTERFACE READY / FROZEN; 38 assets generated and numerically verified.**
Owner: Lane AUDIO (Astra), bounded commission; Hermes Main owns integration. This file and `../CHECKPOINT.md` are the runtime/plugin handoff. Only this lane writes here. No integration, public release or perceptual acceptance is implied.

Current evidence: `../evidence/stage21-verify.log` (46 tests pass and complete rebuild/read-back audit). `../manifest.json` SHA-256: `190fa66d607d4ef3faa75d040629d5eb8000858450a172eed605753fd57c2886`. All IDs below are available. `../RESULT.md` is the final receipt; `../README.md` documents synthesis controls and limitations.

## Packaging

- `manifest.json`: object with `schema_version: 1`, `kit: "thaw"`, `generator_version`, `sample_rate: 22050`, `channels: 1`, `sample_width: 2`, `seed`, `assets` array.
- Each asset: `id` (unique string), `kind` (`sfx`, `ambience`, `music`), `params` (complete resolved synthesis inputs including `seed` and `duration`), `file` (relative POSIX path `wav/<id>.wav`), `duration` (seconds), `peak`, `rms`, `dc` (normalized full-scale amplitude), `sha256` (whole WAV bytes), `loop` (boolean), `frames`, `bytes`, `seam` (numeric report for loops, otherwise null), `review_flags` (string array).
- Mono signed little-endian 16-bit PCM WAV, exactly 22,050 Hz. Peak limit 0.90 full scale. Not stereo/spatialized, not LUFS/mastered.
- Choice: 22,050 Hz keeps artifacts compact and provides an 11,025 Hz Nyquist limit suitable for deliberately low-fi, soft polar ambience. Music additionally uses 12-bit quantization, sample-hold rate reduction and low-pass filtering. This is an aesthetic approximation, NOT emulation of particular hardware.
- WAV files have no embedded loop metadata. Runtime sets loop start=0, end=`frames` (exclusive) for `loop: true`, with no silence or crossfade inserted. No compressed-format conversion is assumed gapless.
- Resolve relative file paths against the manifest directory, NOT the game spec location. Copy `manifest.json` plus `wav/` together. Reject traversal/unknown IDs; do not silently substitute audio.

## Stable IDs

| IDs | Kind | Loop | Meaning |
|---|---|---|---|
| `footstep.snow.01` ... `.03` | sfx | false | Seeded packed-snow steps |
| `footstep.floor.01` ... `.03` | sfx | false | Soft boot on molded floor |
| `hatch.open` | sfx | false | Motor/air whoosh then cushioned latch thunk |
| `ui.move`, `ui.select`, `ui.back` | sfx | false | Short nonverbal interface cues |
| `dialogue.low`, `.mid`, `.bright`, `.airy` | sfx | false | Four nonverbal suited-resident voices; labels are not canon character names |
| `cat.meow.01`, `.02`; `cat.purr.01`, `.02`; `cat.chirp.01`, `.02` | sfx | false | Synthetic cat-like variations, not recordings |
| `sphere.pickup.01` ... `.08` | sfx | false | Glass chime; pitch rises strictly by collection count 1–8 |
| `keycard.accept` | sfx | false | Successful card acknowledgment |
| `storm.gust`, `pod.hum`, `saucer.pass`, `save.tone` | sfx | false | One-shot environmental/interaction cues |
| `ambience.habitat`, `ambience.outside`, `ambience.storm` | ambience | true | Habitat/vents, exterior wind/snow, storm bed |
| `music.hub`, `music.explore` | music | true | Original short calm and tense-but-cozy loops |

## Game-spec reference example (adapter contract, not installed schema)

```json
{
  "audio": {"manifest": "audio/manifest.json", "master_gain": 0.65},
  "rooms": [{
    "id": "habitat",
    "audio": {"ambience": "ambience.habitat", "music": "music.hub"}
  }],
  "characters": [{"id": "resident_01", "audio": {"dialogue": "dialogue.low"}}],
  "events": {
    "hatch_open": {"sound": "hatch.open"},
    "save_complete": {"sound": "save.tone"}
  }
}
```

These optional keys are an adapter proposal, NOT a claim that the story/compiler/runtime lane has accepted them. The stable handoff is ID → manifest record → WAV. Runtime/plugin owners decide their final spec field names.

- Choose step variant deterministically from step ordinal + actor seed, not wall clock.
- Choose pickup ID using `min(max(total_collected, 1), 8)`; `.01` is the FIRST collected sphere. Pitch rises across the eight supplied tiers, then stays at tier 8. A game with more tiers should generate them explicitly rather than apply arbitrary resampling.
- Suggested initial mix (untested): master 0.65; SFX 0.65; dialogue 0.35; ambience 0.28; music 0.35. These gains are not a tested no-clipping guarantee when voices overlap. Limit voices and meter the runtime master bus.
- Dialogue: one blip per roughly 2–4 visible characters, skip punctuation/whitespace; minimum 70 ms spacing, max one voice per speaking actor. Do not play every glyph concurrently.
- Fade room beds over ~0.5–1.0 s; fade on pause/scene exit. Preserve sample-accurate looping within a bed. Do not restart music for every interaction.
- Keep accessibility controls for music, effects and dialogue volume; never encode a required clue only in sound.

## Generator interface

Python 3.9 stdlib only, no network/services/samples. Implemented stable commands from lane root:

```sh
python3 -m thaw_audio.build --seed 73021
python3 -m thaw_audio.audit
python3 -m unittest discover -s tests -v
```

Python API: `thaw_audio.synth.render(kind, params)` → normalized float sample list; `thaw_audio.catalog.catalog(seed)` → resolved definitions; `thaw_audio.wavio.encode(samples)` → WAV bytes. Kinds and parameter ranges are documented in README. Seeds are unsigned 32-bit integers, exactly representable by double-based JSON consumers. Same seed and resolved inputs must produce byte-identical WAVs on the verified Python/platform. Cross-platform libm identity is not promised.

## Quality gates / honesty

Numerical rejection checks: peak/clipping, silence, DC, duration, WAV format/rate, loop seam amplitude/slope and boundary energy, deterministic bytes. Known-bad controls must fail for the correct named validator. A missing implementation or parse error does NOT prove a signal validator works.

Loop seam limits: absolute boundary jump <=0.003 full scale; adjacent-slope mismatch <=0.003; 20 ms RMS on each side >=0.35× whole-loop RMS (detects artificial fade-to-silence seams). All rendered loops are checked after PCM encoding.

**No listening possible in this lane.** Numeric validation and spectra do not establish pleasantness, believable cats, melodic quality, fatigue, console compatibility or actual gapless engine playback. Start listening review quietly. Potential risk categories: high sphere/bell tones, cat chirps, short dialogue transients, snow/storm hiss, resonant saucer tone. Per-file flags will be in the manifest.
