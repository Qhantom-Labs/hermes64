# AUDIO2 integration contract (2.0.0)

**Owner: Hermes Main.** This lane provides source modules and verified offline tools, not live Hermes activation or runtime adoption. All new audio is **machine-checked, not human-approved** after validation. The existing 208 legacy WAVs, catalog, manifest and DSP are not rewritten.

## Minimal plugin merge (not applied in this lane)

Keep the existing general tool router intact. The audio tool has its own action validator/service and uses the same configured `projects_root` and cooperative project lock.

1. `plugin.yaml:7`: append the exact string `"hermes64_audio"` to `provides_tools`.
2. `__init__.py`, after its existing tools import, add:
   ```python
   from .adventure_maker.audio_tools import register_audio_tools
   ```
3. Inside `register(ctx)`, immediately after `register_tools(ctx)`, add:
   ```python
   register_audio_tools(ctx)
   ```
4. Schemas are already implemented in **`adventure_maker/audio_schemas.py`**, exporting:
   ```python
   SCHEMAS = {'hermes64_audio': AUDIO_SCHEMA}
   ```
   **No edit to `adventure_maker/schemas.py` is required.** Do not merely append the audio schema to that legacy `SCHEMAS`: `adventure_maker/tools.py` would route it to the legacy `Service`, which does not implement audio actions. Dedicated registration binds the correct `AudioService`.
5. With registration merged, `tests/test_registration.py:43` changes the expected tool count from `13` to `14`. Its existing manifest/registered-name equality and invalid-argument checks must continue passing. Include `skills/hermes64-audio/SKILL.md` in the packaged skill tree.
6. No Python dependencies/config keys, network privileges, service restarts, engine installs or shared runtime edits are needed. Load/admit the plugin only through Main's normal owner-approved route. Offline recording-context tests are not proof of live admission.

**Existing files changed by AUDIO2 for wiring: none.** All new implementation is additive. Python package-relative legacy imports are exercised under an isolated plugin package name, not only an accidental repository `sys.path`.

## Tool calls

All calls use `hermes64_audio`. Action names are exact:

| Action | Required beyond `action` | Optional / effect |
|---|---|---|
| `list` | none | `category`, `tags`, `limit` 1..50, `offset` |
| `search` | none | `query` (AND substring terms), exact AND `tags`, category, pagination |
| `preview` | `project`, `export`, `id` | `transform`; render a sound or full track bundle, never auto-play |
| `variation` | project/export/id, uint32 `seed`, `ordinal` 0..1023 | seed is actor/pool seed, not global RNG; transform optional |
| `music` | project/export, `music` object | mood/mode/key/tempo/**bars**/seed/style/instruments; transform optional |
| `voice` | project/export, `text` | `voice` object character/emotion/seed/pitch/rate/timbre/formant; transform optional |
| `bank` | project/export | `palette` OR project-relative `profile_path`; `max_bytes` <=32 MiB, `max_assets` <=64 |
| `validate` | project/export | rereads every artifact and rerenders each asset; no option to suppress determinism through the tool |

Arguments that belong to another action, unknown fields, NaN/Infinity, booleans as seeds, unknown IDs, traversal and unsupported parameters reject. No fallback sound is silently substituted.

`project` and `export` are lowercase slugs, not paths. Exports live only at `exports/audio/<export>/` inside an existing managed project. An existing export refuses, even when its previous run was interrupted. No source `.maker/current.json`, game spec, visual profile, pack, runtime or legacy audio is changed. A partial directory is not complete without a valid `bank.json`; the owner should inspect interrupted output, not silently overwrite it.

Discovery returns true `total`, `matched`, `returned`, `has_more` and `next_offset`. Variation members are NOT included in those totals. New canonical IDs begin `h64.`. Generated ad-hoc music/voice use `h64.generated.music`/`h64.generated.voice` scoped to their export, not global catalog insertion.

## Artifacts and reference contract

A bank has `format:2`, `generator_version`, `assets`, `artifacts`, `bindings`, `budgets`, `payload_bytes`, `review_status` and optional palette ID.

