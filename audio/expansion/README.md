# Hermes64 AUDIO2 — recipe-first expansion

302 new purpose-labelled recipes, plus the unchanged 208-entry legacy library. The `hermes64_audio` search surface combines both; it does not count the four members of a variation pool as four catalog entries. All new material is original procedural synthesis, with no samples, TTS, downloads, installs or third-party Python packages.

**New audio is machine-checked, not human-approved.** See `RESULT.md` for actual execution receipts and unverified gates. Listening, animal recognizability, musical quality, fatigue and in-game balance cannot be established by file metrics.

## Contents

| File | Role |
|---|---|
| `recipes.json` | Complete canonical recipes, purpose, category/tags, duration, loop, seed, variation pool, CC0 and compatibility tags |
| `catalog.json` | Measured per-asset PCM metrics/hash, RMS dBFS approximation and optional compact-cache path; generated only after two-process verification |
| `identity.json` | Data-defined N64-era mastering conventions |
| `music.json` | Original sequenced instrument models, style mappings, mood progressions/rhythms |
| `voices.json` | Six character timbres and six emotion transformations |
| `palettes.json` | Neutral/polar/forest/desert selections/transforms and native profile cue adapters |
| `cache/` | Small useful subset: twelve walking surfaces plus six UI cues; not the full expanded WAV library |
| `CC0.txt` | Generated-material dedication and canonical CC0 instrument |
| `verification/` | Compact actual receipts, not rebuild WAVs |

`audio/catalog.json`, `audio/manifest.json`, `audio/wav/`, `audio/stock/wav/` and the legacy synthesis source remain unchanged. New filenames are never silently substituted for old IDs. Newly measured metadata lives here rather than invalidating frozen legacy hashes.

## Coverage

| Category | New canonical entries |
|---|---:|
| Ambience | 20 |
| Combat | 32 |
| Creatures | 24 |
| Fire/explosions | 8 |
| Material foley | 24 |
| Footsteps | 24 |
| Machines/electronics | 20 |
| Magic/energy | 16 |
| Doors/hatches/locks/mechanisms | 20 |
| Movement/hooves/skids | 14 |
| Music | 12 |
| Pickups/rewards/jingles | 18 |
| Stingers | 8 |
| UI | 24 |
| Vehicle engines | 10 |
| Dialogue voice demonstrations | 6 |
| Water | 12 |
| Weather one-shots | 10 |

Footsteps cover snow, ice, stone, wood, metal, grass, leaves, gravel, sand, mud, water and carpet, each with walk/run contacts. Variation members change bounded pitch and seeded microtexture without inflating the canonical count. Tests reject seed-only duplicate recipes; byte uniqueness is also checked. These objective checks do not certify perceptual distinctness.

Music covers polar twilight, forest paths, desert caravans, village hearths, caves, markets, harbors, ruins, combat, racing, machinery and an ending. Each track includes five stems, three aligned adaptive mixes, loop WAV, original score data and standard MIDI. The generator also accepts new key/mode/mood/tempo/bar-count/seed/style inputs. Voice lines include elder/child/robot/hooded-faceless/creature/narrator, configurable formant/pitch/timbre/rate, emotions and sample-clock typewriter data.

## Use

The offline API is `adventure_maker.audio_tools.AudioService(settings).handle(arguments)` and returns JSON. Hermes registration instructions and exact calls are in [`docs/AUDIO-INTEGRATION.md`](../../docs/AUDIO-INTEGRATION.md); the bundled workflow is [`skills/hermes64-audio/SKILL.md`](../../skills/hermes64-audio/SKILL.md).

The normal workflow is search → render preview/variation/music/voice or build a style bank → validate → quiet human audition → runtime-owner integration. Writes require an existing managed project and a fresh export slug. Files stay under `exports/audio/<export>/`; the tool does not play or publish them.

### Reproduce offline

From repository root, with an explicitly chosen Python 3.9 interpreter:

```sh
/usr/bin/python3 -B -m unittest tests.test_audio2_dsp tests.test_audio2_catalog tests.test_audio2_music_voice tests.test_audio2_tools tests.test_audio2_pipeline -v
/usr/bin/python3 -B -m tools.audio2_verify
sh tools/verify_all.sh
```

On other platforms replace `/usr/bin/python3` with the verified interpreter path. Do not assume a background shell resolves the same `python3` as a foreground shell. The full expansion verifier spawns two separate processes, checks every generated artifact, runs known-bad controls, builds/revalidates four style banks, preserves legacy hashes/mtimes, and publishes the compact catalog/cache only after those gates pass. Its rebuild WAVs remain ignored under `audio/evidence/audio2/`.

`tools/audio2_author.py` is the readable data-authoring source for `recipes.json`; changing it or synthesis/mastering data requires re-verification. `catalog.json` is measured output, never a hand-authored success fixture.

## Identity, budgets and limits

Default: 22.05 kHz mono PCM16, 14-bit internal texture, soft low-pass, short reverb, restrained RMS/peak. Optional 32 kHz export. It is a low-memory/sequenced aesthetic, not a particular console DSP emulator. RMS dBFS is deliberately labelled **not LUFS**.

Loops use circular synthesis/tails and a short fixed-origin C1 boundary bridge, not silence ramps. The pulsed radar recipe explicitly selects a non-silent circular origin; musical timelines are never rotated. Sparse music stems allow intentional rests, while full loops must pass boundary energy checks.

Default project bank caps: 64 canonical assets and 32 MiB of rendered payload, including all stems/MIDI/JSON sidecars. Manifest JSON has a separate 1 MiB cap. The compact bundled cache is limited to 1 MiB; render the rest on demand. Full-size rebuilds, verification projects and the owner's sampler WAVs are not repository payload. Exact disk totals are in `RESULT.md`.

Known risks, not heard: bright glass/metal and creature highs may ring; noisy weather/fire can fatigue; voices are babble rather than speech; repeating short loops/blips can become obvious; per-file headroom does not guarantee safe overlap. Reverb and sampler preview fades are not proof of seamless runtime playback. No new sound is approved by an automated validator.
