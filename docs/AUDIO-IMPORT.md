# Bring your own music and voice lines

Hermes64 makes its own music, but you can use your own instead. Give it MP3, OGG, FLAC or WAV files. They are converted to the game's audio format (16-bit WAV). Then you choose where each one plays: menu, a room, a wave, a boss, the results screen, or as a voice line.

Any game can do this, whatever its genre. The steps are the same every time.

## 1. What you need

- **ffmpeg** on your computer. Hermes64 never downloads it.
  - macOS: `brew install ffmpeg`
  - Windows: `winget install Gyan.FFmpeg`
  - Linux: install it with your package manager
- Hermes64 looks for ffmpeg in this order:
  1. the plugin setting `ffmpeg_path`
  2. `tools/bin/<windows|macos|linux>/ffmpeg[.exe]` inside the plugin
  3. your `PATH`
  4. common install folders
- If it can't find ffmpeg, you get an `ffmpeg_missing` error with these same instructions.
- Paths can contain spaces, brackets or non-English letters, and Windows drive letters work. Your files are only read, never changed or moved. Hermes64 runs ffmpeg directly, not through a shell.

## 2. Import

Through Hermes (the `hermes64_audio` tool):

```
hermes64_audio action=import project=my-game sources=["/Users/me/Music/game", "voices/hello.ogg"]
```

From a terminal (run this in the plugin folder):

```
python3 tools/audio_import.py import --projects-root /path/to/games --project my-game ~/Music/game/
python3 tools/audio_import.py import --out ./converted ~/Music/game/        # no project needed: convert + manifest only
```

- **Sources:** files or folders. A folder means every supported file directly inside it (not subfolders). Paths that aren't absolute count from the project folder.
- **IDs:** each file gets an ID made from its name. For example, `Boss Theme (v2).mp3` becomes `boss_theme_v2`. To pick your own IDs or settings, pass `items`:
  ```json
  [{"path": "/Users/me/Music/boss.mp3", "id": "boss_theme", "kind": "music", "start_s": 3.5, "max_seconds": 90, "crossfade_ms": 2000},
   {"path": "/Users/me/Voices/take3.wav", "id": "guide_hello", "kind": "voice"}]
  ```
- **Kinds:** `auto` (the default) treats files of 20 seconds or more as `music` and anything shorter as `voice`. You can also set `music`, `voice` or `sfx` yourself.
- **Re-importing:** importing an ID that already exists is refused. Pass `replace=true` (CLI: `--replace`) to overwrite it.
- **All or nothing:** files are processed in a staging folder. If any file fails, or the total goes over budget, nothing in your project changes.

### What happens to each file

| Step | Music | Voice | SFX |
|---|---|---|---|
| Format | 32 kHz stereo (steps down to fit the size cap) | 22.05 kHz mono | 22.05 kHz mono |
| Trim silence at start/end | below −60 dBFS | below −50 dBFS, keeps 40 ms | below −55 dBFS, keeps 10 ms |
| Loudness target (EBU R128, measured by ffmpeg) | **−18 LUFS** | **−15 LUFS** (3 dB above music) | −16 LUFS |
| Peak ceiling | −1 dBFS | −1 dBFS | −1 dBFS |
| Loop | yes, 1500 ms equal-power crossfade | no | no |
| Per-file size cap | 10 MiB | 1 MiB | 512 KiB |

- **Loudness limiting:** if reaching the target would push peaks over −1 dBFS, a gentle limiter takes off up to 6 dB of peaks. Spoken lines often need this. If more than 6 dB would be needed, the level is lowered instead, and you get a warning.
- **Loops:** the end of the track is crossfaded into its start, so playback wraps around without a gap. Use `start_s` to skip an intro you don't want repeated. Use `max_seconds` to shorten the loop.
- **Size:** if a file is over its cap, it is re-made at a lower quality, one step at a time: 32 kHz stereo → 22.05 kHz stereo → 22.05 kHz mono → 16 kHz mono. If it still doesn't fit, you get a `size_cap` error suggesting `max_seconds`.
- **Total budget:** all imported audio together must stay under 40 MiB (`max_total_bytes`). Web exports ship every WAV, so this keeps the first load reasonable.

### The report

The tool returns one entry per file, also saved in `audio/import/manifest.json`. Each entry includes:

- `output_lufs`: the loudness measured on the finished WAV
- `peak_dbfs`
- the format and size
- the size steps it tried, if any
- the silence trimmed
- the source file's name, hash, codec, sample rate and channels (only the file name is stored, never your folder path)
- a `seam` record for loops:
  - `jump_ratio`: the size of the step from the last sample back to the first, compared with an average step. About 1 is invisible; above 4 risks a click.
  - `click_db`: the biggest step within 5 ms of the loop point, compared with the track's typical step
  - `rms_delta_db`: the change in loudness between the last and first 250 ms
  - `verdict`: `seamless` or `audible_risk`

Possible `warnings`:

- `source_clipped`: the original file was already distorted. Normalising can't fix that.
- `low_source_rate`: the source had a lower sample rate than the output, so upsampling adds no new detail.
- `upmixed` / `downmixed`
- `size_ladder`
- `limiter`
- `peak_limited`
- `loop_seam`
- `loudness_rms_fallback`: the clip is too short for an EBU R128 measurement

