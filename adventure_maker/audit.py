"""STYLE AUDIT: hermes64_check(action='audit') (docs/STYLE-AUDIT.md).

Renders a standard set of views of the user's game in the real Godot window (each room's default camera plus up
to `views` extra authored cameras, characters in frame), measures them against the project's style lock and
returns per-room scores, a plain-English summary, a compact contact sheet and typed fix hints with a `next` list
of exact tool calls (adventure_maker/repair.py). Static checks (asset/character bindings, look colours outside
the palette) also run without a display; the rendered part then reads "not run (no display)".

Style lock = the selected pack snapshot (metadata.hermes64_pack id + sha256): its view.json style_gate
thresholds over style_gate.CORE_DEFAULTS, pack.json budgets, the palette, kits/core/n64_look.json fidelity
thresholds and the kit pack texel density table. Measures numbers only; it never claims human approval.
Deterministic for the same captures (no clocks or randomness in measuring or scoring).
"""
import colorsys
import json
import os
from pathlib import Path
import subprocess
import sys

from . import style_gate, n64_gate, repair
from .repair import Builder, pointer, finding, index_of, nearest_asset
from .safety import fail

FORMAT = 'hermes64-style-audit/1'
WEIGHT = {'error': 25, 'warn': 6}
DRAW_BUDGET = 256          # same probe budget the playtest verdict uses
ROOM_TRIS = 6000           # runtime capture cap; pack thresholds.room_tris overrides
MATERIAL_KINDS = {'baked_unlit', 'chrome_env', 'emissive', 'face_atlas', 'glass_env', 'view_plane', 'water'}
DEPTH_SPREAD_MIN_M = 1.5   # p90-p10 camera distance over drawn non-sky pixels (calibration: docs/AUDIT-RESULT.md)
EXTERIOR_REASONS = ('no sky', 'flat sky', 'distance haze', 'near ground', 'depth layering', 'ground is', 'ground lacks',
                    'no landmark', 'exterior capture')
SCOPE = 'measured low-resolution renders (240 scanlines, aspect-aware width) vs the style lock; not human art approval'


