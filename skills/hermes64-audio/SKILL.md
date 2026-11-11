---
name: hermes64-audio
description: Create and validate original retro game audio banks.
version: 0.1.0
author: Qhantom Labs, Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [audio, games, original, offline]
    related_skills: [hermes64]
---

# Hermes64 audio

Original procedural effects, nonverbal character babble and sequenced music. Python 3.9 stdlib only. No sampled speech, TTS, model, soundfont, download or external service. This is an N64-era aesthetic, not hardware emulation.

## When to use
- Find sound IDs, create sound variations, compose loop music with MIDI/stems, or generate dialogue blips synchronized to text.
- Build an audio bank from a data-only palette or an existing style profile.
- Do not use to imitate a recording, activate held gameplay modules, play sound without permission, or certify perceptual quality.

## Prerequisites
Main must merge the explicit registration changes in `docs/AUDIO-INTEGRATION.md` before `hermes64_audio` is discoverable in Hermes. The offline module is usable without plugin activation. A configured, existing `projects_root` and a scaffolded managed project are required for writes. Discovery needs neither. No engines are needed for synthesis; actual runtime playback is a separate test.

## Procedure
1. Call `hermes64_audio(action="search", tags=["footsteps","run"], limit=20)`. Follow `next_offset` while `has_more` is true; do not infer counts from the displayed subset. `list` is unfiltered discovery. Stable new IDs begin `h64.`; the existing legacy IDs remain byte-preserved.
2. Preview with `action="preview", project="game", export="preview-01", id="h64.footstep.snow.run"`. The tool renders, it does not play. Output is confined to a NEW `exports/audio/<export>/` directory in the managed project. Reuse of a name refuses rather than overwrites.
3. For variations use `action="variation"`, the same ID, `seed` (actor seed) and `ordinal` (0..1023). A pool has four reproducible members with no immediate repeat. Pool members are not extra catalog assets. Frozen legacy WAVs cannot be transformed or varied; choose a new recipe instead.
4. For music use `action="music", music={"mood":"explore","mode":"dorian","key":"D","tempo":96,"bars":8,"seed":42,"style":"warm_folk"}` plus project/export. Length is in four-beat bars, 2..16, capped at 60 seconds. Read `score.json`: actual integer MIDI tempo, progression, motif, events, master gain and adaptive weights are explicit. WAV, standard MIDI, five stems and explore/tension/danger mixes are returned together.
5. For dialogue use `action="voice", text="Hello, traveller!", voice={"character":"elder","emotion":"curious","seed":19}` plus project/export. Optional pitch/rate/timbre/formant are validated. `timing.json` uses Unicode codepoint indices and audio-frame timestamps, not UTF-16 offsets or grapheme indices. Skip whitespace/punctuation blips but preserve their reveal pauses. Play from the audio clock; do not independently schedule text using wall-clock sleeps.
6. For banks use `action="bank", palette="polar"` (also neutral/forest/desert), or a project-relative `profile_path` to an audio-only palette, native style `sections.audio`, or pack `sound_palette`. Do not pass both. Unknown presets/IDs fail. A new palette selects IDs and pitch/filter/reverb/instruments as data; never add a theme-ID branch to synthesis code. This is audio resolution, not visual profile validation.
7. Call `action="validate"` with the same project/export. Require `ok:true` and `determinism_checked` equal to asset count. This reads every file, checks licence/metrics/bindings/budgets and compares a fresh render of every artifact. A SHA alone is not proof of the correct source recipe.
8. Give the manifest path, source IDs, real measured size/peak/RMS and review limits to the runtime owner. Every new sound remains **machine-checked, not human-approved**. Ask for quiet human listening before adopting a mix. No new sound becomes approved because the validator passed.

