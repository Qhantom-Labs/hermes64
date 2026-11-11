# Mood list (kits/core/mood.py `MOODS`)

Every word is from the style bible's closed vocabulary (`mood_vocabulary`); free text resolves through each mood's
`words` (longest match wins, unknown words never map). A plan-07 brief's `palette_mood` builds a custom mood from the
same vocabulary (`mood_from_brief`). `python3 -B -m tools.mood_pack list` prints this table.

| mood | dominant (stone, roof, metal, ground, sky, wood) | support (foliage, cloth) | accent (glow, gate accent arc) | time | value key | extra | words |
|---|---|---|---|---|---|---|---|
| purple_dusk | purple | indigo | gold | dusk | low | | purple dusk, wizard purple, violet dusk, purple twilight, arcane dusk |
| ember_night | crimson | orange | amber | night | low | | ember night, ember, volcanic night, embers, ashen night |
| candy_pastel | pink | azure | yellow | afternoon | high | neutral pastel | candy pastel, candy, pastel, sugar, candyland |
| bone_white | yellow | amber | crimson | noon | high | neutral white | bone white, bone, ivory, bleached, ossuary |
| toxic_green | lime | emerald | magenta | night | low | | toxic green, toxic, acid, radioactive, swamp gas |
| frost_dawn | azure | teal | rose | dawn | mid | | frost dawn, frost, icy dawn, winter morning, frozen |
| golden_hour | amber | orange | crimson | golden_hour | mid | | golden hour, golden, sunset gold, warm evening |
| deep_sea | teal | blue | cyan | night | low | | deep sea, underwater, abyssal, sunken, ocean deep |

## Every shipped pack x every mood (derive_checked with look continuity)

`ok` = derived at full strength (0.85); `ok @s` = clamped to strength s (hue move and light curve eased) so every check
passes; `refused` = no strength passed (first reason shown). Regenerate with `python3 -B -m tools.mood_pack matrix`.

| base | bone_white | candy_pastel | deep_sea | ember_night | frost_dawn | golden_hour | purple_dusk | toxic_green |
|---|---|---|---|---|---|---|---|---|
| alien_world | refused: step: over-crisp texture (87% of strong edges step in one texel, max 8 | refused: step: over-crisp texture (87% of strong edges step in one texel, max 8 | ok @0.34 | ok @0.51 | ok @0.51 | ok | ok @0.68 | ok |
| ancient_ruins | ok | ok | refused: band: value structure changed (span 52% of base, keep 60-160%) | ok | refused: sky: crisper edges than the base texture (29% vs 1% one-texel steps) | ok | ok @0.51 | refused: sky: crisper edges than the base texture (29% vs 1% one-texel steps) |
| canyon_mesa | refused: water: crisper edges than the base texture (27% vs 15% one-texel steps | refused: water: crisper edges than the base texture (27% vs 15% one-texel steps | ok | ok @0.34 | ok | ok | ok | ok |
| castle_keep | ok @0.68 | ok @0.68 | ok | ok | ok | ok @0.51 | ok | ok |
| forest_village | refused: set median texture energy 0.051 > 0.050 | refused: set median texture energy 0.050 > 0.050 | ok | ok @0.51 | ok | ok | ok | ok |
| frontier_town | ok | ok | ok | ok @0.51 | ok | ok | ok | ok |
| frontier_town_golden | ok | ok | ok | ok @0.34 | ok | ok | ok @0.68 | ok |
| frontier_town_night | refused: water: crisper edges than the base texture (27% vs 15% one-texel steps | refused: water: crisper edges than the base texture (27% vs 15% one-texel steps | ok | refused: band: over-crisp / noisy texture (hf energy 0.181 > 0.180) | ok | ok | ok @0.68 | ok |
| jungle_temple | ok @0.51 | ok @0.51 | ok | ok | ok | ok | ok | ok |
| medieval_village | ok | ok | ok | ok | ok | ok @0.51 | ok | ok |
| medieval_village_dusk | ok | ok | ok @0.68 | ok | ok | ok @0.51 | ok | ok |
| medieval_village_night | ok @0.68 | ok | ok @0.68 | ok | ok | ok @0.51 | ok | ok |
| medieval_village_snow | ok @0.68 | ok | ok | ok | ok | ok @0.51 | ok | ok |
| polar_pod | refused: characters unreadable: skin vs ground OKLab distance 0.068 < 0.070 (ba | ok @0.51 | ok | ok @0.68 | ok @0.68 | ok @0.68 | ok | ok |
| space_station | ok @0.68 | ok | ok | ok | ok | ok | ok | ok |
| stone_dungeon | ok @0.51 | ok @0.68 | ok | ok | ok | ok | ok | ok |
| stone_dungeon_torchlit | ok | ok | refused: roof: crisper edges than the base texture (25% vs 4% one-texel steps) | ok | refused: roof: crisper edges than the base texture (25% vs 4% one-texel steps) | ok | ok @0.34 | ok |