- Each canonical asset has ID, purpose, category/tags, style compatibility tags, actual duration/frame count, loop flag, pool specification, complete source recipe/seed, applied transform, licence, peak/RMS/DC/seam, unweighted RMS dBFS, SHA-256 and primary relative file.
- `artifacts` enumerates every generated file. WAV metrics are remeasured; hashes/sizes and complete inventory are checked. Unlisted files reject. Licence is `CC0-1.0` on every asset/artifact.
- Asset paths are relative to the **bank directory**, not the spec or repository. The bank's manifest is not a licence to read arbitrary paths.
- Runtime-facing `bindings` map an event name to `{ "ids": ["h64.ui.confirm.soft"], "gain": 0.5 }`. `gain` is runtime attenuation, not baked normalization. IDs must resolve within the bank. Preserve pool/actor seeds in save/replay state if event replay must sound identical.
- Example host mapping (proposal, not a change to story schema): room ambience → `ambient`; controller foot contact → `walk`/`run`; inventory reward → `pickup`; dialogue speaker → generated voice WAV/timing. The host should resolve the ID from the manifest rather than constructing filenames.

Do not add arbitrary audio JSON to a frozen story contract and claim the compiler accepts it. Main owns versioned schema/compiler/runtime integration. No audio action activates combat, vehicles, world streaming or another gameplay module.

## Music

`music` accepts mood (`explore`, `home`, `mystery`, `night`, `danger`, `chase`, `wonder`, `sadness`, `victory`, `desert`, `water`, `machine`), mode (`major`, `minor`, `dorian`, `mixolydian`, `phrygian`, `pentatonic`), musical key (C..B with supported sharps/flats), tempo 40..180 BPM, 2..16 four-beat bars and uint32 seed. Total length may not exceed 60 seconds. Length is in bars, not arbitrary seconds, to preserve complete musical cycles.

Styles are data: `sequenced`, `cold_ambient`, `warm_folk`, `desert_folk`. Instrument maps choose ocarina-like flute, flute, strings/glass pad, mallets/wood mallets/harp, bass and soft drums. These are original procedural instruments, not samples of any game or hardware.

Each render produces:
- `loop.wav`: full arrangement.
- `score.mid`: standard type-1 MIDI, 480 PPQ; conductor tempo/time signature/loop markers plus five named parts. Program numbers are zero-based GM. Drums use channel 10 (wire channel 9).
- `score.json`: exact progression, seeded motif, event timing/velocity, integer MIDI tempo, mastering and adaptive weights.
- `stem-{pad,melody,bass,arpeggio,drums}.wav` and `layer-{explore,tension,danger}.wav`.

WAV/MIDI events use the same integer microseconds-per-quarter clock. Export frame count is rounded once; the difference from ideal duration is below a sample. All stems/layers start at the same origin and have the same frame count. Reverb tails wrap circularly. The fixed-origin mastering bridge touches <=2 ms on each side of the seam; music is **not rotated**. Sparse stems can contain intentional rests at the seam; mixed tracks must pass the non-silent boundary gate.

Crossfade the aligned mixes with linear amplitude weights over ~0.5 s (implementation: `audio_music.crossfade`). Do not sum all mixes, independently normalize stems, or restart a track when intensity changes. Shared gain is bounded using the sum of stem magnitudes, not cancellation in the full mix. MIDI carries notes/program hints; another GM synth will not sound identical to these WAVs. Actual musical quality still requires listening.

## Voice timing

Original additive/formant babble, no sampled speech and no TTS. Character presets: narrator, elder, child, robot, hooded-faceless and creature. Emotions modify pitch, cadence, glide and brightness as data. Every rendered line includes `timing.json` with per-codepoint reveal frames, punctuation pauses, actual blip start/end frames and per-blip recipe/seed. No blips are assigned to whitespace/punctuation.

Timing indices are **Unicode codepoints**, not UTF-16 code units or grapheme clusters. A UI must map graphemes explicitly. Drive reveal from the playback sample clock; cancelling dialogue should stop both audio and reveal. Blips have bounded spacing and do not stack every glyph. Lines over 1000 codepoints, silent-only lines or >60 s renders reject; split long dialogue explicitly.

## Style-profile and pack adapters

`audio/expansion/palettes.json` contains four ready-made palettes and a mapping from existing style cue generator/preset pairs to canonical sound IDs and transforms. Existing `profiles/n64_base/profile.json`, polar/warm-desert examples, and `packs/*/pack.json` are not rewritten or rehashed.

