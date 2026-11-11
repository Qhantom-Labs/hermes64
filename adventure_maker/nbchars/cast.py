"""cast_v1: the character family on the approved hero body (lane CAST1), plugin side.

A cast character is a SPEC (data): cameo / face / colour params, SHAPE dials (height, lengths, widths), STYLE dials
(hair, visor, coat, guards, plate), PAINT dials (outfit, mark, colours) and props. `cast_presets.json` holds the
presets shipped with the plugin (three faction bosses, a hooded hero, three body variants); any other spec of the
same form builds the same way. Nothing in the generator names a character.

    rec = recipe('npc_child')                      # or recipe(None, shape={...}, style={...}) for a spec of your own
    glb, scene = character_bytes(rec)
    values, bad = gate(rec)                        # tall_v3's alignment gate + symmetry + leg gap, on this body

Rig: human16_v1, the hero's 16 bones moved with the body (same names, same parents, same clip set). The locomotion
bake of lane CHARS5 is not on this branch; when it lands the cast opts in by calling its tool, nothing here edits
locomotion files.

The generator modules (characters/gen/ext/cast_v1*.py) are loaded here with the same loader nbchars/tall_v3 uses
for the restricted round-21 modules, so nbchars/gen.py is not edited. The hero (tall_v3 revisions 1-3), round 21
and masked_v1 / masked_v2 are not touched.
"""
import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

from . import assemble as A
from . import blendmath as BM
from . import gen as GEN
from . import tall_v3 as TV
from .scene import Scene, SceneRig, SceneSocket

F32 = np.float32
PACK = 'cast_v1'
PRESET = 'cast_v1'
SKELETON = TV.SKELETON
CLIPS = list(TV.CLIPS)
BUDGET = dict(TV.BUDGET)
EXT = ('cast_v1', 'cast_v1_paint', 'cast_v1_props')
PRESETS_FILE = Path(__file__).with_name('cast_presets.json')
SPEC_KEYS = ('params', 'shape', 'style', 'paint', 'props')
LOCOMOTION_NOTE = 'rig human16_v1; CHARS5 locomotion bake not on this branch (opt in by calling its tool when present)'


class CastError(A.AssemblyError):
    pass


def _doc():
    return json.loads(PRESETS_FILE.read_text(encoding='utf-8'))


def _load(G, name):
    full = G.pkg + '.' + name
    if full not in sys.modules:
        f = str(G.root / 'ext' / (name + '.py'))
        spec = importlib.util.spec_from_file_location(full, f, loader=GEN._CompatLoader(full, f))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[full] = mod
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(full, None)
            raise
    return sys.modules[full]


def pack_doc(G):
    """The cast pack: the round-21 palette pack plus the colours and ramps of cast_presets.json."""
    ext = _doc()['pack']
    pack = G.pack(ext['base'])
    pack['id'] = ext['id']
    for name, hx in ext['colors'].items():
        if name in pack['palette_names']:
            raise CastError('pack colour %s already exists' % name)
        pack['palette_names'].append(name); pack['palette'].append(hx)
    for key in ('ramps', 'char_ramps'):
        for name, lst in ext['ramps'].items():
            if name in pack[key]:
                raise CastError('pack ramp %s already exists' % name)
            pack[key][name] = list(lst)
    return pack


def modules(G=None):
    """(G, cameo, cameo_paint, tall_v3, tall_v3_paint, clips_tall_v3, pose, cast_v1, cast_v1_paint, cast_v1_props)."""
    mods = TV.modules(G)
    G = mods[0]
    if PACK not in G.inline:
        G.inline[PACK] = {'pack': pack_doc(G)}
    return mods + tuple(_load(G, n) for n in EXT)


def presets():
    return sorted(_doc()['presets'])


def revisions(preset):
    """Revision numbers a preset can be built at: 1 (the preset as listed) plus the entries of the top-level
    `revisions` block of cast_presets.json (lane CEOFIX: the bind fixes). Earlier revisions stay buildable."""
    doc = _doc()
    if preset not in doc['presets']:
        raise CastError('no cast preset %r' % (preset,))
    return [1] + sorted(int(k) for k in doc.get('revisions', {}).get(preset, {}))


def _revised(doc, preset, base, revision):
    """The preset spec at a revision: each revision entry is merged over the one before it, per section (dict
    sections key by key, `props` replaced)."""
    if revision is None:
        return base
    have = revisions(preset)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision not in have:   # True == 1: refused
        raise CastError('cast preset %s has revisions %s, not %r' % (preset, have, revision))
    for r in have[1:]:
        if r > revision:
            break
        step = doc['revisions'][preset][str(r)]
        for k, v in step.items():
            if k == 'props':
                base['props'] = copy.deepcopy(v)
            elif k in ('params', 'shape', 'style', 'paint'):
                base[k] = dict(base.get(k, {}), **v)
            elif k != 'note':
                raise CastError('revision %s of %s: unknown section %r' % (r, preset, k))
    return base


