# Texture slots example: a heraldic crest

Non-demo example of texture slots (docs/SLOTS.md) on the medieval packs (castle_keep, medieval_village*):

- `textures/slots.json` fills `banner_crest` (the cloth of `cst.banner`) with a tower-and-key crest. Copy it to a
  project's `textures/slots.json`; it is part of the game and ships in every export.
- `overlay/` fills `banner_crest_cross` (the `cst.banner__cross` preset) with a guild mark. Copy the folder to a
  project's `overlay/`; it is applied at build and export, reported in `slots-report.json`, and left out (with a
  leak check) by a neutral export.

Preview a recipe: `python3 -B -m tools.mask_preview overlay/textures/banner_crest_cross.mask.json --pack medieval_village --slot banner_crest_cross --out crest.png`
