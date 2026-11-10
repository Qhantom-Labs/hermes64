# Style audit

`hermes64_check(project, action="audit", views=0-2)` renders the game in the real Godot window and scores every
room against the project's style lock. It returns per-room scores, a one-line summary, a compact contact sheet,
typed fix hints and a `next` list of exact tool calls (see [AUTOREPAIR.md](AUTOREPAIR.md)). It measures numbers;
it never claims human art approval (`human_approval: null`). Code: `adventure_maker/audit.py`; render harness:
`runtime/godot/tests/audit_main.tscn` (`audit_capture.gd` extends `main.gd`, so the ordinary capture is unchanged).

## Views

For each room: the default camera (the room's `presentation.camera`) with the room's characters placed, plus up
to `views` extra authored cameras (default 1). Each view is the internal 320×240 frame, UI hidden. The default view
also gets the existing gate passes (key, depth, region mask, classic-lighting, no-glow) and a mesh inventory:
triangles, surfaces (draw-call estimate), cuboid boxes, surfaces with neither texture nor vertex colour, and per-actor
triangles and in-frame flags. Teleported initial state: visual coverage, not a playthrough.

## Style lock

The selected pack snapshot (`metadata.hermes64_pack` id + sha256): `view.json` `style_gate` thresholds over
`style_gate.CORE_DEFAULTS`, `pack.json` budgets (`room_tris`, `character_tris`), the palette, the
`kits/core/n64_look.json` fidelity thresholds and the kit pack's texel-density table.

## Checks

| Check | Measure | Severity |
|---|---|---|
| flatness / contrast | 3×3 near-uniform share; luma p95−p5 | error |
| value range | p2 darks, p99.5 highlights, mean exposure | warn |
| fog | share of pixels within 0.07 of the fog colour | error |
| palette / accent | hue-family adherence to the palette; accent share | error / warn |
| depth separation | p90−p10 camera distance over drawn non-sky pixels (min 1.5 m); a depth pass at one value under a structured frame is reported as unreadable | error / warn |
| void, doors, camera, floating, exterior | existing room-look gate (cutaway void, free-standing doors, camera outside the shell, sky/haze/bands/ground/landmark) | error |
| triangles / draws | room total vs `room_tris`; surfaces vs 256 | error / warn |
| cuboid placeholder | magenta MISSING boxes, unknown piece/prop/floor assets, module marker boxes | error |
| untextured | surfaces with no texture and no vertex colour | error |
| character budget / framing / binding | actor triangles vs `character_tris`; characters out of frame; placeholder bodies | warn |
| N64 fidelity | modern light, glow, clipping, neon, crisp edges, nearest upscale, fog-horizon tint | warn |
| material kinds, texel density | runtime material kinds outside the N64 set; density spread per class | warn |
| look colours (static) | room `look` colours outside the palette hue families | error |

Extra views run the frame checks too. Static checks (asset/character bindings, look colours) also run with no
display; the rendered part then reads `style audit: not run (no display)`.

## Score and status

Each room starts at 100: −25 per error, −6 per warning (floor 0). FAIL if any error, WARN if only warnings, PASS
otherwise. Overall = mean room score minus 25 per global error and 2 per global warning. Deterministic for the
same captures.

## Outputs

Tool result (short): `status`, `score`, `summary` (e.g. `style audit FAIL 6/100: 0/2 rooms pass; fails: room_a
void/doors/camera`), per-room findings, `next`, `manual`, `contact_sheet`, `report_path`. Full report with metrics
and ops: `.maker/runs/audit-*/audit.json`. Contact sheet: 160×120 thumbnails with a status bar (green/amber/red)
and `room score` label; no text bubbles.

## /hermes64 new and the badge

After the playtest, `/hermes64 new` runs the audit when a window can open (macOS GUI session; `HERMES64_DISPLAY=0`
forces off), otherwise records `style audit: not run (no display)`. The badge's style slot shows it:
`style audit WARN 94/100`, `style audit FAIL 6/100 (2/2 rooms)` or `style audit not run (no display)`. A failing
audit keeps `ok` false, like a failing style gate, and the result carries its `next` steps.
