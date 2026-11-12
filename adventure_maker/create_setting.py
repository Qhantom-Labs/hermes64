"""Derived setting packs for the create flow (lane STYLEGEN-1, docs/STYLEGEN-PLAN.md section 2).

An off-catalogue setting (a moon, a sea floor) is built in the Hermes64 look from the nearest reference pack: its
structure (kit room compiler and calibrated create patterns) and its thresholds stay; its surface is recoloured by the
existing mood derivation (tools.mood_pack.derive_all with the kits/core/mood.py checks, unchanged); the pieces the
setting's room patterns need and the reference does not bind are built in the derived palette by the existing install
path. Then the normal create stages, audit, style gate and N64 gate run against that pack with the same thresholds.

The create flow asks this module only when its tag-scored pack choice would refuse the brief or would pick a pack that
does not cover the brief's genre at all (create_flow.stage_style). Routing reads the brief through a data table
(create_setting.json), never prompt text: deterministic, first matching row wins. A reference is skipped when no
create room pattern covers it; a refused derivation falls through to the next reference with a report line; with no
usable reference the caller keeps its honest refusal. Nothing here loosens a threshold or edits a shipped pack.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

TABLE = Path(__file__).with_name('create_setting.json')
FORMAT = 'hermes64-create-setting/1'
ID_VERSION = 1


def load(path=None):
    doc = json.loads(Path(path or TABLE).read_text(encoding='utf-8'))
    if doc.get('format') != FORMAT:
        raise ValueError('create_setting.json: unknown format %r' % doc.get('format'))
    return doc


def _words(text):
    return re.findall(r'[a-z]+', str(text).lower().replace('-', ' '))


def setting_words(brief):
    """Words of the brief's setting fields (place, build types, props, unrecognised). Not the prompt."""
    s = brief.get('setting') or {}
    out = set(_words(s.get('place', '')))
    for b in brief.get('build_types', []):
        out |= set(_words(b))
    for p in brief.get('props', []):
        out |= set(_words(p.get('want', '')))
    for w in brief.get('unrecognised', []):
        out |= set(_words(w))
    return out


def apply_cues(brief, prompt, defaults, table=None):
    """Keyword (no-model) brief only: a cue word of the prompt sets the brief's place for a listed genre while the
    place is still the genre default (brief.D). Returns (brief, used phrases). A model brief is never changed."""
    table = table or load()
    s = brief.get('setting') or {}
    genre = s.get('genre')
    said = set(_words(prompt))
    default_place = (defaults.get(genre) or ('',))[0]
    for cue in table.get('brief_cues', []):
        hit = sorted(said & set(cue['words']))
        if genre in cue['genres'] and hit and s.get('place') == default_place:
            out = copy.deepcopy(brief)
            out['setting']['place'] = cue['place']
            out['assumptions'] = list(out.get('assumptions', []))[:23] + [
                ('setting words used: %s -> place %s' % (', '.join(hit), cue['place']))[:120]]
            return out, hit
    return brief, []


def match(brief, table=None):
    """The first setting row for this brief (genre, then any listed setting word), or None."""
    table = table or load()
    genre = (brief.get('setting') or {}).get('genre')
    bw = setting_words(brief)
    for row in table['settings']:
        m = row['match']
        if genre not in m['genres']:
            continue
        if m.get('words') and not (set(m['words']) & bw):
            continue
        return row
    return None


def prefers(brief, table=None):
    """True when the brief's setting row is marked prefer (STYLEGEN-2): asked even when the tag-scored pick succeeds."""
    row = match(brief, table)
    return bool(row and row.get('prefer'))


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def pack_id(reference, row_id, mood, extras, margin_moved=()):
    """Content-named id of a setting pack (as mood packs are `<base>_m<hash>`). Names moved by the emissive neon
    margin join the hash only when there are some, so a pack the margin leaves alone keeps its STYLEGEN-1 id."""
    key = {'setting': row_id, 'mood': mood, 'extras': sorted(extras), 'v': ID_VERSION}
    if margin_moved:
        key['emissive_margin'] = sorted(margin_moved)
    return '%s_s%s' % (reference, _sha(key)[:8])