Files that are refused, with nothing written:

| Error | Cause |
|---|---|
| `silent` | the file has no sound |
| `source_too_large` / `source_too_long` | over 256 MiB, or over 15 minutes |
| `format` | unsupported file type |
| `id` | two files give the same ID |
| `size_cap` / `size_budget` | too big, see above |
| `too_short` | under 50 ms left after trimming |

## 3. Assign slots

Slots say where each imported sound plays. They are saved in `audio/slots.json`, alongside your other project data:

```
hermes64_audio action=assign project=my-game slots_json='{
  "music": {"default": "explore", "menu": "title", "results": "fanfare", "boss": "boss_theme",
            "scenes": {"harbour": "sea_shanty"}, "waves": {"1": "wave_a", "2": "wave_b"},
            "events": {"region_unlocked": "wonder"}},
  "voice": {"guide_hello": {"asset": "guide_hello", "on_scene": "harbour"},
            "keeper_warn": {"asset": "keeper_warn", "on_action": "talk:keeper"}},
  "cues":  {"interact": "chime", "door_creak": "door"},
  "mix":   {"music_db": -6, "voice_db": -3, "sfx_db": -6, "crossfade_s": 1.5}
}'
```

CLI: `python3 tools/audio_import.py assign --projects-root ... --project my-game --slots slots.json`

**Music slots:**

| Slot | When it plays |
|---|---|
| `default` | everywhere, unless something more specific applies |
| `scenes.<room id>` | in that room (use the room IDs from your story) |
| `waves.<n>` | when a module sends a `wave_started` event with `{"wave": n}` |
| `boss` | from the first `boss_phase` until `boss_defeated` or `encounter_cleared` |
| `events.<kind>` | from any module event of that kind (for example `region_unlocked` or `challenge_failed`) until you leave the room |
| `menu` | while the pause or action menu is open |
| `results` | once an ending is reached |

If more than one applies, the first match in this list wins: results, menu, event/boss/wave, scene, default. Changing tracks always crossfades (`mix.crossfade_s`).

**Voice lines** are keyed by line ID. A line can play automatically:

- `on_scene`: when you enter that room
- `on_action`: when that story action is taken
- `on_event`: when that module event fires

Runtime code can also call `voice("<line id>")`.

**Cues:**

- `ambient` replaces the pack's looping background sound.
- `interact` replaces the sound for story actions.
- Any other name becomes `cue:<name>`, which the combat and puzzle modules can play.

**Mix:** sets each kind's in-game level on top of its normalised loudness. Voice is 3 dB louder than music by default.

**Combat sounds (`combat_sfx`):** off unless you list them. `"combat_sfx": "default"` plays the plugin's own original
set (`audio/combat_sfx/`, CC0, no import needed) for every combat event. Or name events one by one, each `"default"`, an
imported `sfx` asset ID, or a list of up to 4 IDs (played as variants):

```
"combat_sfx": {"robot_hit": ["clang_a", "clang_b"], "boss_hit": "default", "punch_miss": "default"}
```

Events: `punch_hit` (a hit on a non-robot enemy), `punch_miss` (a swing's hit window closes with no hit),
`robot_hit`, `boss_hit` (also a boss defeat), `player_hurt`, `dodge` (a roll starts), `block` (block, armour or
deflect), `robot_death`, `boss_telegraph`. An event you list replaces the pack's stock combat cue for that moment;
events you leave out keep the stock cue. Each sound plays once (no loop) at `mix.sfx_db`. One event plays at most once
every 4 to 30 ticks (hits 4, telegraph 30). At most 4 combat sounds play at once (the longest-playing one is cut).
Music drops 3 to 4 dB for 0.35 s under a boss hit, a hurt or a robot death.

Unknown asset IDs or the wrong kind (for example a voice file in a music slot) are refused. Each build re-checks every slot and file hash. If an imported file changed on disk, the build stops with an error instead of playing something else.

## 4. Build, play, check

Rebuild or open the game as usual. Your audio is included in the game's audio list (`runtime/audio.json`, as `music:*`, `voice:*` and `cue:*` entries) and in exports like every other sound.

`hermes64_audio action=imported project=my-game` (CLI: `status`) re-checks every file's hash and shows your slots and the size report.

### Volume settings

The game has three volume groups: **Music**, **Voice** and **SFX**. Players can set them in `user://hermes64_audio.json`:

```json
{"master": 1.0, "music": 0.7, "voice": 1.0, "sfx": 0.8}
```

Values run from 0 to 1, and 0 mutes. The game reads this file but never writes it, and replays and test bots never change it. If the file is missing, everything plays at full volume. There is no in-game volume slider yet.

### Simulation and replays are unaffected

Audio only affects what you hear. The audio code never reads or changes game state, random numbers or physics, and headless test runs load and hash-check files without playing them. Replays, saves and proofs come out the same whether or not you import audio.

## Limits

- Loudness and seam numbers are measurements, not listening. A `seamless` verdict means no click or level jump was measured at the loop point. It doesn't mean the loop sounds musically right, so listen before you ship.
- Output hashes are byte-identical for the same input files and the same ffmpeg build. A different ffmpeg version can change decoding or resampling slightly. The manifest records the ffmpeg version.
- Only use music and voice recordings you have the rights to. Hermes64 does not check licences on imported files.
