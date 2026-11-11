# Handoff to L4 (template/premise): Nous showcase scenes as DATA

Not plugin code and not in the package. This is the shape the `teknium-vs-tyrants` premise file
should emit into `metadata.presentation.scenes`, following the owner's 11-10 direction: cutscenes for the
transitions between rooms and waves (for example Teknium runs from the street to the subway), the
server room is the gloat scene, the finale is on the rooftop. This changes 05C section 7, where the
finale and the CEO lines were on the server floor; the owner's later direction wins.

Every coordinate below is a **placeholder**: the cyber rooms are on `cyberpolish-lane` and their
final sizes and anchors were not read by this lane. `story/presentation/scenes.py` will refuse the
file until the room ids, door pairs and positions match the real pack rooms. Character ids are the
CHARS3/cameo ids as 05C names them; replace with the bound ids.

| Scene id | Trigger | Content |
|---|---|---|
| `gloat` | `start` | O1 in `server_room`: captive centre, three CEOs (`taunt`, falls back to `idle`), low wide `hold` then slow `push`. No dialogue, optional `vo_ceos_laugh` |
| `signal` | `start` (second) | O2 `tower_roof`, `pan` up to the sky signal; O3 behind Teknium at the desk (`type` then `look_up`), `push` |
| `to_wave1` | `door` `tower_roof` -> `canyon` | `track` Teknium running across the roof edge; card 2 `title` `WAVE 1  NOT EVIL AI`, `cut: iris` |
| `to_wave2` | `door` `canyon` -> `subway` | Teknium runs from the street down to the subway: `track` on the street, `cut` to a `hold` on the stairs; `title` `WAVE 2  CLOSED MODELS CORP` |
| `to_wave3` | `door` `subway` -> `club` | `track` through the platform; `title` `WAVE 3  AIPO` |
| `server_gloat` | `enter` `server_room` | P1-P6 from 05C section 7 word for word, one `voice` id per card (`vo_aipo_1`, `vo_aipo_2`, `vo_closed_models`, `vo_not_evil_1`, `vo_not_evil_2`, `vo_teknium`), `push`/`hold` close shots, holds as in 05C |
| `to_roof` | `door` `server_room` -> `rooftop` | the CEOs flee up; `track` Teknium on the stairs; `title` `FINALE` |
| `rescue` | `ending` | E1/E2 on `rooftop`: freed captive and Teknium (`idle`, then `walk` with `to`) |

Results: `{"enabled": true, "music": "results"}`. With `gameplay.run` (combat2) the card shows the run
clock with the +10 s penalties inside it, DEATHS and PENALTY.

Example card (placeholder numbers):

```json
{"id": "to_wave2", "trigger": {"on": "door", "from": "canyon", "to": "subway"},
 "cards": [
  {"room": "canyon", "hold": 150, "cast_only": true,
   "actors": [{"character": "protagonist", "at": [4, 16], "to": [10, 19], "moving_clip": "run"}],
   "shot": {"kind": "track", "follow": 0, "offset": [0, 2.2, 3.0]}},
  {"room": "subway", "hold": 120, "cut": "iris", "title": "WAVE 2  CLOSED MODELS CORP",
   "shot": {"kind": "pan", "from": [10, 3, 11], "look": [4, 1, 5], "look_to": [7, 1, 4]}}]}
```

Open for Main/L4: whether the music for the server-room lines stays `music.scenes.server_room` (the
scene does not switch music) or the finale track moves to the rooftop room slot.
