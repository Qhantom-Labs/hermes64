# WIN3 shared-file hunk index

Integration base: `aa569b4f`. Generated from the local diff; line ranges are candidate ranges, not stable API identifiers.
No runner opt-in, sandbox, proof, physical qualification, visual acceptance or numeric parity tolerance was changed.

## Semantic hunks

- host_compat.py: per-key legacy/canonical overlay and malformed-mapping guard.
- setup_check.py: PowerShell 5.1 dependency hint, truthful missing-storage row, setup result follows games-folder readiness.
- platforms.py / tools.py / tools/hermes64_setup.py: encoding-aware human display, Windows ctime advisory caveat, explicit standalone --projects-root.
- newgame.py / hub.py / service.py: ASCII-escaped JSON at transport boundary, canonical UTF-8 files/hashes unchanged. Existing 24000-byte transport cap applies to escaped wire bytes.
- safety.py: NTFS-reserved project ids rejected before creation.
- export.py: documentation-only key hint, Shift run / Alt precision.
- All other Python edits below: explicit UTF-8 text I/O, binary/ZIP/wave/descriptor I/O left binary.
- nbchars/PARITY.json: fingerprint refreshed only after real 37-file parity rerun; tolerances/verdict logic untouched.

## Shared-file ranges

| File | Hunks (-base +candidate) |
|---|---|
| `adventure_maker/export.py` | `-399 +399` |
| `adventure_maker/host_compat.py` | `-64 +64,3`; `-67,4 +69,6` |
| `adventure_maker/hub.py` | `-569 +569` |
| `adventure_maker/nbchars/PARITY.json` | `-13 +13` |
| `adventure_maker/nbchars/api.py` | `-197 +197`; `-235 +235`; `-250 +250`; `-302 +302` |
| `adventure_maker/nbchars/gen.py` | `-87 +87`; `-94 +94` |
| `adventure_maker/newgame.py` | `-533 +533` |
| `adventure_maker/platforms.py` | `-81,0 +82,10` |
| `adventure_maker/safety.py` | `-123,0 +124` |
| `adventure_maker/service.py` | `-69,3 +69,4` |
| `adventure_maker/setup_check.py` | `-74,5 +74,10`; `-95 +100,2`; `-254 +260` |
| `adventure_maker/static_preview.py` | `-121 +121` |
| `adventure_maker/tools.py` | `-129 +129,3`; `-177 +179,2` |
| `audio/thaw_audio/catalog.py` | `-78 +78` |
| `audio/thaw_audio/diagnostics.py` | `-157 +157` |
| `audio/thaw_audio/stock.py` | `-41 +41`; `-68 +68` |
| `audio/thaw_audio/stock_build.py` | `-18 +18` |
| `audio/thaw_audio/stock_catalog.py` | `-17 +17`; `-51 +51`; `-87 +87` |
| `audio/thaw_audio/stock_media.py` | `-27 +27`; `-87 +87` |
| `characters/gen/build.py` | `-136 +136`; `-149 +149` |
| `characters/gen/core/blender.py` | `-19 +19` |
| `characters/gen/core/roles.py` | `-39 +39` |
| `kits/build.py` | `-41 +41`; `-52 +52` |
| `kits/core/bake.py` | `-22 +22` |
| `kits/core/blendio.py` | `-218 +218` |
| `kits/core/pipeline.py` | `-154 +154` |
| `kits/core/texgen.py` | `-29 +29` |
| `kits/tools/controls.py` | `-117 +117`; `-120 +120`; `-287 +287`; `-290 +290`; `-305 +305` |
| `kits/tools/determinism.py` | `-22 +22`; `-112 +112` |
| `kits/tools/failsum.py` | `-11 +11` |
| `kits/tools/manifest.py` | `-41 +41`; `-54 +54`; `-134 +134`; `-140 +140`; `-151 +151` |
| `kits/tools/packcheck.py` | `-85 +85` |
| `kits/tools/rebuild.py` | `-29 +29`; `-58 +58` |
| `kits/tools/room.py` | `-93 +93`; `-121 +121`; `-128 +128` |
| `kits/tools/schemadump.py` | `-21 +21` |
| `kits/tools/sweep.py` | `-48 +48`; `-98 +98` |
| `kits/tools/verify_manifest.py` | `-18 +18`; `-50 +50` |
| `kits/tools/visdiff.py` | `-93 +93`; `-96 +96`; `-128 +128` |
| `refpack/blender_proof.py` | `-339 +339`; `-353 +353`; `-364 +364` |
| `refpack/build_library.py` | `-71,3 +71,3` |
| `refpack/calibrate_gens.py` | `-28 +28`; `-62 +62` |
| `refpack/measure.py` | `-10 +10`; `-37 +37` |
| `refpack/proof.py` | `-14 +14`; `-30 +30`; `-58 +58`; `-73 +73` |
| `refpack/tool.py` | `-217 +217` |
| `refpack/worker.py` | `-20 +20`; `-22 +22` |
| `tools/hermes64_setup.py` | `-23,0 +24`; `-36,0 +38`; `-41 +43`; `-43 +45`; `-45 +47`; `-51 +53` |
| `tools/import_characters.py` | `-62 +62`; `-234 +234` |
| `tools/roomlook.py` | `-178 +178`; `-181 +181`; `-187,2 +187,2`; `-206 +206`; `-218,2 +218,2`; `-221 +221`; `-227 +227`; `-230 +230`; `-266 +266`; `-288 +288`; `-292 +292` |
| `tools/win3_audit.py` | `-0,0 +1,53` |

## New lane-only files

`tests/test_win3.py`, `tools/win3_audit.py`, `tools/win3_kit_check.py`, `tools/win3_hunks.py`,
`tools/windows_pc_check.ps1`, the `docs/WIN3-*.md` handoff documents and `docs/win3-kit/` sources.
Existing tests adjusted only to supply a known games-folder fixture; the real missing-storage regression is now asserted.

The frozen demo and every other worktree remain read-only. Main owns composition/publication and native-PC signoff.