def recipe(preset=None, revision=None, **over):
    """The record of a preset (or of an empty spec), with overrides merged per section:
    recipe('npc_child', shape={'height': 1.3}); recipe('ceo_aipo', revision=2) builds a later revision."""
    doc = _doc()
    if preset is None:
        if revision is not None:
            raise CastError('a revision needs a preset')
        base = {}
    elif preset in doc['presets']:
        base = _revised(doc, preset, copy.deepcopy(doc['presets'][preset]), revision)
    else:
        raise CastError('no cast preset %r (have %s)' % (preset, ', '.join(sorted(doc['presets']))))
    unknown = set(over) - set(SPEC_KEYS) - {'id'}
    if unknown:
        raise CastError('unknown spec sections %s' % sorted(unknown))
    rec = {'id': over.get('id') or preset or 'cast_custom', 'preset': PRESET, 'label': base.get('label', ''), 'stance': 'neutral'}
    if revision is not None and revision != 1:      # validated above: an int revision of this preset
        rec['revision'] = revision
    params, _ = TV.r21_params()
    params.pop('height', None)
    params.update(doc.get('common', {}))
    params.update(base.get('params', {})); params.update(over.get('params') or {})
    rec['params'] = params
    for k in ('shape', 'style', 'paint'):
        d = dict(base.get(k, {})); d.update(over.get(k) or {})
        rec[k] = d
    rec['props'] = copy.deepcopy(over['props'] if over.get('props') is not None else base.get('props', []))
    return rec


def _spec(rec):
    return {'params': rec['params'], 'shape': rec.get('shape') or {}, 'style': rec.get('style') or {}}


def body(rec, G=None):
    m = modules(G)
    CAM, T3, C = m[1], m[3], m[7]
    try:
        return C.person(CAM, T3, _spec(rec))
    except C.SpecError as e:
        raise CastError('%s: %s' % (rec.get('id'), e))


def gate(rec, G=None, a=None):
    """(values, failures) of tall_v3's alignment gate plus the cast checks (symmetry of every group, leg gap)."""
    m = modules(G)
    return m[7].gate(m[3], a if a is not None else body(rec, m[0]))


def textures(rec, a, G=None):
    G, CAM, CAMP, T3, T3P, CL, PO, C, CP, CPR = modules(G)
    PPT = G.core('people_paint')
    pack = G.pack(PACK)
    p = a.params
    cloth = CAMP.costume_atlas(pack, p); face = PPT.face_atlas(pack, p); hair = CAMP.headwear(pack, p)
    cloth, face, hair = T3P.repaint(pack, p, cloth, face, hair)
    try:
        return CP.repaint(pack, p, a.cast['style'], rec.get('paint'), cloth, face, hair, C.CR, C.HWR, CAM.HW)
    except CP.PaintError as e:
        raise CastError('%s: %s' % (rec.get('id'), e))


def _prop_socket(G, a, prop, h, mods):
    CPR = mods[9]
    pack = G.pack(PACK)
    unknown = set(prop) - {'kind', 'colors', 'form'}
    if unknown:
        raise CastError('prop %s: unknown keys %s' % (prop.get('kind'), sorted(unknown)))
    try:
        m = CPR.build(prop['kind'], a, prop.get('colors'), pack, form=prop.get('form', 'box'))
    except CPR.PropError as e:
        raise CastError(str(e))
    kind = m['kind']
    if len(m['faces']) > BUDGET['prop']:
        raise CastError('prop %s: %d tris, budget <= %d' % (kind, len(m['faces']), BUDGET['prop']))
    mat = A._material('mat_%s_prop_%s_%s' % (PACK, kind, h), 'tex_%s_prop_%s' % (h, kind), A.png_bytes(m['texture']),
                      pack['id'], 'prop')
    me = A._mesh('kit_acc_%s_%s_mesh' % (m['slot'], kind), m['vertices'], m['faces'], [0] * len(m['faces']), m['uv'], [mat])
    me.corner_color = A._bake_colors(me.vertices, me.faces, me.vertex_normals, A._ramp(G, pack),
                                     lambda vi, n: .84 + .15 * max(-.6, A._vdot(n)))
    head = a.bones[m['bone']]
    me.vertices = (np.asarray(m['vertices'], dtype=np.float64) - np.asarray(head)).astype(F32)
    extras = {'n64_prop': {'kind': kind, 'slot': m['slot'], 'tris': len(m['faces']), 'removable': True}}
    return SceneSocket(name='kit_acc_%s_%s' % (m['slot'], kind), bone=m['bone'], translation=(0., 0., 0.),
                       rotation=(0., 0., 0., 1.), mesh=me, extras=extras)