For `bank(profile_path=...)`, the project-local document may contain:
1. `audio_palette` with `{format:2,id,transform,bindings}`. This is an audio-only companion document, NOT a newly admitted visual profile field.
2. Existing `sections.audio.cues` with the supported generator/preset names. Unknown pairs, conflicting transforms and loop mismatches reject. This is audio extraction only; it does not resolve visual inheritance or certify an entire visual profile.
3. Existing pack `sound_palette` paths. Paths resolve only by exact match against the canonical legacy catalog; they are never arbitrary file reads. Frozen files remain unchanged.

Transforms: pitch in semitones, soft filter cutoff, early-reflection time/mix, 22,050/32,000 Hz export and music instrument choices. Instrument choices affect only music; nonmusic receives the common pitch/filter/reverb transform. Music pitch transposition requires whole semitones so score/MIDI/WAV agree. New themes require data, not core code changes.

Music transposition shifts the actual melodic note numbers, including octave crossings, and leaves GM drum assignments unchanged. The supplied key string is preserved; a nonzero shift is recorded as `score.transpose_semitones`. A +12 shift is an octave, not a modulo-12 no-op.

## N64-era mastering and numeric gates

`audio/expansion/identity.json` defines the aesthetic. Default mono PCM16 at 22,050 Hz, 14-bit internal quantization, gentle low-pass, short reflections, soft saturation and RMS-targeted/peak-limited gain. 32 kHz is an optional export transform. Legacy WAVs retain their original gentle low-fi mastering, not a second destructive mastering pass.

Omitted transform fields inherit that data file; explicit transforms override it. Measured catalog metadata is accepted only when the recipe, preset-data and DSP source fingerprints match the verification receipt. Editing identity/instruments/voices therefore invalidates old measured peaks/hashes/review status until a real rebuild; it never silently reuses a stale machine-check label.

New default ceiling is 0.46 FS. Validation independently rejects >0.90 FS peaks, abs DC >0.002, RMS <0.0005, unweighted RMS dBFS outside -48..-12, loop jump/slope >0.003 FS, and mixed-loop boundary RMS below 0.35 of whole-file RMS. Category-level bank loudness spread is capped at 18 dB. No pass is LUFS, true peak, perceptual comfort or overlap-mix certification.

Budget counts all rendered payloads including stems, MIDI, score and timing JSON. Manifest JSON has the inherited 1 MiB bound. Ship recipes and the small expansion cache, not `audio/evidence/audio2` rebuilds or all music stems. Full catalog renders and sampler sizes are reported in the final receipt, not inferred from preset duration.

## Upcoming gameplay module handoff

Read-only design packet reviewed: `lane-gamemodules/SUMMARY.md` and audio/animation references. Its modules remain proposals. Suggested event bindings:

| Proposed event | Available cue |
|---|---|
| melee swing / parry / armor hit | `h64.combat.sword.swing` / `.sword.parry` / `.hit.armor` |
| dodge / stagger / defeat | `h64.combat.dodge.roll` / `.hurt.stagger` / `.death.small` |
| gate / ability unlock | `h64.door.portcullis.raise` / `h64.reward.ability.unlock` |
| timed-course checkpoint / finish | `h64.reward.race.checkpoint` / `h64.stinger.race.finish` |
| optional skimmer idle / boost | `h64.vehicle.hover.idle` / `.hover.boost` |
| outdoor region / tension | biome ambience IDs plus aligned explore/tension/danger music mixes |

These IDs are stock audio, not proof of playable combat, horses, racing physics or open-world streaming. Bind attack sounds to actual animation/contact events, not checker success. Keep gameplay-critical information visible as well as audible.

## Verification boundary

Run `/usr/bin/python3 -B -m unittest tests.test_audio2_dsp tests.test_audio2_catalog tests.test_audio2_music_voice tests.test_audio2_tools tests.test_audio2_pipeline -v` on the verified macOS environment. For portable development use the explicitly selected Python 3.9 interpreter, not an unpinned background-shell `python3`. `python3 -B -m tools.audio2_verify` performs two distinct process renders and bank proofs. The optional sampler destination is restricted to the commissioned sibling sampler folder or verification scratch.

Human listening, new-audio in-game timing/mixing, device latency, cross-platform bit identity, hardware emulation, BS.1770/true peak, live Hermes admission and independent review remain separate acceptance gates.
