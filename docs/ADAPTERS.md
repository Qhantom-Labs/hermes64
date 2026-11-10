# Assembled component adapters

The root is one trusted bundle, not a collection of shell-generated fixture responses. All production child processes pass through `Runner`: fixed argv lists, no shell, stdin closed, bounded output/deadlines, scrubbed env, project-local HOME/temp/cache and macOS no-network/outside-write sandbox. A configured missing engine fails explicitly; it is never downloaded or replaced by fabricated output.

## Story

`python3 -B -m story` runs from the trusted bundle root (not an untrusted game cwd). The CLI contracts remain:

- `compile SPEC -o GAME`
- `check GAME --max-states N --report REPORT`
- `edit SPEC move-entrance --room ID --door ID --wall WALL --position N --out-dir DIR`
- `edit SPEC change-role --character ID --role ID --out-dir DIR`
- `edit SPEC add-ending --ending PAYLOAD --out-dir DIR`
- `migrate SAVE --from-game OLD --to-game NEW -o OUT --report REPORT [--manifest MANIFEST]`

Strict JSON stdout, exit/status agreement and report-file agreement are checked. Named edit output is independently recompiled and checked before promotion. Unproved/inconclusive results, identity changes, locality failure and rejected supplied-save migrations cannot replace the current revision. Expected changed-room sets must match **exactly**, not merely contain observed changes.

## KITS 3.1

`kits/manifest.json` is the relocated measured derivative of the source manifest, retaining original hashes. The original copy is `kits/library/manifest.json`. The real path is `assets_v3.py`:

```text
BLENDER --background --factory-startup --disable-autoexec --python BUNDLE/kits/build.py -- --id KIT --pack RECIPE --params JSON --seed N --out PROJECT/.maker/cache/assets/HASH.glb --tex-dir PROJECT/.maker/cache/textures
```

It builds default floor/wall modules and requested pack presets, caches by input/generator/pack/conversion bytes, checks builder validation and SHA-256, independently counts triangles, and converts colours to explicit sRGB8. Immutable bundled semantic variants are verified and reused. Real same-seed cache reuse is asserted by the integration harness. Cache reuse is not an independent claim of Blender byte determinism across machines or versions.

The legacy KITS 2.0 branch is retained only for the historical negative boundary suite. Its synthetic transport tests are labeled and **not used by the assembled 3.1 integration**. Its unmeasured style result remains partial.

## Godot proof replay

Each call copies a bounded trusted runtime template into a fresh project-owned operation directory and writes exact game, bindings, theme and audio snapshots. The normalized seam now exists:

```text
GODOT --headless --path COPY --script res://tests/playthrough.gd -- --game GAME --proof PROOF --report REPORT [--save MIGRATED_SAVE]
```

`playthrough.gd` extends the original proof consumer and drives the same gameplay runtime used by presentation. It checks the proof hash/status, reaches every claimed ending/collectible witness, writes actual disk saves and loads them into fresh runtime instances. Optional migrated-save input must load successfully in Godot. Reports bind game hash, exact ending keys, witness/step/failure counts and save results. Missing/malformed/mismatched reports or nonzero child exits fail.

The old positional `tests/replay.gd` remains an independent trace/oracle test API; it was not silently renamed as if the protocols matched.

## GUI and screenshots

```text
GODOT --path COPY -- --game=GAME --pack=THEME --bindings=BINDINGS --quit_after=SECONDS [--screens=DIR]
```

Default renderer is Mobile/Metal. `screenshots:true` visits every room for **visual coverage**, waits for real rendered frames, writes full-window and 320×240 captures plus a report, then exits. It explicitly teleports initial story state for room coverage; this is not called a reachability playthrough. The separate proof replay establishes abstract path acceptance.

`open` returns false on script/engine errors, missing screenshot reports, over-budget rooms or unresolved assets. A successful capture or normal GUI exit still does not certify human playability. No detached process survives the call.

## Benchmark

An explicit list of 1–20 validated operations is applied to private candidate revisions. Each row separately reports compiled validity, exact changed/unchanged room hashes and canonical bytes, preserved identities, current solvability, supplied-save migration, measured asset validation and Godot replay/loading of that migrated save. Missing dimensions cannot pass. The exact live source/game pointer bytes are compared before/after; the benchmark does not promote candidates. Asset cache snapshots may advance independently and are revalidated against the selected pack.

The shipped acceptance list is E1 workstation entrance → north wall/position 2, E2 Neri → authored saboteur role, E3 supplied Shared Glow ending. Five other rooms remain byte-identical for each edit. These are measured examples, not proof that arbitrary natural-language edits work.

## Limits

Story children: 90 seconds; engine children: at most 180 seconds. GUI allows requested time plus startup/capture margin, bounded by 180 seconds. Combined child output ≤1 MiB, JSON ≤1 MiB/48 levels/50,000 nodes, tool response ≤24,000 bytes with full report dereference, runtime copy ≤1,000 files/32 MiB, project audit ≤10,000 entries. Existing roots only; traversal, symlinks, hardlinks and special files reject. Reads are not confidential. No live Hermes/catalog validation is implied.