def character(rec, clips=None, G=None):
    mods = modules(G)
    G, CAM, CAMP, T3, T3P, CL, PO, C, CP, CPR = mods
    pack = G.pack(PACK)
    a = body(rec, G)
    p = a.params
    if len(a.faces) >= BUDGET['body']:
        raise CastError('%s: body %d tris, budget < %d' % (rec['id'], len(a.faces), BUDGET['body']))
    h = hashlib.sha256(json.dumps([PRESET, p, a.cast, rec.get('paint'), rec.get('props')], sort_keys=True).encode()).hexdigest()[:10]
    cloth, face, hair = textures(rec, a, G)
    tex = [('tex_' + h + '_cloth', cloth), ('tex_' + h + '_face', face), ('tex_' + h + '_hair', hair)]
    spec = [('costume', 'baked_unlit', None), ('face', 'face_atlas', {'cols': 4, 'rows': 2, 'cell': p['expression']}),
            ('headwear', 'baked_unlit', None)]
    mats = []
    for (img_name, arr), (role, kind, atlas), slot in zip(tex, spec, ('costume', 'face', 'headwear')):
        mats.append(A._material('mat_%s_char_%s_%s' % (PACK, slot, h), img_name, A.png_bytes(arr), pack['id'], role, kind, atlas))
    fmat = [A.HUMAN_ROLE_SLOT[r] for r in a.roles]
    mesh = A._mesh('kit_body_mesh', a.vertices, a.faces, fmat, a.uv, mats)
    twins = getattr(a, 'cast_twins', None)
    if twins:
        # coat_top 'tucked': the skirt's top ring and the jacket's hem ring are one vertex for shading, as when they
        # were shared (revision 1): normals of the faces with each twin welded to its hem vertex
        Fw = np.asarray(mesh.faces).copy()
        for t, h0 in sorted(twins.items()):
            Fw[Fw == t] = h0
        vn = BM.vertex_normals(mesh.vertices, Fw)
        for t, h0 in sorted(twins.items()):
            vn[t] = vn[h0]
        mesh.vertex_normals = vn
    ramp = A._ramp(G, pack)
    V32 = mesh.vertices
    low = p['height'] * .12
    soft = set()
    ao = getattr(a, 'ao', {})
    for part in ('face', 'nose'):
        soft |= set(a.parts.get(part, []))

    def shade(vi, n):
        d = A._vdot(n)
        s = .76 + .23 * max(-.7, d) if vi not in soft else .84 + .14 * max(-.5, d)
        if float(V32[vi, 2]) < low:
            s -= .045
        return s * ao.get(vi, 1.)
    mesh.corner_color = A._bake_colors(V32, mesh.faces, mesh.vertex_normals, ramp, shade)
    order = list(a.bones)
    mesh.groups = order
    gi = {n: i for i, n in enumerate(order)}
    mesh.weights = [[(gi[n], float(F32(w))) for n, w in wts.items()] for wts in a.weights]
    extras = {'skeleton': SKELETON, 'params_json': json.dumps(p, sort_keys=True), 'stance': rec['stance'],
              'topology': a.topology, 'preset': PRESET, 'cast_json': json.dumps(a.cast, sort_keys=True),
              'locomotion': LOCOMOTION_NOTE}
    if rec.get('revision'):                         # later revisions only: revision-1 files keep their bytes
        extras['cast_revision'] = rec['revision']
    if getattr(a, 'cast_bind', None):
        extras['cast_bind_json'] = json.dumps(a.cast_bind, sort_keys=True)
    rig = SceneRig(object_name='rig_' + SKELETON, skeleton=SKELETON, bones={n: tuple(a.bones[n]) for n in order},
                   parents={n: a.parents[n] for n in order}, extras=extras)
    sc = Scene(kind='human', rig=rig, body=mesh)
    for slot, bone in A.ATTACH_SLOTS:
        sc.sockets.append(SceneSocket(name='attach_' + slot, bone=bone, rotation=(A.SQRT_HALF, 0., 0., A.SQRT_HALF)))
    props = []
    for prop in rec.get('props') or []:
        s = _prop_socket(G, a, prop, h, mods)
        sc.sockets.append(s)
        props.append(dict(s.extras['n64_prop']))
    names = list(clips) if clips is not None else list(CLIPS)
    sk = A._Skinner(a.bones, a.parents, a.vertices, a.weights)
    metrics = PO.body_metrics(a)
    tv_rec = {'preset': 'tall_v3', 'stance': rec['stance']}
    for name in names:
        sc.clips.append(TV._clip(G, a, sk, name, order, metrics, tv_rec))
    for m in mats:
        at = m.n64.get('atlas')
        if at and names:
            cells = dict(at.get('clip_cells', {}))
            m.atlas_cell = (int(cells.get(names[-1], at['cell'])), int(at['cols']), int(at['rows']))
    sc.info = {'params': p, 'hash': h, 'stance': rec['stance'], 'props': props, 'pack': PACK, 'topology': a.topology,
               'skeleton': SKELETON, 'generator': a, 'tris': len(a.faces), 'preset': PRESET, 'cast': a.cast,
               'prop_tris': sum(x['tris'] for x in props)}
    return sc


def character_bytes(rec, clips=None, G=None):
    from . import writer
    sc = character(rec, clips=clips, G=G)
    return writer.write_scene(sc, writer.GENERATOR), sc