# ------------------------------------------------------------------ emissive neon margin (STYLEGEN-2)
# The mood derivation keeps every non-neon colour outside its neon margin (kits/core/mood.py NEON_MARGIN: saturation
# below .55 OR value below .88) as a PALETTE colour. Emissive roles are drawn brighter than their palette colour:
# the runtime adds the role's emission and the room profile's grade (exposure, saturation, contrast) on top
# (runtime/godot/view/assets.gd, shaders/n64_world.gdshader). A setting pack builds pieces its reference never
# showed (station light strips in a planet palette), so a cyan at s .61 / v .86 drew at v >= .92 under the outpost
# grade and the N64 gate counted 1.70% neon pixels. This step applies the same margin to the colour as drawn, for
# palette names that emissive roles paint, by lowering OKLCh chroma only (lightness and hue kept). The result is
# checked again by the unchanged mood checks (tools.mood_pack.derive_all adjust). No threshold moves.
EMISSIVE_MARGIN = (0.55, 0.88)


def _rgb(h):
    h = str(h).lstrip('#')
    return [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _sv(c):
    mx, mn = max(c), min(c)
    return (0.0 if mx <= 0 else (mx - mn) / mx), mx


def graded(c, g):
    """The runtime colour grade on an sRGB colour (n64_world.gdshader grade(); rig.gd maps the profile's grade keys)."""
    g = g or {}
    lift, gain = _rgb(g.get('lift', '#000000')), _rgb(g.get('gain', '#ffffff'))
    c = [x * float(g.get('exposure', 1.0)) for x in c]
    c = [min(1.0, max(0.0, lift[i] + c[i] * (gain[i] - lift[i]))) for i in range(3)]
    c = [x ** (1.0 / max(float(g.get('gamma', 1.0)), 0.01)) for x in c]
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    c = [lum + float(g.get('saturation', 1.0)) * (x - lum) for x in c]
    return [min(1.0, max(0.0, (x - 0.5) * float(g.get('contrast', 1.0)) + 0.5)) for x in c]


def drawn_sv(hexc, scales, grades):
    """An emissive colour as drawn: texel x role scale (vertex light 1, no fog: the brightest case), then each room
    profile's grade. Returns (inside the margin under any role/profile?, worst [s, v]); worst = the pair closest to
    (or deepest inside) the margin."""
    c0 = _rgb(hexc)
    worst = (-1.0, 0.0, 0.0)
    for k in sorted(scales):
        for g in grades:
            s, v = _sv(graded([min(1.0, x * k) for x in c0], g))
            risk = min(s / EMISSIVE_MARGIN[0], v / EMISSIVE_MARGIN[1])
            if risk > worst[0]:
                worst = (risk, round(s, 3), round(v, 3))
    return worst[0] >= 1.0, [worst[1], worst[2]]


def emissive_scales(kit, view, conv, M):
    """palette name -> set of drawn-brightness scales, one per emissive role that paints with it."""
    names = set(kit['palette_names'])
    resp = ((view or {}).get('look') or {}).get('materials') or {}
    light = (conv or {}).get('lighting') or {}
    ul, em_max = float(light.get('unlit_level', 1.0)), light.get('emission_max')
    out = {}
    for role, m in sorted(kit['materials'].items()):
        if m.get('kind') != 'emissive':
            continue
        r = resp.get(role) or {}
        e = float(r.get('emission', 0.0))
        if em_max is not None and 'emission' in r:
            e = min(e, float(em_max))
        lit = max(0.0, min(1.0, float(r.get('lit', 0.0))))
        k = round((1.0 + e) * (ul + (1.0 - ul) * lit) * (1.0 + 0.8 * lit), 6)   # lit surfaces: room rig up to 1.8
        for n in M._names_in({kk: v for kk, v in m.items() if kk != 'kind'}, names):
            out.setdefault(n, set()).add(k)
    return out


def profile_grades(view, names=None):
    """Grades of the named look profiles (the profiles the setting's rooms use); every profile when none is named."""
    look = (view or {}).get('look') or {}
    profs = look.get('profiles') or {}
    keys = [n for n in (names or []) if isinstance(profs.get(n), dict)] or sorted(profs)
    grades = [profs[k].get('grade') or {} for k in keys if isinstance(profs.get(k), dict)]
    if isinstance(look.get('grade'), dict):
        grades.append(look['grade'])
    return grades or [{}]


def emissive_margin(kit, derived, view, conv, M, profiles=None):
    """-> (derived copy, moved rows). Names whose base colour was already neon are left alone (as the mood does)."""
    scales = emissive_scales(kit, view, conv, M)
    grades = profile_grades(view, profiles)
    pal = list(derived['palette'])
    moved = []
    for i, n in enumerate(derived['palette_names']):
        if n not in scales or M.is_neon(kit['palette'][i]):
            continue
        risk, sv = drawn_sv(pal[i], scales[n], grades)
        if not risk:
            continue
        L, C, H = M.hex_lch(pal[i])
        out = pal[i]
        for _ in range(60):
            C *= 0.93
            out = M.lch_hex(L, C, H)
            if not drawn_sv(out, scales[n], grades)[0]:
                break
        moved.append({'name': n, 'from': pal[i], 'to': out, 'drawn_sv_before': list(sv),
                      'drawn_sv_after': list(drawn_sv(out, scales[n], grades)[1])})
        pal[i] = out
    d = copy.deepcopy(derived)
    if moved:
        idx = {m['name'] for m in moved}
        order = [i for i, n in enumerate(d['palette_names']) if n not in idx] + \
                [i for i, n in enumerate(d['palette_names']) if n in idx]
        d['palette'] = M._unique(pal, order)
    return d, moved


def margin_adjuster(bundle, reference, row_id, mood, extras, M, profiles=None):
    """The adjust step for tools.mood_pack.derive_all/install: the emissive neon margin, measured with the
    reference's own view (material response, the look profiles the setting's rooms use) and the N64 convention
    lighting."""
    bundle = Path(bundle)
    vp, cp = bundle / 'packs' / reference / 'view.json', bundle / 'kits' / 'core' / 'n64_look.json'
    view = json.loads(vp.read_text(encoding='utf-8')) if vp.is_file() else {}
    conv = json.loads(cp.read_text(encoding='utf-8')) if cp.is_file() else {}
    profiles = sorted(set(profiles or []))

    def adjust(kit, derived):
        d, moved = emissive_margin(kit, derived, view, conv, M, profiles)
        if moved:
            d['id'] = pack_id(reference, row_id, mood, extras, [m['name'] for m in moved])
            if 'style' in d:
                d['style'] = d['id']
        return d, {'step': 'emissive neon margin', 'margin': list(EMISSIVE_MARGIN), 'profiles': profiles, 'moved': moved}
    return adjust


def room_profiles(fam_row, row, reference):
    """The look profiles of the patterns a setting uses with this reference."""
    outdoor, indoor = chosen_patterns(fam_row, row, reference)
    return sorted({str(p['plan']['look_profile']) for p in outdoor + indoor if p['plan'].get('look_profile')})


def adjuster_for(bundle, setting, families, M, table=None):
    """The same adjust step, rebuilt from a recorded setting decision (create/style.json `setting`), for the mood
    and install stages: they must derive exactly the pack the style stage chose."""
    table = table or load()
    if not table.get('emissive_margin', {}).get('on'):
        return None
    row = next((r for r in table['settings'] if r['id'] == setting['setting']), None)
    if row is None or setting.get('family') not in families:
        return None
    return margin_adjuster(bundle, setting['base'], row['id'], setting['mood'], setting.get('extras') or [], M,
                           room_profiles(families[setting['family']], row, setting['base']))


def pattern_keys(pat):
    return {p['key'] for p in pat['plan'].get('pieces', []) if p.get('key')}


def chosen_patterns(fam_row, row, reference=None, camera=None):
    """(entry patterns, inside patterns) the setting may use: the row's named ones, else the family's lists. A pattern's
    look_profile_for names the reference pack's own look profile for that room (a profile the reference calibrated).
    camera (STYLEGEN-2): camera(pattern, alternate id) -> camera; a row's entry_camera names one of the entry
    pattern's calibrated, knob-bounded camera alternates, which becomes that room's pattern camera (its first view)."""
    out = [p for p in fam_row['outdoor'] if not row.get('entry') or p['id'] == row['entry']] or fam_row['outdoor']
    ins = [p for p in fam_row['indoor'] if not row.get('inside') or p['id'] == row['inside']] or fam_row['indoor']

    def own(p):
        prof = (p.get('look_profile_for') or {}).get(reference)
        if not prof:
            return p
        return dict(p, plan=dict(p['plan'], look_profile=prof))

    def framed(p):
        if not (row.get('entry_camera') and camera):
            return p
        return dict(p, plan=dict(p['plan'], camera=camera(p, row['entry_camera'])), camera_from=row['entry_camera'])
    return [framed(own(p)) for p in out], [own(p) for p in ins]


def _line(value):
    return ' '.join(str(value).split())


def decide(bundle, brief, mp, family_for, families, bindings_keys, one_line=_line, table=None):
    """-> (decision or None, report lines). Tries the matching row's references in order."""
    table = table or load()
    row = match(brief, table)
    genre = (brief.get('setting') or {}).get('genre')
    if row is None:
        return None, ['setting: no row in create_setting.json for genre %r and these setting words' % genre]
    lines = ['setting: row %s' % row['id']]
    bundle = Path(bundle)
    for ref in row['references']:
        pid, mood = ref['pack'], ref.get('mood')
        if not (bundle / 'packs' / pid / 'bindings.json').is_file():
            lines.append('setting: %s is not in this plugin tree; next reference' % pid)
            continue
        fam = family_for(pid, setting=True)
        if fam is None:
            lines.append('setting: %s has no create room patterns (create_patterns.json); next reference' % pid)
            continue
        outdoor, indoor = chosen_patterns(families[fam], row)
        need = set().union(*[pattern_keys(p) for p in outdoor + indoor])
        base_keys, _doc = bindings_keys(pid)
        extras = sorted(need - base_keys)
        presets = json.loads((bundle / 'kits' / 'packs' / pid / 'pack.json').read_text(encoding='utf-8')).get('kit_presets') or {}
        unbuildable = [k for k in extras if '__' in k and k.partition('__')[2] not in (presets.get(k.partition('__')[0]) or {})]
        if unbuildable:
            lines.append('setting: %s cannot build %s (no such kit preset); next reference' % (pid, ', '.join(unbuildable)))
            continue
        if not mood:
            if extras:
                lines.append('setting: %s lacks %s and has no mood to build them in; next reference' % (pid, ', '.join(extras)))
                continue
            lines.append('setting: %s used as-is (no mood)' % pid)
            return dict({'setting': row['id'], 'base': pid, 'pack': pid, 'mood': None, 'family': fam,
                         'entry': row.get('entry'), 'inside': row.get('inside'), 'extras': [], 'lines': lines},
                        **framing(row, lines)), lines
        new_id = pack_id(pid, row['id'], mood, extras)
        adjust = None
        if table.get('emissive_margin', {}).get('on'):
            adjust = margin_adjuster(bundle, pid, row['id'], mood, extras, mp.M, room_profiles(families[fam], row, pid))
        try:
            derived, sp, view, rep = mp.derive_all(pid, mood, new_id, root=bundle, adjust=adjust)
        except SystemExit as e:
            lines.append('setting: %s + %s refused by the mood checks (%s); next reference' % (pid, mood, one_line(e)[:240]))
            continue
        if sp is None or view is None:
            lines.append('setting: %s has no style pack/view to derive; next reference' % pid)
            continue
        lines.append('setting: derived %s from %s + %s (strength %s%s); %d pattern pieces built in the derived palette'
                     % (derived['id'], pid, mood, rep.get('strength'), ', clamped' if rep.get('clamped') else '', len(extras)))
        moved = (rep.get('adjust') or {}).get('moved') or []
        if moved:
            lines.append('setting: emissive neon margin (as drawn in the %s profiles): %s' % (
                '/'.join((rep.get('adjust') or {}).get('profiles') or ['all']),
                ', '.join('%s %s -> %s' % (m['name'], m['from'], m['to']) for m in moved)))
        return dict({'setting': row['id'], 'base': pid, 'pack': derived['id'], 'mood': mood, 'family': fam,
                     'entry': row.get('entry'), 'inside': row.get('inside'), 'extras': extras,
                     'pack_sha256': rep['pack_sha256'], 'view_sha256': rep.get('view_sha256'), 'strength': rep.get('strength'),
                     'clamped': rep.get('clamped'), 'margin_moved': [m['name'] for m in moved], 'lines': lines},
                    **framing(row, lines)), lines
    lines.append('setting: no reference of row %s could be used' % row['id'])
    return None, lines


def framing(row, lines):
    """STYLEGEN-2: the row's entry_camera (a calibrated camera alternate of its entry pattern), only when it names one,
    so every other decision keeps its keys and bytes."""
    if not row.get('entry_camera'):
        return {}
    lines.append('setting: entry first view on the pattern\'s calibrated %s camera (%s)' % (
        row['entry_camera'], row.get('entry_camera_why', 'row entry_camera')))
    return {'entry_camera': row['entry_camera']}


def marker(decision):
    """packs/<id>/setting.json: what made this setting pack (shipped_packs never offers it as a base)."""
    return {'format': 'hermes64-setting-pack/1', 'setting': decision['setting'], 'reference': decision['base'],
            'mood': decision['mood'], 'extras': decision['extras'], 'pack_sha256': decision.get('pack_sha256'),
            'note': 'derived setting pack (adventure_maker/create_setting.py); not a shipped base'}
