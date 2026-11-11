# INTEG5 export repeatability investigation

## Initial reproduction (M11 merge head `ec5e74ec`)

Two actual `hermes64_export` web calls exported the **same** penguin project without any source edit, through `demo.handle`. Both completed and passed their ordinary privacy scan. Full file inventory, lengths and SHA256 pairs: `early-export/export-comparison.json` in the compressed diagnostic receipts. The original spec SHA256 remained equal.

Exactly four paths differ in `share/`:

- `web/index.pck`: 2,920,524 bytes each; first `b1ca9d0f3d5ab0d236d34bbbf96df52b8e6f27637fe7cb3a7b2edff7b0a6dfec`; second `f87a4819a287a87709d4e28589b5e3128e39d7be66e720de630188680039abaf`.
- `web/FILES.json`: downstream inventory of that PCK.
- `web.zip`: downstream archive containing the PCK and inventory.
- `FILES.json`: downstream inventory containing the changed target archive/inventory/PCK.

No JS, WASM, texture, game JSON or notice payload differed. This is not a timestamp-only ZIP mismatch.

## PCK-level diagnosis

The read-only v3 PCK table inspector verifies each member's stored MD5 against its actual payload, then computes SHA256. **153 members** each. Exactly one differs:

`.godot/exported/133200997/export-3070c538c03ee49b7677ff960a3f5195-main.scn` (677 bytes), first SHA256 `309f4d44b1eb1858e4c4fa1c91f1e5f9dcbf73aa4a8819d560d0097f4940ed96`, second `851020132bbe7e1017937ea091262039c85e92f9329bb4c139b130825087b066`.

Across the whole PCK, 19 bytes differ: four bytes in the binary scene's serialized `node_ids` array, plus the corresponding directory MD5 bytes. This identifies the engine-generated binary conversion of our single-node `main.tscn`, not gameplay RNG or project build IDs.

## Bounded candidate, not yet applied

The installed official Godot binary contains the setting `editor/export/convert_text_resources_to_binary`. In two independent scratch release copies, setting it to `false` keeps the authored text scene instead of generating the randomized binary scene. Both import/export processes exit 0 with no script errors; all seven engine-produced web files match exactly, including PCK SHA256 `c1ab517870eec621e387cebe5cd6f10af844c439819cde02a9b9f1422177ea10`.

This is an owned export-configuration candidate, not a binary/PCK hash rewrite, generated-resource mutation or acceptance exemption. Ordinary release closure, engine hash/version, proof and privacy checks remain required. The candidate is not yet production code, has not been tested on final stack A, and does not establish native-target or cross-Godot/OS repeatability.