def display_available():
    """(available, reason). A real window needs a macOS GUI (Aqua) session; HERMES64_DISPLAY=0 forces off."""
    forced = os.environ.get('HERMES64_DISPLAY')
    if forced == '0':
        return False, 'HERMES64_DISPLAY=0'
    if sys.platform == 'win32':
        # An interactive Windows desktop session (Hermes run by the signed-in person) can open a window;
        # a service (session 0) cannot. SESSIONNAME is Console or RDP-* for interactive sessions.
        session = os.environ.get('SESSIONNAME', '')
        return (bool(session), 'Windows desktop session (%s)' % session if session else 'no interactive Windows session')
    if sys.platform != 'darwin':
        return False, 'not macOS'
    try:
        name = subprocess.run(['/bin/launchctl', 'managername'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5,
                              stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, 'launchctl unavailable'
    return (name == 'Aqua'), ('GUI session' if name == 'Aqua' else 'no GUI session (%s)' % (name or 'unknown'))


def room_path(rid, *rest):
    return ('metadata', 'presentation', 'rooms', rid) + rest


# ---------------------------------------------------------------- style lock
def style_lock(root, spec, pack, theme=None):
    root = Path(root)
    base = pack['id'] if (root / 'packs' / pack['id'] / 'view.json').is_file() else pack['kit_pack_id']
    view = theme or json.loads((root / 'packs' / base / 'view.json').read_text(encoding='utf-8'))
    th = dict(style_gate.CORE_DEFAULTS)
    th.update(view.get('style_gate') or {})
    budgets = dict(pack.get('thresholds') or {})
    ref = (spec.get('metadata') or {}).get('hermes64_pack') or {}
    return {'pack': pack['id'], 'pack_sha256': ref.get('sha256'), 'kit_pack': pack['kit_pack_id'],
            'palette': list(view.get('palette_colors') or pack.get('palette') or []), 'gate': th, 'budgets': budgets,
            'n64': n64_gate.thresholds(view), 'room_tris': budgets.get('room_tris', ROOM_TRIS),
            'character_tris': budgets.get('character_tris', 700), 'view': view}


def known_assets(root, pack):
    root = Path(root)
    base = pack['id'] if (root / 'packs' / pack['id'] / 'bindings.json').is_file() else pack['kit_pack_id']
    keys = set(json.loads((root / 'packs' / base / 'bindings.json').read_text(encoding='utf-8'))['assets'])
    return keys | {'_floor', '_wall', ''}


def cast_rows(root):
    rows = []
    for rel in ('bindings.json', 'kits/bindings.json'):
        path = Path(root) / rel
        if path.is_file():
            rows += [r for r in json.loads(path.read_text(encoding='utf-8')).get('characters', []) if isinstance(r, dict)]
    return rows


# ---------------------------------------------------------------- colour helpers
def hex_rgb(value):
    v = value.lstrip('#')[:6]
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def nearest_palette(value, palette):
    rgb = hex_rgb(value)
    best = min(palette, key=lambda c: sum((a - b) ** 2 for a, b in zip(rgb, hex_rgb(c))))
    return '#' + best.lstrip('#')[:6].lower()


def on_palette(value, palette, tol=20.0):
    """Palette hue-family membership (the same rule the rendered gate uses), for authored look colours."""
    r, g, b = (x / 255.0 for x in hex_rgb(value))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    fam, neutral = style_gate.palette_families(palette)
    if v <= 0.10 or s < 0.12:
        return neutral or v <= 0.10
    return any(style_gate._hue_dist(h * 360.0, f) <= tol for f in fam)


def look_colours(value, trail=()):
    if isinstance(value, str) and value.startswith('#') and len(value) in (7, 9):
        yield trail, value
    elif isinstance(value, dict):
        for k in sorted(value):
            yield from look_colours(value[k], trail + (k,))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from look_colours(v, trail + (i,))


# ---------------------------------------------------------------- static checks (no display needed)
def static_findings(root, spec, pack, lock):
    out = []
    known = known_assets(root, pack)
    pres = ((spec.get('metadata') or {}).get('presentation') or {}).get('rooms') or {}
    anchors = (spec.get('metadata') or {}).get('collectible_prop_ids') or {}
    bound = {anchors.get(c['id'], c['id']) for c in spec.get('collectibles', []) if c.get('character')}
    for room in spec.get('rooms', []):
        rid = room['id']
        prow = pres.get(rid) or {}
        for i, piece in enumerate(prow.get('pieces') or []):
            ref = piece.get('asset', '')
            if ref not in known:
                pick = nearest_asset(ref, known - {'', '_floor', '_wall'})
                out.append(finding('missing_binding', 'rooms/%s/pieces/%d' % (rid, i),
                                   'room %s piece %r has no asset (draws a magenta cuboid): use %s' % (rid, ref, pick),
                                   _replace_piece(rid, ref, pick), room=rid, check='cuboid_placeholder'))
        floor = prow.get('floor')
        if isinstance(floor, str) and floor not in known:
            pick = 'terrain.patch' if 'terrain.patch' in known else '_floor'
            out.append(finding('missing_binding', 'rooms/%s/floor' % rid, 'room %s floor %r has no asset: use %s' % (rid, floor, pick),
                               lambda b, rid=rid, pick=pick: b.op('replace', pointer(*room_path(rid, 'floor')), pick), room=rid,
                               check='cuboid_placeholder'))
        for k, prop in enumerate(room.get('props', [])):
            if prop['id'] in bound and prop.get('asset') not in known:
                continue  # a collectible's character stands here; the runtime draws no prop for it
            if prop.get('asset') not in known:
                pick = nearest_asset(prop['asset'], known - {'', '_floor', '_wall'})
                pid = prop['id']
                out.append(finding('missing_binding', 'rooms/%s/props/%s' % (rid, pid),
                                   'room %s prop %s asset %r is missing (draws a cuboid): use %s' % (rid, pid, prop['asset'], pick),
                                   _replace_prop(rid, pid, pick), room=rid, check='cuboid_placeholder'))
        look = prow.get('look') or {}
        for trail, colour in look_colours(look):
            if lock['palette'] and not on_palette(colour, lock['palette'], lock['gate']['palette_hue_tol_deg']):
                pick = nearest_palette(colour, lock['palette'])
                out.append(finding('palette_drift', 'rooms/%s/look/%s' % (rid, '/'.join(map(str, trail))),
                                   'room %s look %s %s is outside the %s palette: set it to %s' % (rid, '.'.join(map(str, trail)), colour, lock['pack'], pick),
                                   lambda b, rid=rid, trail=trail, pick=pick: b.op('replace', pointer(*room_path(rid, 'look', *trail)), pick),
                                   room=rid, check='palette'))
    rows = cast_rows(root)
    for c in spec.get('characters', []):
        if not any(r.get('body_id') == c.get('body_id') and r.get('base_rig_id') == c.get('base_rig_id') and r.get('params') == c.get('params') for r in rows):
            pick = next((r for r in rows if r.get('body_id') == c.get('body_id') and r.get('public_release')), None) or \
                next((r for r in rows if r.get('public_release')), None)
            cid = c['id']
            out.append(finding('missing_binding', 'characters/' + cid,
                               'character %s has no matching body binding (shows a placeholder)%s' % (cid, ': bind it to ' + pick['character_id'] if pick else ''),
                               _bind_character(cid, pick) if pick else None, severity='warn', check='character_binding', route='compile'))
    return out


def _replace_piece(rid, ref, pick):
    def run(b):
        pieces = b.doc['metadata']['presentation']['rooms'][rid]['pieces']
        i = next(k for k, p in enumerate(pieces) if p.get('asset') == ref)
        b.op('replace', pointer(*room_path(rid, 'pieces', i, 'asset')), pick)
    return run


def _replace_prop(rid, pid, pick):
    def run(b):
        ri = index_of(b.doc['rooms'], rid)
        b.op('replace', pointer('rooms', ri, 'props', index_of(b.doc['rooms'][ri]['props'], pid), 'asset'), pick)
    return run


def _bind_character(cid, row):
    def run(b):
        i = index_of(b.doc['characters'], cid)
        c = b.doc['characters'][i]
        b.op('replace', pointer('characters', i, 'body_id'), row['body_id'])
        b.op('replace', pointer('characters', i, 'base_rig_id'), row['base_rig_id'])
        b.op('replace', pointer('characters', i, 'params'), row['params'])
        for role in sorted(c.get('role_profiles', {})):
            b.op('replace', pointer('characters', i, 'role_profiles', role), row['params'])
    return run


# ---------------------------------------------------------------- rendered measurement
def depth_spread(folder, row):
    """p10/p50/p90 camera distance (m) over drawn, non-sky pixels of the depth pass."""
    rid = row['id']
    dp = Path(folder) / row.get('depth', rid + '-depth.png')
    mp = Path(folder) / row.get('mask', rid + '-mask.png')
    if not dp.is_file():
        return None
    w, h, d = style_gate.read_png(dp)
    sky = style_gate.sky_mask(style_gate.read_png(mp)) if mp.is_file() else bytearray(w * h)
    scale = float(row.get('depth_scale_m', 120))
    raw = [d[3 * i] for i in range(w * h) if not sky[i] and d[3 * i] < 254]
    if len(raw) < 100:
        return {'p10': 0.0, 'p50': 0.0, 'p90': 0.0, 'spread_m': 0.0, 'drawn': len(raw), 'mode_share': 1.0}
    counts = {}
    for v in raw:
        counts[v] = counts.get(v, 0) + 1
    vals = sorted(v / 255.0 * scale for v in raw)
    p = lambda q: round(vals[int(q * (len(vals) - 1))], 2)
    return {'p10': p(0.1), 'p50': p(0.5), 'p90': p(0.9), 'spread_m': round(p(0.9) - p(0.1), 2), 'drawn': len(raw),
            'mode_share': round(max(counts.values()) / len(raw), 4)}


def frame_findings(rid, m, th, palette, view=None, exterior=False):
    """Findings from one frame's style_gate metrics (default view or an extra view)."""
    out, tag = [], ('' if view is None else ' (%s)' % view)
    where = 'rooms/%s%s' % (rid, '' if view is None else '/' + view)

    def add(ok, cls, check, says, sev='error'):
        if not ok:
            out.append(finding(cls, where, says, severity=sev, room=rid, check=check, view=view or 'default'))
    add(m['flat_fraction'] <= th['flat_fraction_max'], 'flat_room', 'flatness',
        'room %s%s is flat: %.0f%% near-uniform pixels (max %.0f%%)' % (rid, tag, 100 * m['flat_fraction'], 100 * th['flat_fraction_max']))
    add(m['contrast_range'] >= th['contrast_range_min'], 'flat_room', 'contrast',
        'room %s%s has low contrast: %.2f (min %.2f)' % (rid, tag, m['contrast_range'], th['contrast_range_min']))
    add(m['luma_p2'] <= th['black_point_max'], 'flat_room', 'value_range',
        'room %s%s has no real darks: p2 %.2f (max %.2f)' % (rid, tag, m['luma_p2'], th['black_point_max']), 'warn')
    add(m['luma_p995'] >= th['white_point_min'], 'flat_room', 'value_range',
        'room %s%s has no highlights: p99.5 %.2f (min %.2f)' % (rid, tag, m['luma_p995'], th['white_point_min']), 'warn')
    add(th['mean_luma_min'] <= m['luma_mean'] <= th['mean_luma_max'], 'flat_room', 'value_range',
        'room %s%s exposure %.2f outside %.2f-%.2f' % (rid, tag, m['luma_mean'], th['mean_luma_min'], th['mean_luma_max']), 'warn')
    if 'fog_swallowed_fraction' in m:
        add(m['fog_swallowed_fraction'] <= th['fog_swallowed_max'], 'fog_swallow', 'fog',
            'room %s%s: fog swallows %.0f%% of the frame (max %.0f%%)' % (rid, tag, 100 * m['fog_swallowed_fraction'], 100 * th['fog_swallowed_max']))
    add(th['edge_density_min'] <= m['edge_density'] <= th['edge_density_max'], 'flat_room', 'detail',
        'room %s%s detail (edge density %.2f) outside %.2f-%.2f' % (rid, tag, m['edge_density'], th['edge_density_min'], th['edge_density_max']), 'warn')
    if 'palette_adherence' in m and palette:
        add(m['palette_adherence'] >= th['palette_adherence_min'], 'palette_drift', 'palette',
            'room %s%s: only %.0f%% of pixels in the palette hue families (min %.0f%%)' % (rid, tag, 100 * m['palette_adherence'], 100 * th['palette_adherence_min']))
        add(m['accent_fraction'] <= th['accent_fraction_max'], 'palette_drift', 'accent',
            'room %s%s accent overuse %.0f%% (max %.0f%%)' % (rid, tag, 100 * m['accent_fraction'], 100 * th['accent_fraction_max']), 'warn')
    if view is None:
        vmax = th['void_fraction_max_exterior'] if exterior else th['void_fraction_max_interior']
        add(m['void_fraction'] <= vmax, 'flat_room', 'void',
            'room %s shows %.1f%% uncovered background (max %.1f%%)' % (rid, 100 * m['void_fraction'], 100 * vmax))
    return out


def rendered_findings(root, folder, spec, pack, lock):
    """Per-room rows (metrics + findings) from a capture folder written by tests/audit_main.tscn."""
    folder = Path(folder)
    cap = json.loads((folder / 'capture.json').read_text(encoding='utf-8'))
    views = json.loads((folder / 'audit-views.json').read_text(encoding='utf-8')) if (folder / 'audit-views.json').is_file() else {'rooms': []}
    extra = {r['id']: r for r in views.get('rooms', [])}
    theme = lock['view']
    th = lock['gate']
    gate = style_gate.gate_directory(folder, dict(theme, style_gate=th))
    fid = n64_gate.gate_folder(folder, theme)
    gate_rows = {r['id']: r for r in gate['rooms']}
    fid_rows = {r['id']: r for r in fid['rooms']}
    spec_rooms = {r['id']: r for r in spec.get('rooms', [])}
    pres = ((spec.get('metadata') or {}).get('presentation') or {}).get('rooms') or {}
    rows, global_findings = [], []
    for crow in cap['rooms']:
        rid = crow['id']
        g = gate_rows.get(rid, {})
        m = g.get('metrics') or {}
        audit = crow.get('audit') or {}
        exterior = bool(audit.get('exterior'))
        f = []
        if not m:
            f.append(finding('flat_room', 'rooms/' + rid, 'room %s has no clean capture' % rid, room=rid, check='capture'))
        else:
            f += frame_findings(rid, m, th, lock['palette'], None, exterior)
        # Geometry audit from the existing capture harness.
        if audit.get('floating'):
            f.append(finding('flat_room', 'rooms/' + rid, 'room %s has floating pieces: %s' % (rid, ', '.join(x['name'] for x in audit['floating'][:4])), room=rid, check='floating'))
        if audit.get('uncut_doors', 0):
            f.append(finding('flat_room', 'rooms/' + rid, 'room %s has %d free-standing door frame(s)' % (rid, audit['uncut_doors']), room=rid, check='doors'))
        cam = audit.get('camera') or {}
        if th.get('camera_inside_interior') and not exterior and cam and not cam.get('inside_bounds', True):
            f.append(finding('flat_room', 'rooms/' + rid, 'room %s camera is outside the room shell (cutaway framing)' % rid, room=rid, check='camera'))
        # Exterior composition (sky, haze, depth bands, ground, landmark) from the existing gate.
        for why in g.get('reasons', []):
            if why.startswith(EXTERIOR_REASONS):
                f.append(finding('flat_room', 'rooms/' + rid, 'room %s: %s' % (rid, why), room=rid, check='exterior'))
        ds = depth_spread(folder, crow)
        if ds is not None and ds['spread_m'] < DEPTH_SPREAD_MIN_M:
            textured = m.get('contrast_range', 0) >= th['contrast_range_min'] and m.get('flat_fraction', 1) <= th['flat_fraction_max']
            if ds.get('mode_share', 1.0) >= 0.95 and textured:
                # One depth value under a frame with real contrast and structure: the depth pass did not capture
                # this room (e.g. a material that skips the depth override). Report it; do not guess a fix.
                f.append(finding('flat_room', 'rooms/' + rid, 'room %s depth pass is unreadable (%d%% of pixels at one depth); depth separation not measured' % (
                    rid, round(100 * ds['mode_share'])), severity='warn', room=rid, check='depth'))
            else:
                f.append(finding('flat_room', 'rooms/' + rid, 'room %s has no depth separation: %.1f m between near and far (min %.1f m)' % (
                    rid, ds['spread_m'], DEPTH_SPREAD_MIN_M), room=rid, check='depth'))
        # Budgets.
        tris = int(crow.get('triangles', 0))
        if tris > lock['room_tris']:
            f.append(finding('over_budget', 'rooms/' + rid, 'room %s is %d triangles over the %d cap' % (rid, tris - lock['room_tris'], lock['room_tris']),
                             room=rid, check='triangles', measured=tris, limit=lock['room_tris'],
                             top=((crow.get('triangles_split') or {}).get('top') or [])[:10]))
        inv = (extra.get(rid) or {}).get('inventory') or {}
        if inv.get('surfaces', 0) > DRAW_BUDGET:
            f.append(finding('over_budget', 'rooms/' + rid, 'room %s draws %d surfaces (budget %d)' % (rid, inv['surfaces'], DRAW_BUDGET),
                             room=rid, check='draws', severity='warn', measured=inv['surfaces'], limit=DRAW_BUDGET,
                             top=((crow.get('triangles_split') or {}).get('top') or [])[:10]))
        markers = [c for c in inv.get('cuboids', []) if c['ref'].startswith('@')]
        for cub in [c for c in inv.get('cuboids', []) if not c['ref'].startswith('@')]:
            f.append(finding('missing_binding', 'rooms/%s/%s' % (rid, cub['name']), 'room %s draws a cuboid placeholder %s (%s)' % (rid, cub['name'], cub['ref']),
                             room=rid, check='cuboid_placeholder', ref=cub['ref']))
        if markers:  # runtime-drawn module markers (gate posts, landmarks, checkpoints): module art, not room data
            names = sorted({c['name'] for c in markers if not c['name'].startswith('@')})
            f.append(finding('missing_binding', 'rooms/%s/markers' % rid, 'room %s draws %d flat-colour cuboid module marker(s) (%s): module runtime art, no automatic fix' % (
                rid, len(markers), ', '.join(names) or 'boxes'), room=rid, check='cuboid_placeholder'))
        if inv.get('untextured_count', 0):
            names = sorted({u['ref'] for u in inv.get('untextured', [])})[:4]
            f.append(finding('missing_binding', 'rooms/' + rid, 'room %s has %d surface(s) with no texture or vertex colour: %s' % (rid, inv['untextured_count'], ', '.join(names)),
                             room=rid, check='untextured'))
        for actor in inv.get('actors', []):
            if actor['triangles'] > lock['character_tris']:
                f.append(finding('over_budget', 'rooms/%s/%s' % (rid, actor['node']), 'room %s %s is %d triangles (character budget %d, body + attachments)' % (
                    rid, actor['node'], actor['triangles'], lock['character_tris']), room=rid, check='character_budget', severity='warn'))
        protagonist = (spec.get('metadata') or {}).get('protagonist')
        wanted = [c for c in (spec_rooms.get(rid) or {}).get('character_ids', []) if c != protagonist]
        framed = [a for a in inv.get('actors', []) if 'in_frame' in a]
        if wanted and framed:
            if not any(a['in_frame'] for a in framed):
                f.append(finding('character_off_frame', 'rooms/' + rid, 'room %s: none of %s is in the camera frame' % (rid, ', '.join(wanted)),
                                 room=rid, check='characters', severity='warn'))
        # N64 fidelity tells (warn: the fidelity section is separate from the defect gate).
        for why in (fid_rows.get(rid) or {}).get('reasons', []):
            f.append(finding('palette_drift' if 'neon' in why else 'flat_room', 'rooms/' + rid, 'room %s N64 tell: %s' % (rid, why), room=rid,
                             check='n64_fidelity', severity='warn'))
        # Extra authored views.
        vrows = []
        for v in (extra.get(rid) or {}).get('views', []):
            p = folder / v['file']
            if p.is_file():
                vm = style_gate.image_metrics(style_gate.read_png(p), None, audit.get('fog_color'), lock['palette'], th)
                vf = frame_findings(rid, vm, th, lock['palette'], v['camera'], exterior)
                f += vf
                vrows.append({'camera': v['camera'], 'file': v['file'], 'flat': vm['flat_fraction'], 'contrast': vm['contrast_range'],
                              'palette': vm.get('palette_adherence'), 'findings': len(vf)})
        metrics = {k: m.get(k) for k in ('contrast_range', 'flat_fraction', 'edge_density', 'luma_p2', 'luma_p995', 'luma_mean',
                                         'fog_swallowed_fraction', 'palette_adherence', 'accent_fraction', 'void_fraction') if k in m}
        metrics.update(triangles=tris, surfaces=inv.get('surfaces'), depth=ds,
                       n64={k: v for k, v in ((fid_rows.get(rid) or {}).get('metrics') or {}).items() if isinstance(v, (int, float))})
        rows.append({'id': rid, 'exterior': exterior, 'camera': crow.get('camera'), 'views': vrows, 'metrics': metrics,
                     'findings': f, 'clean': crow.get('clean', rid + '-clean.png'),
                     'presentation_pieces': len((pres.get(rid) or {}).get('pieces') or [])})
    for kind, n in sorted((cap.get('material_kinds') or {}).items()):
        if kind not in MATERIAL_KINDS:
            global_findings.append(finding('palette_drift', 'materials/' + kind, 'material kind %r (%d) is outside the N64 material rules' % (kind, n),
                                           check='material', severity='warn'))
    for ref in cap.get('missing_assets') or []:
        global_findings.append(finding('missing_binding', 'assets/' + ref, 'asset %s did not load' % ref, check='missing_asset'))
    for cid, why in sorted((cap.get('placeholder_characters') or {}).items()):
        global_findings.append(finding('missing_binding', 'characters/' + cid, 'character %s shows a placeholder body (%s)' % (cid, why),
                                       check='character_binding', severity='warn'))
    try:
        lib = n64_gate.library_report(root, packs=[lock['kit_pack']])
        for why in lib.get('reasons', []):
            global_findings.append(finding('palette_drift' if 'noisy' in why else 'flat_room', 'pack/' + lock['kit_pack'], 'texel density/texture: ' + why,
                                           check='texel_density', severity='warn'))
    except (OSError, KeyError, ValueError):
        pass
    return rows, global_findings, cap


# ---------------------------------------------------------------- fixes for rendered findings
def attach_fixes(spec, rows, lock, known):
    """Give each rendered finding a typed, mechanically applicable fix where one exists."""
    pres = ((spec.get('metadata') or {}).get('presentation') or {}).get('rooms') or {}
    profiles = ((lock['view'].get('look') or {}).get('profiles') or {})
    for row in rows:
        rid = row['id']
        prow = pres.get(rid) or {}
        profile = profiles.get('exterior' if row['exterior'] else 'interior') or {}
        done = set()
        for f in row['findings']:
            if f.get('severity') != 'error' or '_fix' in f:
                continue
            check = f.get('check')
            if check == 'triangles' and 'over_budget' not in done:
                fix, says = drop_pieces(rid, prow, f.get('top') or [], f['measured'] - f['limit'])
                if fix:
                    f['_fix'], f['says'] = fix, f['says'] + ': ' + says
                    f['auto'] = True
                    done.add('over_budget')
            elif check in ('flatness', 'contrast', 'depth', 'detail') and 'flat' not in done and f.get('view') in (None, 'default'):
                f['_fix'], says = dress_room(rid, row, prow, known)
                f['says'] += ': ' + says
                f['auto'] = True
                done.add('flat')
            elif check == 'fog' and 'fog' not in done and profile.get('fog'):
                fog = dict(profile['fog'])
                fog['far'] = round(float(fog.get('far', 40.0)) * 1.5, 1)
                fog['max'] = round(min(float(fog.get('max', 0.5)), 0.5), 2)
                f['_fix'] = lambda b, rid=rid, fog=fog: (b.ensure(*room_path(rid, 'look')), b.op('add', pointer(*room_path(rid, 'look', 'fog')), fog))
                f['says'] += ': push the fog back (look.fog far %.0f m, max %.2f)' % (fog['far'], fog['max'])
                f['auto'] = True
                done.add('fog')
            elif check == 'palette' and 'palette' not in done:
                look = prow.get('look') or {}
                bad = [(t, c) for t, c in look_colours(look) if not on_palette(c, lock['palette'], lock['gate']['palette_hue_tol_deg'])]
                if bad:  # the static look-colour findings carry the snap fix; do not apply it twice
                    f['says'] += ': room look colours %s are off-palette (see the look colour fix)' % ', '.join(c for _, c in bad[:3])
                else:
                    f['says'] += ': off-palette pixels come from assets/materials, not room data (pack-level; no automatic fix)'
                done.add('palette')
            elif check == 'cuboid_placeholder' and f.get('ref'):
                pick = nearest_asset(f['ref'], known - {'', '_floor', '_wall'})
                if any(p.get('asset') == f['ref'] for p in prow.get('pieces') or []):
                    f['_fix'] = _replace_piece(rid, f['ref'], pick)
                    f['says'] += ': use %s' % pick
                    f['auto'] = True


def drop_pieces(rid, prow, top, over):
    """Remove the heaviest authored presentation pieces until the room is under its cap."""
    pieces = prow.get('pieces') or []
    cost = {}
    for name, ref, tris in top:
        cost[ref] = max(cost.get(ref, 0), int(tris))
    ranked = sorted(((cost.get(p.get('asset'), 0), i, p.get('asset')) for i, p in enumerate(pieces) if cost.get(p.get('asset'), 0) > 0), reverse=True)
    chosen, saved = [], 0
    for tris, i, ref in ranked:
        if saved >= over:
            break
        chosen.append((i, ref))
        saved += tris
    if not chosen or saved < over:
        return None, 'the cost is in the shell/cast, not authored pieces (no automatic fix)'
    assets = [ref for _, ref in chosen]

    def run(b):
        rows = b.doc['metadata']['presentation']['rooms'][rid]['pieces']
        for i in sorted((i for i, _ in chosen), reverse=True):
            if rows[i].get('asset') in assets:
                b.op('remove', pointer(*room_path(rid, 'pieces', i)))
    counts = {}
    for ref in assets:
        counts[ref] = counts.get(ref, 0) + 1
    names = ', '.join('%s x%d' % (k, v) if v > 1 else k for k, v in sorted(counts.items()))
    return run, 'drop %d piece(s): %s (~%d triangles)' % (len(assets), names, saved)


def dress_room(rid, row, prow, known):
    """Flat/low-contrast room: add value structure with original kit dressing (a lamp pool and floor detail)."""
    cam = None
    w = d = 10
    look_at = [w / 2.0, 0, d / 2.0]
    adds = []
    if row['exterior']:
        floor = 'terrain.patch' if 'terrain.patch' in known else None
        for asset, dx, dz in (('nature.rock', -2.5, 1.5), ('nature.bush', 2.0, 2.5), ('nature.tree', -3.5, -2.5)):
            if asset in known:
                adds.append(asset)
        says = 'raise terrain variation: floor %s plus %s' % (floor or 'unchanged', ', '.join(adds))
    else:
        floor = None
        for asset in ('furn.rug', 'furn.lamp', 'prop.vessel'):
            if asset in known:
                adds.append(asset)
        says = 'add value structure: %s near the camera target' % ', '.join(adds)

    def run(b):
        b.ensure(*room_path(rid))
        room = b.doc['metadata']['presentation']['rooms'][rid]
        cams = room.get('cameras') or []
        spec_room = next((r for r in b.doc['rooms'] if r['id'] == rid), None)
        gx, gz = (spec_room or {}).get('grid_size', [w, d])
        tx, tz = (cams[0]['look_at'][0], cams[0]['look_at'][2]) if cams else (gx / 2.0, gz / 2.0)
        if 'pieces' not in room:
            b.op('add', pointer(*room_path(rid, 'pieces')), [])
        offsets = [(-1.2, 0.8), (1.6, -0.6), (0.4, 1.4)] if not row['exterior'] else [(-2.5, 1.5), (2.0, 2.5), (-3.5, -2.5)]
        for asset, (dx, dz) in zip(adds, offsets):
            x = round(min(max(tx + dx, 0.6), gx - 0.6), 2)
            z = round(min(max(tz + dz, 0.6), gz - 0.6), 2)
            b.op('add', pointer(*room_path(rid, 'pieces', '-')), {'asset': asset, 'position': [x, 0, z], 'scale': [1, 1, 1], 'yaw': 15})
        if floor and room.get('floor') != floor:
            b.op('add', pointer(*room_path(rid, 'floor')), floor)
    return run, says


# ---------------------------------------------------------------- scoring + summary
def score_rows(rows, global_findings):
    for row in rows:
        errs = sum(1 for f in row['findings'] if f.get('severity') == 'error')
        warns = sum(1 for f in row['findings'] if f.get('severity') != 'error')
        row['score'] = max(0, 100 - WEIGHT['error'] * errs - WEIGHT['warn'] * warns)
        row['status'] = 'FAIL' if errs else ('WARN' if warns else 'PASS')
    g_err = sum(1 for f in global_findings if f.get('severity') == 'error')
    g_warn = len(global_findings) - g_err
    overall = round(sum(r['score'] for r in rows) / len(rows)) if rows else 0
    overall = max(0, overall - WEIGHT['error'] * g_err - 2 * g_warn)
    status = 'FAIL' if g_err or any(r['status'] == 'FAIL' for r in rows) else (
        'WARN' if g_warn or any(r['status'] == 'WARN' for r in rows) else 'PASS')
    return overall, status


def summary(rows, overall, status, global_findings, rendered=True):
    """One plain line: status, score, rooms passing, and the failing checks per room (no prose bubbles)."""
    if not rendered:
        return 'style audit: not run (no display)'
    fails = []
    for r in rows:
        checks = []
        for f in r['findings']:
            if f.get('severity') == 'error' and f.get('check') not in checks:
                checks.append(f.get('check'))
        if checks:
            fails.append('%s %s' % (r['id'], '/'.join(checks[:4])))
    text = 'style audit %s %d/100: %d/%d rooms pass' % (status, overall, sum(1 for r in rows if r['status'] != 'FAIL'), len(rows))
    if fails:
        text += '; fails: ' + '; '.join(fails[:4]) + ('; ...' if len(fails) > 4 else '')
    return text


# ---------------------------------------------------------------- contact sheet (compact, no text bubbles)
def contact_sheet(folder, rows, out, cols=3):
    from .golden import write_png
    from .cover_font import small_mask
    folder = Path(folder)
    cw, ch, pad, bar = 160, 120, 4, 9
    n = max(1, len(rows))
    W = pad + cols * (cw + pad)
    H = pad + ((n + cols - 1) // cols) * (ch + bar + pad)
    px = bytearray(bytes((14, 14, 18)) * (W * H))
    colours = {'PASS': (80, 190, 110), 'WARN': (230, 180, 60), 'FAIL': (225, 70, 60)}
    for k, row in enumerate(rows):
        x0 = pad + (k % cols) * (cw + pad)
        y0 = pad + (k // cols) * (ch + bar + pad)
        p = folder / row['clean']
        if p.is_file():
            w, h, rgb = style_gate.read_png(p)
            for y in range(ch):
                sy = min(h - 1, y * h // ch)
                for x in range(cw):
                    sx = min(w - 1, x * w // cw)
                    o = 3 * ((y0 + y) * W + x0 + x)
                    i = 3 * (sy * w + sx)
                    px[o:o + 3] = rgb[i:i + 3]
        col = colours.get(row.get('status'), (120, 120, 120))
        for y in range(y0 + ch, y0 + ch + bar):
            for x in range(x0, x0 + cw):
                px[3 * (y * W + x):3 * (y * W + x) + 3] = bytes(col)
        label = ('%s %d' % (row['id'], row.get('score', 0)))[:39]
        mw, mh, mask = small_mask(label)
        for y in range(mh):
            for x in range(min(mw, cw - 2)):
                if mask[y * mw + x]:
                    o = 3 * ((y0 + ch + 2 + y) * W + x0 + 2 + x)
                    px[o:o + 3] = b'\x10\x10\x14'
    write_png(out, (W, H, bytes(px)))
    return out


# ---------------------------------------------------------------- tool entry
def render(settings, project, game, folder, views):
    from .adapters import Components
    from .runner import locate
    c = Components(settings, project)
    exe = locate('godot', settings.get('godot_path', ''))
    c.shipped('runtime/godot/tests/audit_main.tscn')
    runtime = c.prepare_runtime(game, folder)
    screens = project.path(folder + '/screens')
    argv = [exe, '--path', str(runtime), 'res://tests/audit_main.tscn', '--', '--game=' + str(project.path(game)),
            '--pack=' + str(runtime / 'theme.json'), '--bindings=' + str(runtime / 'bindings.json'),
            '--screens=' + str(screens), '--audit_views=' + str(views)]
    process = c.runner.run(argv, project.root, timeout=180)
    project.write_json(folder + '/audit.process.json', dict(process, argv=argv))
    if not (screens / 'capture.json').is_file():
        fail('audit_render', 'Godot wrote no audit capture (exit %s): %s' % (process['returncode'], process['stderr'][-600:]))
    return folder + '/screens', json.loads((runtime / 'theme.json').read_text(encoding='utf-8'))


def measure(root, spec, pack, folder=None, theme=None, rendered=True):
    """Full audit dict from a capture folder (or static-only when folder is None). Pure function of its inputs."""
    lock = style_lock(root, spec, pack, theme)
    known = known_assets(root, pack)
    static = static_findings(root, spec, pack, lock)
    rows, global_findings, cap = ([], [], {})
    if folder is not None:
        rows, global_findings, cap = rendered_findings(root, folder, spec, pack, lock)
        attach_fixes(spec, rows, lock, known)
    for f in static:  # static findings join their room row (or the global list)
        row = next((r for r in rows if r['id'] == f.get('room')), None)
        (row['findings'] if row else global_findings).append(f)
    overall, status = score_rows(rows, global_findings)
    if folder is None:
        status = 'FAIL' if any(f.get('severity') == 'error' for f in global_findings) else 'not_run'
    return {'format': FORMAT, 'status': status if folder is not None else status, 'rendered': folder is not None,
            'score': overall if folder is not None else None, 'rooms': rows, 'global': global_findings,
            'lock': {k: lock[k] for k in ('pack', 'pack_sha256', 'kit_pack', 'room_tris', 'character_tris')},
            'summary': summary(rows, overall, status, global_findings, folder is not None) if folder is not None else
            'style audit: not run (no display)' + ('; static check found %d problem(s)' % len(global_findings) if global_findings else ''),
            'engine': cap.get('engine'), 'display': cap.get('display'), 'scope': SCOPE}


def compact(report, folder_rel=None):
    """Short tool-result view: per-room score/status and finding one-liners."""
    rooms = [{'id': r['id'], 'score': r['score'], 'status': r['status'],
              'findings': [{'class': f['class'], 'check': f.get('check'), 'severity': f.get('severity', 'error'), 'says': f['says'], 'auto': f.get('auto', False)}
                           for f in r['findings']][:8]} for r in report['rooms']]
    out = {'status': report['status'], 'score': report['score'], 'summary': report['summary'], 'rooms': rooms,
           'global': [{'class': f['class'], 'severity': f.get('severity', 'error'), 'says': f['says']} for f in report['global']][:8],
           'lock': report['lock'], 'scope': report['scope'], 'human_approval': None}
    return out


def run(service, project, args):
    """hermes64_check(action='audit'): render when a display exists, measure, plan fixes, write reports."""
    from .packs import Packs
    current = service.current(project)
    spec = project.read_json(current['spec'])
    pack = Packs(service.settings, project).selected(spec)
    root = Path(service.settings.get('bundle_root') or Path(__file__).resolve().parents[1])
    folder = service.folder(project, 'audit')
    ok_display, why = display_available()
    screens = theme = None
    if ok_display:
        screens, theme = render(service.settings, project, current['game'], folder, args.get('views', 1))
    report = measure(root, spec, pack, project.path(screens) if screens else None, theme)
    proof = project.read_json(current['game']).get('game_hash')
    report['game_hash'] = proof
    report['display'] = report.get('display') or ('none: ' + why)
    findings = [f for r in report['rooms'] for f in r['findings']] + report['global']
    pre = []
    shell_checks = {'void', 'doors', 'camera', 'exterior'}
    if not project.path('.maker/assets/current.json').is_file() and any(
            f.get('check') in shell_checks and f.get('severity') == 'error' for f in findings):
        # Cutaway void, free-standing doors and outside cameras come from rooms built without their shells.
        pre.append({'tool': 'hermes64_build_assets', 'args': {'project': project.root.name, 'seed': 7},
                    'why': 'build the room shells/yards (cutaway void, free-standing doors, camera outside the shell)'})
        for f in findings:
            if f.get('check') in shell_checks:
                f['says'] += ': room shells are not built (hermes64_build_assets)'
                f['auto'] = True
            elif f.pop('_fix', None) is not None:  # re-measure after the build before dressing rooms
                f['auto'] = False
                f['deferred'] = 'after hermes64_build_assets'
    elif project.path('.maker/assets/current.json').is_file() and not (theme or {}).get('shells'):
        for f in findings:  # assets are built, yet the pack has no interior shells to build: kit work, not room data
            if f.get('check') in shell_checks and f.get('severity') == 'error' and not f.get('_fix'):
                f['says'] += ': pack %s builds no room shells (kit/pack work; no automatic fix)' % pack['id']
    planned = repair.plan(project.root.name, spec, current['spec'], audit_findings=findings,
                          proved=proved_now(service, project, current), pre=pre,
                          then=[{'tool': 'hermes64_check', 'args': {'project': project.root.name, 'action': 'audit'},
                                 'why': 're-measure the style audit'}])
    for r in report['rooms']:
        for f in r['findings']:
            f.pop('_fix', None)
    for f in report['global']:
        f.pop('_fix', None)
    sheet = None
    if screens:
        sheet = folder + '/contact-sheet.png'
        contact_sheet(project.path(screens), report['rooms'], project.path(sheet))
    report['contact_sheet'] = sheet
    project.write_json(folder + '/audit.json', report)
    result = compact(report)
    result.update(ok=report['status'] in ('PASS', 'WARN'), action='audit', report_path=folder + '/audit.json',
                  contact_sheet=sheet, next=planned['next'], manual=planned['manual'], fix_classes=planned['classes'])
    if not ok_display:
        result['ok'] = report['status'] != 'FAIL'
    return result


def proved_now(service, project, current):
    """True when the newest check report for this build proves it (cheap: no re-check)."""
    game_hash = project.read_json(current['game']).get('game_hash')
    runs = sorted(project.path('.maker/runs').glob('check-*/proof.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in runs[:5]:
        try:
            proof = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if proof.get('game_hash') == game_hash:
            return proof.get('status') == 'proved'
    return False
