# Default combat sounds (COMBATFIX)

14 original sounds for the combat events, made from oscillators and seeded noise by `tools/combat_sfx_synth.py`. No
recordings or samples from anywhere are used. License: CC0 1.0 (public domain dedication), for the script and the
WAV files.

| Event | Files |
|---|---|
| `punch_hit` (a hit on a non-robot enemy) | `punch_hit_1..3.wav` |
| `punch_miss` (a swing's hit window closes with no hit) | `punch_miss.wav` |
| `robot_hit` | `robot_hit_1..3.wav` |
| `boss_hit` (also a boss defeat) | `boss_hit_1..2.wav` |
| `player_hurt` | `player_hurt.wav` |
| `dodge` (a roll starts) | `dodge.wav` |
| `block` (block, armour, deflect) | `block.wav` |
| `robot_death` | `robot_death.wav` |
| `boss_telegraph` (a boss starts a telegraph) | `boss_telegraph.wav` |

Format: 22.05 kHz mono 16-bit PCM WAV, each at most 60,000 bytes, sample peak -3.5 to -5.7 dBFS, -16 LUFS as the
plugin's sfx import measures it. `combat_sfx.json` lists each file's event, sha256 and numbers. A game plays them only
when its `audio/slots.json` lists `combat_sfx` (docs/AUDIO-IMPORT.md); the build refuses a changed file.

Re-make or check: `python3 tools/combat_sfx_synth.py --out DIR`, `--check audio/combat_sfx` (byte equality and every
limit), `--self-test` (known-bad variants are refused). Needs numpy.