## Bring your own audio (import / assign / imported)
User music and voice lines (MP3/OGG/FLAC/WAV) become runtime WAVs with the user's local ffmpeg. Full guide: `docs/AUDIO-IMPORT.md`.
1. `hermes64_audio(action="import", project="game", sources=["/abs/folder", "song.mp3"])`. Relative sources are project-relative. `kind` auto|music|voice|sfx (auto: ≥20 s is music). Use `items=[{"path":..., "id":"boss_theme", "kind":"music", "start_s":4, "max_seconds":90, "crossfade_ms":2000}]` for explicit IDs. `options` takes loop, crossfade_ms, start_s, max_seconds, max_file_bytes, max_total_bytes. Re-importing an ID needs `replace=true`.
2. Read each asset's `output_lufs` (music −18, voice −15, sfx −16), `seam.verdict` (seamless / audible_risk) and `warnings` (source_clipped, low_source_rate, size_ladder, limiter, loop_seam). Report them; do not hide an audible_risk seam. Fix it with start_s/max_seconds/crossfade_ms.
3. `action="assign", slots_json="{...}"` with `music` (default, menu, results, boss, scenes{room}, waves{n}, events{module event kind}), `voice` {line: id | {asset, on_action|on_scene|on_event}}, `cues` {ambient|interact|cue id: id} and `mix` (music_db, voice_db, sfx_db, crossfade_s). Unknown IDs or wrong kinds refuse.
4. Rebuild/open the game. The build re-hashes every imported file. `action="imported"` reports problems, slots and the web size budget.
- ffmpeg missing → `ffmpeg_missing` with install steps. Never download it; the user installs it or sets `ffmpeg_path`.
- Over budget → `size_budget` / `size_cap`, nothing written. Shorten music (max_seconds) before raising caps: web exports ship every WAV.
- Numbers are not listening. Say plainly that loudness/seam values are measured, not heard.

## Pitfalls
- RMS dBFS is an unweighted loudness approximation, **not LUFS**, BS.1770 or true peak. A clean isolated peak does not protect an overlapping runtime mix.
- Never sum all three adaptive mixes: run them on the same sample clock and crossfade with linear amplitude weights. Alternatively use stems and `score.json` weights. Stems share one gain; do not independently normalize them. Transpose actual melodic note numbers, not key classes modulo twelve, and leave drum assignments unchanged. GM MIDI playback uses the player's instruments, not identical WAV timbres.
- Loops contain circular tails, no silent endpoint fades. Only sparse stems may have intentional boundary rests; mixed loops/ambience must pass energy checks. Numeric seam checks cannot establish musical continuity or inaudibility.
- Voices are synthetic babble, not intelligible speech or voice clones. Animal recognizability, harshness, hiss, repetition and fatigue need listening. The same short line repeated can be annoying even with variation pools.
- Output budgets cover all WAV/MIDI/score/timing payloads (default 32 MiB, 64 canonical assets); manifest JSON has its own 1 MiB bound. Select a small bank, not the entire catalog. Recipes are rendered on demand.
- After editing recipe/preset/mastering data or synthesis code, rerun the two-process verifier. Catalog measurements are source-fingerprinted and are withheld after a source change; do not copy old measurements or hardcode defaults that bypass the identity data.
- Project locks refuse concurrent operations. Never delete another operation's lock. An interrupted directory without a valid bank is incomplete; choose a new export name until the owner inspects it.
- Registration is not live activation. In-game event dispatch, attenuation, device latency and mix/timing remain a separate runtime-owner acceptance step.

## Verification
Use `terminal` for `python3 -B -m unittest tests.test_audio2_dsp tests.test_audio2_catalog tests.test_audio2_music_voice tests.test_audio2_tools tests.test_audio2_pipeline -v` from the repository root. Resolve and verify the Python 3.9 executable first, then use its absolute path for background jobs: shell initialization can select a different interpreter. Full offline expansion receipts are produced by `python3 -B -m tools.audio2_verify`; it runs two separate render processes and retains actual hashes and metrics. Do not rewrite frozen legacy audio. Use `read_file` on manifests/reports instead of treating a tool exit as human approval.

Before changing a loop validator, reproduce the failing recipe: pulsed beds may need a declared circular origin, not relaxed gates. Keep music at its fixed MIDI/sample-clock origin. For fractional envelopes, enforce analytic endpoints before mastering; floating-point sine can fall just below zero at pi and yield a complex value under a fractional power.

Git does not preserve historic file mtimes. If a frozen legacy test fails its timestamp check in a fresh worktree, first verify every protected byte hash and record the failure. Do not rewrite source timestamps or lower the gate to obtain a green report. A separate byte-identical fixture with restored historical timestamps can test the legacy code, but it is not a pass of the unmodified worktree verifier.
