# SHIP integration handoff for Main

SHIP is additive to baseline `80d5236`. No story, character, visual/theme, existing public registry, or existing test file is modified. New native registration lives entirely in `adventure_maker/demo.py`; the three closed schemas are `SHIP_SCHEMAS`. CLI works without plugin activation. This lane does not install/enable a Hermes profile or publish anything.

## Exact merge wiring (not applied in this lane)

1. In root `__init__.py`, after the existing import:

```python
from .adventure_maker.demo import register_tools as register_ship_tools
```

Inside `register(ctx)`, immediately after `register_tools(ctx)`:

```python
    register_ship_tools(ctx)
```

2. In the `plugin.yaml` JSON `provides_tools` array, append exactly:

```json
"hermes64_playtest", "hermes64_export", "hermes64_demo"
```

No hooks, middleware, capabilities, environment requirements or new settings. Result: 16 tools on this baseline, subject to other lanes' additive tools. Do not overwrite their declarations.

3. **No edit to `adventure_maker/schemas.py` is required.** SHIP registration carries `SHIP_SCHEMAS` directly and uses the existing `validate`, `COMMON`, `obj` definitions. Do not simply merge them into the legacy `SCHEMAS`: the legacy service dispatcher does not route SHIP handlers. Call `demo.handle(settings, name, args)` for these three names. For schema introspection, combine the dictionaries in the caller without changing either registry.

4. Update the exact-count assertion in `tests/test_registration.py` from `13` to `16` when applying steps 1–2 (or account for additional lanes), and update the disclosure's existing tool count. The new isolated registration test exercises the additive public ctx surface without activation.

5. Append `docs/README-SHIP-FRAGMENT.md` to the appropriate README section; append `docs/DISCLOSURE-SHIP.md` to the existing disclosure and reconcile its old physical-navigation limitation. Include `skills/hermes64-playtest-and-ship/SKILL.md` as a bundled skill, not an installed profile mutation.

## Required files

- `adventure_maker/{playtest,export,demo}.py`
- `runtime/godot/playtest/{view,runner,script_error,release}.gd`
- `tools/{ship_probe,ship_templates,ship_web_smoke,ship_verify}.py`
- `tests/test_ship*.py`, `licenses/godot-4.6.2/{LICENSE,COPYRIGHT}.txt`
- This documentation and the new skill. Existing `tools/pngtool.py` is the trusted stdlib contact-sheet helper and must remain bundled.

Runtime staging already copies the Godot tree, so no adapter edit is necessary. Export staging includes only approved runtime directories and the release entry, not playtest error controls or source repo metadata.

## Acceptance after integration

```sh
/usr/bin/python3 -B -m unittest tests.test_ship tests.test_ship_native tests.test_registration -v
sh tools/verify_all.sh
```

Then rerun a real demo and export smoke on the **merged exact tree**. SHIP's receipts do not certify another lane's later visual/audio changes. Windows executable creation is never a Windows execution pass. All generated share bundles are local-only; public upload, catalog admission, signing identities and notarization remain separate owner decisions.

If the original verifier reaches its 180s plugin-suite cap after adding real native tests, retain that failed receipt. `python3 -B -m tools.ship_verify` runs the same six command bodies with a 300s plugin-suite wall cap, leaving each game process bound and every assertion intact. Its success is a separate extended-budget result, not permission to describe the original run as passed. No existing verifier source was modified.
