# Western kit texture-energy failures (owner decision; no threshold changed)

The gen_tools library gate (`kits/core/look.py`, `hf_energy_median_max` 0.05 and per-texture `hf_energy_max` 0.18 in
`kits/core/n64_look.json`) refuses rebuilt copies of many western pieces. The create flow then uses each shipped
pack's own hash-pinned binding as-is and says so per piece (ORCH behaviour, unchanged). This file lists the affected
pieces and one tested candidate data patch. **Nothing here was applied to the kit, the packs or the thresholds.**

Measured on the orch2 package (`f1d4fd19`), Python builder, `gen_tools.build(..., 'frontier_town', seed=7)` for every
`wprop.*`, `wtown.*`, `wland.*`, `wrail.*`, `wmine.*` generator (79 pieces). Receipts:
`evidence/orch2/western-tex.json` (now) and `evidence/orch2/western-soften-A.json` (candidate patch A).

## Now: 40 of 79 western pieces fail, all on "set median texture energy" (0.052 to 0.142 > 0.050)

The cause is in the pack textures, not the meshes: 20 of 51 frontier_town texture roles are above 0.05 on their own
(medieval packs: 15 of 51, pack medians 0.044-0.045). The largest: `paper` 0.196, `band` 0.174, `wall` 0.158
(`wk_clapboard`, 14 boards), `cap` 0.142, `roof` 0.139 (`wk_shingle`, 14 rows), `stone` 0.136 (`wk_brick`, 10 rows),
`step` 0.135 (`wk_deck`), `ice` 0.118, `door` 0.099 (`wk_door`). The medieval equivalents carry `"soften": 1` and fewer
rows/boards at half the texture size; the western `wk_*` materials have no `soften`.

## Candidate patch A (tested in a disposable copy only)

Data only, in `kits/packs/{frontier_town,frontier_town_golden,frontier_town_night,canyon_mesa}/pack.json`: for each
texture role over 0.05, raise `materials.<role>.texture.soften` by one per pass, at most 3 passes / level 3.

| piece | median hf now | after patch A |
|---|---:|---|
| wland.arch, wland.butte, wland.canyon_wall, wland.hoodoo, wland.ledge, wland.mesa, wland.slope | 0.062 | passes |
| wland.boulder, wmine.cart, wmine.ore_pile, wprop.tombstone | 0.065 | passes |
| wmine.headframe, wrail.station, wtown.bank, wtown.sheriff | 0.063 | passes |
| wland.scrub, wprop.barrel, wprop.crate, wprop.trough, wtown.hotel, wtown.saloon, wtown.shack, wtown.store | 0.052 | passes |
| wprop.campfire | 0.057 | passes |
| wprop.wagon | 0.055 | passes |
| wprop.bottles | 0.057 | 0.055 |
| wprop.cactus | 0.142 | 0.059 |
| wprop.lantern, wprop.stove, wrail.trestle | 0.063 | 0.064 |
| wprop.saloon_doors, wrail.car | 0.099 | 0.057 |
| wprop.wheel, wrail.handcar | 0.118 | 0.064 / 0.057 |
| wprop.windmill, wtown.church, wtown.water_tower | 0.063 | 0.052 |
| wtown.facade | 0.099 | 0.052 |
| wrail.locomotive, wrail.signal | 0.063 | **new failure:** `band` per-texture hf 0.220 > 0.180 |

Result: 40 failing -> 15 failing. Softening raises `band` (0.174 -> 0.220, over the per-texture maximum) and does not
lower `metal` (0.063 -> 0.064) or `fire`; those generators need a different change.

| role (frontier_town) | hf now | soften level after A | hf after A |
|---|---:|---:|---:|
| paper | 0.196 | 3 | 0.050 |
| band | 0.174 | 3 | 0.220 |
| wall | 0.158 | 3 | 0.052 |
| cap | 0.142 | 3 | 0.059 |
| roof | 0.139 | 3 | 0.059 |
| stone | 0.136 | 2 | 0.043 |
| step | 0.135 | 3 | 0.057 |
| ice | 0.118 | 3 | 0.047 |
| door | 0.099 | 3 | 0.057 |
| hull_alt | 0.091 | 3 | 0.052 |
| book | 0.081 | 1 | 0.040 |
| ceiling | 0.074 | 1 | 0.048 |
| rock | 0.065 | 1 | 0.048 |
| metal | 0.063 | 3 | 0.064 |
| cliff | 0.062 | 1 | 0.034 |
| fire | 0.057 | 3 | 0.056 |
| hull | 0.055 | 2 | 0.036 |
| body_alt, foliage, screen | 0.052 | 1-2 | 0.035-0.044 |

## Proposed owner change (for the western kit owner to decide)

1. Apply patch A for the roles where it lands at or under 0.05 without side effects (`paper`, `stone`, `ice`, `book`,
   `ceiling`, `rock`, `cliff`, `hull`, `body_alt`, `foliage`, `screen`), and leave `band` unsoftened.
2. For `wall`, `roof`, `step`, `door`, `cap`, `hull_alt` (still 0.052-0.059 at soften 3) and `band`, `metal`, `fire`:
   lower the generator detail instead (fewer `boards`/`rows`, lower `joints`/`weather`/`wear`, or a 32 px texture like
   the medieval kit), then re-measure with `look.continuity`.
3. Rebuild and re-pin the shipped library GLBs of the four western packs (their `bindings.json` hashes change with
   the pack), re-run the western kit's own gates and goldens. Dylan judges the resulting look.

Until then the create flow keeps using the shipped western bindings as-is and names each one in the report.
