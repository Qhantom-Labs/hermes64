"""STYLEENGINE: make anything in the house N64 style (docs/STYLEENGINE-PLAN.md).

Every intake ends as a project `gen:` recipe (hermes64-recipe/1) that the existing generator path builds, gates,
places and records:

  compose(words)          plain words -> recipe (forms + modifiers in styleengine.json; examples, not limits)
  make(...)               words, an agent recipe (.json) or an agent builder script (.py, run once in the sandbox)
                          -> recipe with a conform block -> build -> gates (+ conform-and-retry, + hints)
  import_file(...)        the user's own GLB/OBJ (+ PNG/JPG) -> role-mapped mesh (sandboxed child) -> recipe -> build
  conform_file(...)       an existing GLB -> decimated, palette/texture-conformed, unlit GLB with its numbers (not placed)

The parent needs no numpy: geometry, textures and scripts run in the sandboxed child (styleengine_child.py) under
runner.Runner, with reads confined to the project, the bundle and the interpreter.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

DATA = Path(__file__).with_name('styleengine.json')
ROOT = Path(__file__).resolve().parents[1]
CHILD = Path(__file__).with_name('styleengine_child.py')
CLASS_TRIS = {'shell': 1500, 'building': 900, 'structure': 500, 'arch': 300, 'terrain': 512, 'flora': 300,
              'furniture': 300, 'furniture_large': 400, 'vehicle': 500, 'prop': 150, 'soft': 150}
CLASS_EXTENT = {'prop': 1.6, 'furniture': 4.5, 'furniture_large': 6.0, 'structure': 40.0, 'arch': 16.0,
                'building': 30.0, 'flora': 30.0, 'vehicle': 20.0, 'soft': 3.2, 'terrain': 200.0, 'shell': 40.0}
CLASS_UP = ['prop', 'furniture', 'furniture_large', 'structure']
SCRIPT_BYTES = 65536
FIT_KEEP_MIN = 0.4          # decimate-to-fit keeps at least this share of a piece's triangles
IMPORT_BYTES = 32 * 1024 * 1024
STOP = {'a', 'an', 'the', 'of', 'with', 'and', 'on', 'in', 'for', 'to', 'its', 'my', 'some', 'made', 'from', 'that',
        'this', 'at', 'by', 'very', 'old', 'new', 'little'}


class StyleEngineError(ValueError):
    pass


def load():
    return json.loads(DATA.read_text(encoding='utf-8'))


def words(text):
    return re.findall(r"[a-z][a-z'\-]*", str(text or '').lower())


def _singular(w):
    return w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w


def slug(text, prefix='se'):
    w = [x.replace("'", '').replace('-', '_') for x in words(text) if x not in STOP][:5]
    base = '_'.join(w)[:36].strip('_') or 'piece'
    base = re.sub(r'[^a-z0-9_]', '', base)
    return (prefix + '_' + base)[:48] if prefix else base[:48]


# ------------------------------------------------------------------------------------------------- pack colours
def _hex(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def role_colours(pack_dict):
    """{role: mean RGB of its ramp} from pack JSON alone (no numpy, no painting)."""
    pal = dict(zip(pack_dict.get('palette_names', []), pack_dict.get('palette', [])))
    out = {}
    for role, m in (pack_dict.get('materials') or {}).items():
        t = m.get('texture') if isinstance(m, dict) else None
        names = (t or {}).get('ramp') or ([m.get('tint')] if isinstance(m, dict) and m.get('tint') else [])
        cols = [_hex(pal[n]) for n in names if n in pal]
        if cols:
            out[role] = tuple(sum(c[i] for c in cols) / len(cols) for i in range(3))
    return out


def ranked_roles(target_hex, colours, candidates):
    """Pack roles by distance of their ramp colour to the target (nearest first; weighted RGB, as palette.py)."""
    t = _hex(target_hex)
    rows = []
    for r in dict.fromkeys(candidates):
        if r in colours:
            c = colours[r]
            rows.append((3 * (c[0] - t[0]) ** 2 + 4 * (c[1] - t[1]) ** 2 + 2 * (c[2] - t[2]) ** 2, r))
    return [r for _d, r in sorted(rows)]


def nearest_role(target_hex, colours, candidates):
    ranked = ranked_roles(target_hex, colours, candidates)
    return ranked[0] if ranked else None


# ------------------------------------------------------------------------------------------------------ compose
def _gear(r, n):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        for da, rr in ((-0.32, 0.78), (-0.16, 1.0), (0.16, 1.0), (0.32, 0.78)):
            b = a + da * 2 * math.pi / n
            pts.append([round(r * rr * math.cos(b), 4), round(r * rr * math.sin(b), 4)])
    return pts[:32]


def _scaled(v):
    if isinstance(v, list):
        return [_scaled(x) for x in v]
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return {'param': 'height', 'mul': round(float(v), 4)} if v else 0
    return v


def _op(raw, slots):
    prim, slot, args = raw[0], raw[1], dict(raw[2])
    extra = raw[3] if len(raw) > 3 else {}
    out = {}
    for k, v in args.items():
        if isinstance(v, str) and v.startswith('@gear:'):
            _, r, n = v.split(':')
            v = _gear(float(r), int(n))
        if k in ('segs', 'sides', 'nu', 'nv') or (k == 'rings' and not isinstance(v, list)):
            out[k] = int(v)
        elif k == 'squash_bottom' or (prim == 'lathe' and k in ('rx', 'ry')):
            out[k] = v
        else:
            out[k] = _scaled(v)
    op = {'primitive': prim, 'role': slots.get(slot, slot), 'args': out}
    tr = {}
    if 'rotate' in extra:
        tr['rotate'] = list(extra['rotate'])
    if 'translate' in extra:
        tr['translate'] = _scaled(extra['translate'])
    if tr:
        op['transform'] = tr
    if 'repeat' in extra:
        rep = dict(extra['repeat'])
        if 'step' in rep:
            rep['step'] = _scaled(rep['step'])
        op['repeat'] = rep
    if extra.get('mirror'):
        op['mirror'] = extra['mirror']
    return op


def compose(description, pack_dict=None, data=None):
    """Plain words -> (hermes64-recipe/1 with a conform block, notes). Never refuses for vocabulary."""
    data = data or load()
    ws = [w for w in words(description) if w not in STOP]
    bag = set(ws) | {_singular(w) for w in ws}
    notes = []
    noun_form = {}
    for fid, f in data['forms'].items():
        for n in f['nouns'] + f.get('near', []):      # STYLEENGINE-2: near nouns still size/shape a stand-in
            noun_form.setdefault(n, fid)
    # head noun: the last word naming a form; material words that are also nouns (stone, crystal) count only if no
    # other form noun follows them
    head, fid = None, None
    for w in reversed(ws):
        s = _singular(w)
        if w in noun_form or s in noun_form:
            head, fid = w, noun_form.get(w) or noun_form.get(s)
            break
    if fid is None:
        fid = 'object'
        head = next((w for w in reversed(ws) if w not in data['scale']), '')
        notes.append('no form known for "%s": made as the generic object form (base, body, band); '
                     'an agent recipe or builder script can make its real shape' % (head or description))
    form = data['forms'][fid]
    used_mats = [mid for mid, m in data['materials'].items() if set(m['words']) & bag]
    variant = next((mid for mid in used_mats if mid in form.get('variants', {})), None)
    parts = copy.deepcopy(form['variants'][variant] if variant else form['parts'])
    slots = dict(data['slots'])
    colours = role_colours(pack_dict) if pack_dict else {}
    cands = data['candidates']
    role_params = {}

    def by_colour(hex_, slot, why):
        # the three nearest pack roles; the loop steps to the next one if a gate refuses the first (a transform)
        ranked = ranked_roles(hex_, colours, cands)[:3]
        if not ranked:
            return None
        if why:
            notes.append('%s: pack roles nearest to %s: %s' % (why, hex_, ', '.join(ranked)))
        if len(ranked) == 1:
            return ranked[0]
        role_params['role_' + slot] = {'type': 'string', 'default': ranked[0], 'enum': ranked}
        return {'param': 'role_' + slot}
    if colours and form.get('colour'):
        r = by_colour(form['colour'], 'primary', '')
        if r:
            slots['primary'] = r
    for mid in used_mats:
        m = data['materials'][mid]
        for slot, role in m.get('slot', {}).items():
            if role == '@colour':
                role = by_colour(m['colour'], slot, mid if not any(n.startswith(mid + ':') for n in notes) else '') \
                    if colours else None
            if role:
                slots[slot] = role
        if m.get('add') and m['add'] in data['adds'] and not (variant == mid):
            if m['add'] == 'stand' and fid in ('balloon', 'tower', 'house', 'tree', 'rock', 'bridge', 'fountain'):
                continue
            parts += copy.deepcopy(data['adds'][m['add']])
            if m['add'] == 'stand':
                notes.append('floating: raised on a thin stand so the room\'s floating check holds')
    scale = 1.0
    for w in ws:
        k = data['scale'].get(w)
        if k is not None:
            scale = max(scale, k) if k > 1 else min(scale, k)
    height = round(float(form['height']) * scale, 3)
    cls = form['class']
    while cls in CLASS_UP[:-1] and height > CLASS_EXTENT[cls] * 0.95:
        cls = CLASS_UP[CLASS_UP.index(cls) + 1]
    if cls != form['class']:
        notes.append('class %s -> %s for its size (%.1f m)' % (form['class'], cls, height))
    ops = [_op(p, slots) for p in parts]
    rid = slug(description)
    params = {'height': {'type': 'number', 'default': height, 'minimum': round(height * 0.4, 3),
                         'maximum': round(height * 1.6, 3)}}
    used_params = {op['role']['param'] for op in ops if isinstance(op['role'], dict)}
    params.update({k: v for k, v in role_params.items() if k in used_params})
    recipe = {'format': 'hermes64-recipe/1', 'id': rid, 'class': cls, 'licence': 'CC0-1.0', 'parameters': params,
              'operations': ops, 'conform': {'max_tris': CLASS_TRIS.get(cls, 300)}}
    roles = {params[op['role']['param']]['default'] if isinstance(op['role'], dict) else op['role'] for op in ops}
    info = {'form': fid, 'head': head, 'variant': variant, 'materials': used_mats, 'class': cls, 'height_m': height,
            'roles': sorted(roles), 'notes': notes}
    from .needs_design import assess          # STYLEENGINE-2: does this form truly depict the words? (known/near/unknown)
    got = assess(description, data)
    info.update(fit=got['fit'], unknown=got['unknown'], why=got['why'])
    return recipe, info


# ---------------------------------------------------------------------------------------------- build pipeline
def _project(root):
    from . import gen_tools
    return gen_tools.workspace(root)


def build_recipe(root, recipe, pack_id, *, model, want, python_path='', max_tries=4, seed=0):
    """author -> build -> (parameter adjust | conform transform) -> build, at most max_tries; returns a row."""
    from . import asset_loop, gen_tools
    p = _project(root)
    gen_tools.author(p.root, recipe, model=model, brief_line=want,
                     replace=p.path('recipes/' + recipe['id'] + '.json').exists())
    spec = gen_tools.spec_from_recipe(recipe)
    P = spec.defaults()
    row = {'want': want, 'id': spec.id, 'attempts': [], 'model': model}
    built = None
    t0 = time.monotonic()
    for n in range(max_tries):
        built = gen_tools.build(p.root, spec.id, pack_id, params=P, seed=seed, sweep=False, python_path=python_path)
        row['attempts'].append({'try': n + 1, 'ok': built['ok'], 'errors': built['errors'][:6]})
        if built['ok']:
            break
        P2, changes = asset_loop._adjust(recipe, P, built['errors'])
        if not changes:
            recipe, changes = asset_loop._conform(recipe, built)
            if changes:
                gen_tools.author(p.root, recipe, model=model, brief_line=want, replace=True)
        else:
            P = P2
        if not changes:
            break
        row['attempts'][-1]['next'] = changes
    row['seconds'] = round(time.monotonic() - t0, 2)
    row['recipe'] = recipe
    row['ok'] = bool(built and built['ok'])
    if row['ok']:
        row.update(file=built['file'], sha256=built['sha256'], tri_count=built['tri_count'],
                   measure=measure(built), gates=_gate_summary(built))
    else:
        errs = (built or {}).get('errors') or ['not built']
        row['errors'] = errs[:6]
        row['hints'] = [h for h in (hint_for(e, (built or {}).get('conform_hint')) for e in errs) if h]
    return row


def hint_for(error, plan=None):
    """One concrete conform hint for a gate error line (the gate itself is unchanged)."""
    s = str(error)
    m = re.search(r'texture energy ([0-9.]+) > ([0-9.]+)', s) or re.search(r'hf energy ([0-9.]+) > ([0-9.]+)', s)
    if m:
        c = (plan or {}).get('conform')
        if c:
            return 'texture energy %s > %s: conform %s (measured %s after)' % (
                m.group(1), m.group(2), json.dumps(c, sort_keys=True), (plan.get('after') or {}).get('median_hf'))
        return 'texture energy %s > %s: conform {"soften": 1} and build again' % (m.group(1), m.group(2))
    m = re.search(r'budget: (\d+) triangles > (\d+)', s)
    if m:
        return 'triangles %s > %s: conform {"max_tris": %s} (decimate)' % (m.group(1), m.group(2), m.group(2))
    m = re.search(r'room triangle budget \((-?\d+) left, piece (\d+)\)', s)
    if m:
        left, piece = int(m.group(1)), int(m.group(2))
        keep = left / piece if piece else 0
        if keep >= FIT_KEEP_MIN:
            return 'room budget: decimate the piece to %d triangles (keeps %.0f%%)' % (left, 100 * keep)
        return 'room budget: %d left for a %d-triangle piece keeps %.0f%% (< %.0f%%): free triangles in the room first' % (
            left, piece, 100 * keep, 100 * FIT_KEEP_MIN)
    m = re.search(r'largest side ([0-9.]+).*?\[([0-9.]+),\s*([0-9.]+)\]', s)
    if m:
        return 'size %s m outside [%s, %s]: scale the piece (height) or choose another class' % m.groups()
    if 'palette' in s:
        return 'colours: use pack roles (never RGB); import re-materials to the nearest role'
    if 'non-manifold' in s or 'inconsistently wound' in s or 'boundary edges' in s:     # STYLEENGINE-2
        return ('topology: two closed parts share exact corner positions (two halves meeting face to face, a box '
                'sitting exactly on another): let them overlap a little (move one 1-2 cm into the other) instead of '
                'touching exactly; flat sheets (sails, flags) as card(), or as a thin beam to see both sides')
    return ''


def _gate_summary(built):
    tex = built.get('texture_fidelity') or {}
    return {'bible': bool((built.get('screen') or {}).get('ok')), 'file': all(v.get('ok') for v in (built.get('validation') or {}).values()),
            'structure': bool((built.get('structure') or {}).get('ok')), 'texture': bool(tex.get('ok')),
            'determinism': bool((built.get('determinism') or {}).get('ok'))}


def measure(built):
    tex = built.get('texture_fidelity') or {}
    per = tex.get('per_texture') or {}
    return {'triangles': built.get('tri_count'), 'texture_energy_median': (tex.get('set') or {}).get('median_hf'),
            'texture_energy_max': max((r.get('hf_energy', 0) for r in per.values()), default=None),
            'roles': sorted(per), 'conform': (built.get('meta') or {}).get('conform'),
            'texture_conform': (built.get('meta') or {}).get('texture_conform')}


# ------------------------------------------------------------------------------------------ sandboxed child
def _python(python_path=''):
    from .runner import locate
    return locate('python', python_path)


def run_child(root, req, *, python_path='', script=False):
    """Run styleengine_child.py under runner.Runner (no network, writes only in the project). Scripts also get the
    read-confined profile (project, bundle, interpreter). Returns the child's result dict."""
    from .runner import Runner
    from .safety import fail
    p = _project(root)
    key = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:24]
    stage_rel = '.maker/local/styleengine/%s/%s' % (req['mode'], key)
    stage = p.path(stage_rel)
    stage.mkdir(parents=True, exist_ok=True)
    req = dict(req, out=str(stage / 'out.obj'), result=str(stage / 'result.json'))
    p.write_json(stage_rel + '/request.json', req)
    if (stage / 'result.json').is_file():
        (stage / 'result.json').unlink()
    py = _python(python_path)
    if script and sys.platform != 'darwin':
        fail('sandbox_unavailable', 'builder scripts run only where the read/write/network sandbox exists (macOS here); '
             'use a recipe (JSON) instead')
    reads = [str(ROOT), str(Path(py).parent.parent), str(Path(py).resolve().parent.parent)] if script else None
    argv = [py, '-I', '-B', str(CHILD), str(stage / 'request.json')]
    proc = Runner(p).run(argv, p.root, timeout=120, reads=reads) if reads else Runner(p).run(argv, p.root, timeout=120)
    res = json.loads((stage / 'result.json').read_text(encoding='utf-8')) if (stage / 'result.json').is_file() else {
        'ok': False, 'error': 'child failed: ' + (proc['stderr'] or proc['stdout'])[-400:].replace('\n', ' ')}
    res['stage'] = stage_rel
    res['child_seconds'] = proc['elapsed_seconds']
    return res


def store_mesh(root, obj_path):
    """Copy a child's OBJ into the content-addressed assets/meshes/<sha256>.obj; returns the sha256."""
    p = _project(root)
    raw = Path(obj_path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rel = 'assets/meshes/%s.obj' % sha
    if not p.path(rel).is_file():
        p.write_bytes(rel, raw)
    return sha


def mesh_recipe(rid, sha, cls, role='body', conform=None, licence='CC0-1.0', kinds=None, nodes=None):
    """One `mesh` operation per content-addressed part (a list keeps a file's nodes as separate recipe nodes); a
    part's kind (shell/card: open surfaces by the source's own rules) rides along, solid by default; a builder
    group's name (STYLEENGINE-2) names its node."""
    shas = [sha] if isinstance(sha, str) else list(sha)
    kinds = list(kinds or []) + ['solid'] * len(shas)
    names = list(nodes or []) + [None] * len(shas)
    ops = [{'primitive': 'mesh', 'role': role, 'args': dict({'sha256': h}, **({'kind': k} if k != 'solid' else {}),
                                                            **({'node': n} if n else {}))}
           for h, k, n in zip(shas, kinds, names)]
    return {'format': 'hermes64-recipe/1', 'id': rid, 'class': cls, 'licence': licence, 'operations': ops,
            'conform': dict({'max_tris': CLASS_TRIS.get(cls, 300)}, **(conform or {}))}


def store_parts(root, res):
    """The child's per-node OBJ parts -> content-addressed project meshes; returns their sha256 list."""
    p = _project(root)
    return [store_mesh(p.root, p.path(res['stage']) / part['file']) for part in res['parts']]


def pack_dict(root, pack_id):
    from . import gen_tools
    return gen_tools.resolve_pack(root, pack_id).d


def _pack_file(root, pack_id):
    from . import gen_tools
    return str(gen_tools.resolve_pack(root, pack_id).path)


def _plain(text):
    """The descriptive words of a brief: licence ids, rights phrases and sizes removed."""
    t = LICENCE.sub(' ', str(text or ''))
    t = OWN.sub(' ', t)
    return re.sub(r'\d+(?:\.\d+)?\s*(m|metres|meters|metre|meter|cm|tris|triangles)\b', ' ', t)


def _class_for(description, size_m=None):
    data = load()
    _r, info = compose(_plain(description) or 'object', None, data)
    info['notes'] = [n for n in info['notes'] if not n.startswith('no form known')]
    cls = info['class'] if info['form'] != 'object' else None
    if cls is None and size_m:
        cls = next((c for c in CLASS_UP if size_m <= CLASS_EXTENT[c] * 0.95), 'structure')
    return cls or 'prop', info


def _size_from(text):
    m = re.search(r'(\d+(?:\.\d+)?)\s*(m|metres|meters|metre|meter|cm)\b', str(text or '').lower())
    if not m:
        return None
    v = float(m.group(1))
    return v / 100.0 if m.group(2) == 'cm' else v


# ------------------------------------------------------------------------------------------------ entry points
def make(root, pack_id, *, brief=None, source=None, out_id=None, python_path='', model='styleengine-words'):
    """Words, an agent recipe (.json) or an agent builder script (.py) -> a built, gated project recipe asset."""
    t0 = time.monotonic()
    p = _project(root)
    info = {}
    if source:
        rel = str(source)
        path = p.path(rel)
        if not path.is_file():
            raise StyleEngineError('no file at %s (paths are project-relative)' % rel)
        if rel.endswith('.py'):
            raw = path.read_bytes()
            if len(raw) > SCRIPT_BYTES:
                raise StyleEngineError('builder script larger than %d bytes' % SCRIPT_BYTES)
            stage_copy = 'assets/scripts/%s.py' % hashlib.sha256(raw).hexdigest()
            p.write_bytes(stage_copy, raw)
            res = run_child(p.root, {'mode': 'script', 'script': str(p.path(stage_copy))}, python_path=python_path,
                            script=True)
            if not res.get('ok'):
                return {'ok': False, 'error': 'builder script refused: ' + str(res.get('error')), 'stage': res['stage'],
                        'hints': [script_hint(res.get('error'))]}
            if res.get('parts'):           # STYLEENGINE-2: one node per group / kind (solid, shell, card)
                sha = store_parts(p.root, res)
                kinds = [x.get('kind', 'solid') for x in res['parts']]
                if len(sha) == 1:
                    sha = sha[0]
            else:
                sha, kinds = store_mesh(p.root, p.path(res['stage']) / 'out.obj'), None
            cls, info = _class_for(brief or Path(rel).stem.replace('_', ' '), None)
            cls = _fit_class(cls, res.get('bounds_m'), _design_record(p, out_id))       # STYLEENGINE-2
            rid = out_id or slug(brief or Path(rel).stem, 'sc')
            recipe = mesh_recipe(rid, sha, cls, kinds=kinds, nodes=[x.get('group') for x in res.get('parts', [])])
            info['size_m'] = _size(res.get('bounds_m'))
            info['groups'] = [x.get('group') for x in res.get('parts', []) if x.get('group')]
            info.update(script_sha256=hashlib.sha256(raw).hexdigest(), mesh_sha256=sha, raw_triangles=res['triangles'])
            model = 'agent-script'
        elif rel.endswith('.json'):
            from . import gen_tools
            recipe = gen_tools.decode(path.read_bytes())
            if not isinstance(recipe, dict):
                raise StyleEngineError('recipe JSON must be an object')
            recipe = dict(recipe)
            recipe.setdefault('conform', {'max_tris': CLASS_TRIS.get(recipe.get('class'), 300)})
            if out_id:
                recipe['id'] = out_id
            model = 'agent-recipe'
        else:
            raise StyleEngineError('make takes a builder script (.py) or a recipe (.json); files to import use action import')
    else:
        if not brief:
            raise StyleEngineError('make needs brief (the words) or recipe (a .json recipe or .py builder script)')
        recipe, info = compose(brief, pack_dict(p.root, pack_id))
        if out_id:
            recipe['id'] = out_id
        if info.get('fit') != 'known':
            # STYLEENGINE-2: the composer does not truly depict these words: nothing generic is built; the agent
            # designs it (builder script, recipe or file) with the record's examples and submits it with make
            from . import needs_design as ND
            rec = ND.record(brief, brief, info, named=True, project=p.root.name, pack=pack_id,
                            design_id=out_id or slug(brief, 'ff'))
            return {'ok': False, 'needs_design': rec, 'id': rec['id'], 'info': info,
                    'error': 'needs design: %s' % info.get('why'), 'total_seconds': round(time.monotonic() - t0, 2)}
    prev = _previous(p, recipe['id'])                                                    # STYLEENGINE-2: revise
    row = build_recipe(p.root, recipe, pack_id, model=model, want=brief or str(source), python_path=python_path)
    row.update(info=info, total_seconds=round(time.monotonic() - t0, 2))
    if row['ok'] and model == 'agent-script':
        _annotate_provenance(p.root, row['file'], {'script_sha256': info['script_sha256'], 'model': 'agent-script',
                                                   'made_by': 'user/agent generated, builder script sha256'})
    if row['ok']:
        row['version'] = _keep_version(p, row['recipe'], row, prev, source)
        row['design_for'] = _link_design(p, row['recipe'], row)
    elif prev is not None:
        gen_restore(p, prev)                    # a refused revision keeps the last good recipe in place
    return row


VERSIONS_KEPT = 5


def _previous(p, rid):
    path = p.path('recipes/%s.json' % rid)
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None


def gen_restore(p, recipe):
    from . import gen_tools
    p.write_bytes('recipes/%s.json' % recipe['id'], gen_tools.canonical(recipe) + b'\n')


def _keep_version(p, recipe, row, prev, source):
    """Version history per id (last 5): assets/designs/<id>/v<N>.json (the recipe) + history.json (numbers)."""
    rid = recipe['id']
    rel = 'assets/designs/%s' % rid
    hist = p.read_json(rel + '/history.json') if p.path(rel + '/history.json').is_file() else {'id': rid, 'versions': []}
    if not hist['versions'] and prev is not None and prev != recipe:
        p.write_json(rel + '/v0.json', prev)
        hist['versions'].append({'version': 0, 'recipe': rel + '/v0.json', 'note': 'the recipe before the first make '
                                 '(a create-flow placeholder or composed piece)'})
    n = max([v['version'] for v in hist['versions']] + [0]) + 1
    p.write_json('%s/v%d.json' % (rel, n), recipe)
    m = row.get('measure') or {}
    hist['versions'].append({'version': n, 'recipe': '%s/v%d.json' % (rel, n), 'file': row.get('file'),
                             'triangles': m.get('triangles'), 'texture_energy': m.get('texture_energy_median'),
                             'source': str(source) if source else 'words', 'model': row.get('model'),
                             'at': time.strftime('%Y-%m-%dT%H:%M:%S')})
    while len(hist['versions']) > VERSIONS_KEPT:
        old = hist['versions'].pop(0)
        for rel_old in (old['recipe'], old['recipe'][:-len('.json')] + '.png'):     # + its preview sheet
            if p.path(rel_old).is_file():
                p.path(rel_old).unlink()
    p.write_json(rel + '/history.json', hist)
    return {'version': n, 'history': rel + '/history.json', 'kept': [v['version'] for v in hist['versions']],
            'rollback': 'make id=%s recipe=%s/v<N>.json' % (rid, rel)}


def _design_record(p, rid):
    """The create flow's needs_design record for this recipe id, if any."""
    if not rid:
        return None
    for rel in ('create/needs_design.json', 'create/assets.json'):
        if p.path(rel).is_file():
            doc = p.read_json(rel) or {}
            recs = doc.get('records') if rel.endswith('needs_design.json') else (doc.get('craft') or {}).get('needs_design')
            hit = next((r for r in recs or [] if r.get('id') == rid), None)
            if hit:
                return hit
    return None


def _link_design(p, recipe, row):
    """A design submitted for a needs_design id goes into create/candidates.json under that name, so the next
    create_flow run builds it in place of the placeholder (same id, same slot)."""
    rec = _design_record(p, recipe['id'])
    if rec is None:
        return None
    cands = p.read_json('create/candidates.json') if p.path('create/candidates.json').is_file() else {}
    cands[rec['name']] = {'recipe': recipe, 'model': 'agent-design', 'needs_design': recipe['id'],
                          'version': (row.get('version') or {}).get('version')}
    p.write_json('create/candidates.json', cands)
    return {'name': rec['name'], 'candidates': 'create/candidates.json',
            'next': 'cd <plugin> && python3 -B -m adventure_maker.create_flow run --name %s (assets and rooms run again; '
                    'the placeholder is replaced in place)' % p.root.name}


def _size(bounds):
    if not bounds or len(bounds) != 6:
        return None
    return [round(bounds[i + 3] - bounds[i], 3) for i in range(3)]


def _fit_class(cls, bounds, rec=None):
    """A builder script's class: the needs_design guess or the composer's, moved up when the mesh is bigger."""
    size = _size(bounds)
    want = (rec or {}).get('budget', {}).get('class') or cls
    if not size:
        return want
    big = max(size)
    if want in CLASS_EXTENT and big <= CLASS_EXTENT[want] * 0.95:
        return want
    return next((c for c in CLASS_UP if big <= CLASS_EXTENT[c] * 0.95), 'structure')


def script_hint(error):
    s = str(error or '')
    if 'unknown role' in s:
        return 'roles are pack palette roles: body, body_alt, trim, frame, wood, bark, stone, wall, metal, chrome, glass, light, screen, fabric, rope, foliage, cap, flower, fur, hull, band'
    if 'emitted nothing' in s:
        return 'end the script with emit(part, ...)'
    if 'not allowed' in s or 'not supported' in s or 'unknown name' in s:
        return 'only the builder API, math and plain Python (no imports, files or attributes); see %s' % BUILDER_REF_PATH
    return 'see %s for the API and two worked examples' % BUILDER_REF_PATH


BUILDER_REF_PATH = 'skills/hermes64-generators/references/builder-api.md'


def _annotate_provenance(root, file, extra, converted=None):
    from . import provenance
    doc = provenance.load(root)
    row = next((r for r in doc['assets'] if r['file'] == file), None)
    if row is None:
        return
    row = dict(row, **extra)
    if converted:
        row.update(source='converted', converted_from=converted['from'], rights_declared=True)
    provenance.record(root, row)


LICENCE = re.compile(r'\b(CC0-1\.0|CC0|MIT|Apache-2\.0|BSD-[23]-Clause|CC-BY-4\.0|CC-BY-SA-4\.0|CC-BY-NC-4\.0|CC-BY-NC-SA-4\.0)\b', re.I)
OWN = re.compile(r"\b(my own|i made|i own|mine|made by me|my model|my file|my texture|own work)\b", re.I)


def rights_from(brief):
    """(licence, declaration) from the user's own words; None when they do not declare rights."""
    text = str(brief or '')
    m = LICENCE.search(text)
    if m:
        lic = m.group(1).upper().replace('CC0', 'CC0-1.0').replace('CC0-1.0-1.0', 'CC0-1.0')
        lic = {'MIT': 'MIT'}.get(lic, lic)
        return lic.replace('CLAUSE', 'Clause').replace('APACHE', 'Apache'), text[:300]
    if OWN.search(text):
        return 'LicenseRef-Private', text[:300]
    return None


def import_file(root, pack_id, path, *, brief='', textures=(), out_id=None, python_path=''):
    """The user's own GLB/OBJ (+ PNG/JPG) -> role-mapped project mesh -> conformed recipe asset."""
    t0 = time.monotonic()
    p = _project(root)
    rights = rights_from(brief)
    if rights is None:
        raise StyleEngineError('import needs your rights in brief, e.g. "my own model, CC0-1.0" (recorded as declared, '
                               'not verified)')
    src = p.path(str(path))
    if not src.is_file() or src.suffix.lower() not in ('.glb', '.obj'):
        raise StyleEngineError('import takes a project-relative .glb or .obj file')
    raw = src.read_bytes()
    if len(raw) > IMPORT_BYTES:
        raise StyleEngineError('file larger than %d bytes' % IMPORT_BYTES)
    for t in textures:
        if not p.path(str(t)).is_file() or Path(str(t)).suffix.lower() not in ('.png', '.jpg', '.jpeg'):
            raise StyleEngineError('textures must be project-relative PNG/JPG files')
    size = _size_from(brief)
    cls, info = _class_for(brief, size)
    lo = {'prop': 0.03, 'furniture': 0.15, 'furniture_large': 0.3, 'structure': 0.5, 'arch': 0.1, 'building': 2.0,
          'flora': 0.05, 'vehicle': 0.5}.get(cls, 0.1)
    data = load()
    req = {'mode': 'mesh', 'source': str(src), 'pack': _pack_file(p.root, pack_id), 'size_m': size,
           'class_range': [lo, CLASS_EXTENT.get(cls, 40.0)], 'textures': [str(p.path(str(t))) for t in textures],
           'candidates': data['candidates'] + ['glass', 'light', 'screen', 'metal', 'chrome', 'rope', 'water', 'ice']}
    res = run_child(p.root, req, python_path=python_path)
    if not res.get('ok'):
        return {'ok': False, 'error': 'import refused: ' + str(res.get('error')), 'stage': res['stage']}
    sha = store_parts(p.root, res)
    rid = out_id or slug(_plain(brief) or src.stem, 'im')
    lic, said = rights
    recipe = mesh_recipe(rid, sha, cls, kinds=[x.get('kind', 'solid') for x in res['parts']])
    prev = _previous(p, rid)                                                             # STYLEENGINE-2
    row = build_recipe(p.root, recipe, pack_id, model='user-import', want=brief or src.name, python_path=python_path)
    row.update(info=dict(info, mesh_sha256=sha, child=res), total_seconds=round(time.monotonic() - t0, 2))
    if row['ok']:
        _annotate_provenance(p.root, row['file'], {'declared_by_user': said, 'licence': lic},
                             converted={'from': {'name': src.name, 'sha256': hashlib.sha256(raw).hexdigest(),
                                                 'licence': lic}})
        row['version'] = _keep_version(p, row['recipe'], row, prev, path)
        row['design_for'] = _link_design(p, row['recipe'], row)
    elif prev is not None:
        gen_restore(p, prev)
    return row


def conform_asset(root, pack_id, glb, *, brief='', out_id=None, max_tris=None, extra=None, python_path='', cls=None):
    """An existing GLB in the project (a recipe output, a kit piece) -> a derived recipe (mesh op + conform)."""
    p = _project(root)
    src = p.path(str(glb)) if not Path(str(glb)).is_absolute() else Path(str(glb))
    if not src.is_file():
        raise StyleEngineError('no GLB at %s' % glb)
    target = max_tris or (int(re.search(r'(\d+)\s*(tris|triangles)', brief).group(1))
                          if re.search(r'(\d+)\s*(tris|triangles)', str(brief)) else None)
    res = run_child(p.root, {'mode': 'mesh', 'source': str(src), 'pack': _pack_file(p.root, pack_id),
                             'candidates': load()['candidates'] + ['glass', 'light', 'screen', 'metal', 'chrome', 'rope',
                                                                   'water', 'ice', 'roof', 'door', 'step', 'floor']},
                    python_path=python_path)
    if not res.get('ok'):
        return {'ok': False, 'error': 'conform refused: ' + str(res.get('error')), 'stage': res['stage']}
    sha = store_parts(p.root, res)
    if cls is None:
        cls, _info = _class_for(brief or src.stem, res.get('size_m'))
    conform = dict(extra or {})
    if target:
        conform['max_tris'] = int(target)
    rid = out_id or slug(_plain(brief) or src.parent.name, 'cf')
    recipe = mesh_recipe(rid, sha, cls, conform=conform, kinds=[x.get('kind', 'solid') for x in res['parts']])
    row = build_recipe(p.root, recipe, pack_id, model='styleengine-conform', want=brief or str(glb), python_path=python_path)
    row.update(info={'mesh_sha256': sha, 'child': res, 'source': str(glb)})
    return row


def report_lines(row):
    """Short plain lines for a tool reply."""
    if not row.get('ok'):
        return ['not made: ' + '; '.join(row.get('errors') or [row.get('error', 'unknown')])[:300]] + \
            ['hint: ' + h for h in row.get('hints', [])]
    m = row.get('measure') or {}
    c = m.get('conform') or {}
    lines = ['made %s: %s triangles (%s in), texture energy %s (rule 0.050), roles %s, gates %s, %.1f s' % (
        row['id'], m.get('triangles'), c.get('in_tris', m.get('triangles')), m.get('texture_energy_median'),
        ', '.join(m.get('roles') or []), 'all passed' if all((row.get('gates') or {}).values()) else row.get('gates'),
        row.get('total_seconds') or row.get('seconds') or 0)]
    for n in (row.get('info') or {}).get('notes', []):
        lines.append('note: ' + n)
    return lines


# --------------------------------------------------------------------------------------- create-flow helpers
SKIP_WANTS = ('character: ', 'sounds and music')
ENERGY = ('texture energy', 'hf energy', 'noisy texture')


STOP = {'a', 'an', 'the', 'and', 'or', 'with', 'on', 'in', 'of', 'to', 'at', 'by', 'for', 'from', 'into', 'onto',
        'me', 'make', 'game', 'some', 'its', 'his', 'her', 'their', 'that', 'which', 'who', 'is', 'are', 'beside',
        'near', 'under', 'over', 'behind', 'inside', 'outside', 'across', 'toward', 'towards', 'one', 'two', 'three'}


# Is a brief word a THING to make? The brief keeps loose words it could not classify ("unrecognised"); verbs, adverbs
# and pronouns land there too. A word is made only when it is a recognised prop, a multi-word phrase, or stands in a
# noun position in the prompt (a determiner before it, a boundary after it). Abstract and ground words are not props.
FUNCTION = STOP | {'then', 'first', 'last', 'next', 'ahead', 'whole', 'she', 'he', 'they', 'it', 'we', 'you', 'i', 'him',
                   'them', 'us', 'must', 'can', 'will', 'would', 'should', 'could', 'may', 'might', 'shall', 'do',
                   'does', 'did', 'be', 'been', 'being', 'was', 'were', 'has', 'have', 'had', 'not', 'very', 'also',
                   'just', 'only', 'even', 'still', 'again', 'once', 'here', 'there', 'where', 'when', 'while', 'before',
                   'after', 'during', 'until', 'above', 'below', 'besides', 'around', 'through', 'up', 'down', 'off',
                   'out', 'away', 'back', 'along', 'every', 'each', 'all', 'both', 'few', 'many', 'much', 'more', 'most',
                   'other', 'another', 'such', 'own', 'same', 'so', 'than', 'too', 'how', 'what', 'why', 'whose',
                   'this', 'these', 'those', 'my', 'your', 'our', 'new', 'old', 'big', 'small', 'little', 'top'}
DET = {'a', 'an', 'the', 'some', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'his',
       'her', 'its', 'their', 'my', 'your', 'our', 'this', 'that', 'these', 'those', 'every', 'each', 'no', 'many',
       'several', 'giant', 'huge'}
BOUNDARY = {'and', 'or', 'on', 'in', 'with', 'at', 'by', 'for', 'from', 'of', 'to', 'into', 'onto', 'near', 'beside',
            'under', 'over', 'behind', 'that', 'which', 'who', 'while', 'as', 'across', 'toward', 'towards', 'inside',
            'outside', 'atop', 'above', 'below', 'between', 'is', 'are', 'stands', 'sits', 'floats', 'hangs'}
VERBS = {'find', 'finds', 'found', 'seen', 'see', 'sees', 'look', 'looks', 'looking', 'walk', 'walks', 'climb', 'climbs',
         'stand', 'run', 'runs', 'go', 'goes', 'gone', 'come', 'comes', 'make', 'makes', 'made', 'take', 'takes', 'taken',
         'give', 'gives', 'given', 'know', 'known', 'show', 'shown', 'hold', 'held', 'keep', 'kept', 'leave', 'left',
         'lose', 'lost', 'build', 'built', 'open', 'opens', 'guide', 'guides', 'search', 'searching', 'hunt', 'hunting',
         'repair', 'repairing', 'brew', 'brews', 'near', 'nears', 'help', 'helps', 'save', 'saves', 'fight', 'fights',
         'need', 'needs', 'want', 'wants', 'try', 'tries', 'get', 'gets', 'got', 'play', 'plays', 'live', 'lives'}
NOT_THINGS = {'way', 'love', 'time', 'day', 'night', 'life', 'world', 'place', 'home', 'journey', 'hope', 'path', 'road',
              'street', 'ground', 'floor', 'sky', 'bottom', 'side', 'end', 'start', 'middle', 'game', 'story',
              'adventure', 'quest', 'level', 'area', 'land', 'kind', 'thing', 'things', 'stuff', 'lot', 'bit', 'part',
              'dream', 'memory', 'fear', 'courage', 'magic', 'power', 'light', 'darkness', 'storm', 'weather', 'wind',
              'rain', 'snow', 'fog', 'mist', 'air', 'water', 'fire', 'sound', 'music', 'voice', 'name', 'friend',
              'friends', 'enemy', 'enemies', 'player', 'hero', 'people', 'crew', 'team', 'family', 'help', 'hint',
              'hints', 'clue', 'clues', 'secret', 'secrets', 'treasure', 'top', 'view', 'distance', 'horizon',
              'island', 'city', 'town', 'village', 'jungle', 'forest', 'desert', 'ocean', 'sea', 'planet', 'kingdom',
              'valley', 'mountains', 'countryside', 'wilderness', 'space'}


def noun_position(prompt, word):
    """True when `word` (or its plural) follows a determiner (within four words, through describing words) and is
    followed by the end, punctuation or a boundary word: 'a clockwork heart on', 'three zorblaxes in'."""
    toks = re.findall(r"[a-z][a-z']*|[^a-z\s]", str(prompt or '').lower())    # 'stained-glass' -> stained - glass
    forms = {word, word + 's', word + 'es'}
    for i, t in enumerate(toks):
        if t not in forms:
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else ''
        if nxt == '-' or nxt and re.match(r'^[a-z]', nxt) and nxt not in BOUNDARY:
            continue
        for j in range(i - 1, max(i - 7, -1), -1):
            if toks[j] == '-':                    # inside a hyphenated describing word ('a stained-glass window')
                continue
            if toks[j] in DET:
                return True
            if not re.match(r'^[a-z]', toks[j]) or toks[j] in FUNCTION or toks[j] in BOUNDARY or toks[j] in VERBS:
                break
    return False


def unknown_noun(want, prompt, data=None):
    """STYLEENGINE-2: 'an old CRT television': a size/age word (old, new, big, small, little) broke the noun test of
    is_thing; when the style engine does not know the thing, it is a thing (needs design), never a silent skip."""
    from . import needs_design as ND
    w = want.lower()
    if len(w.split()) != 1 or w in NOT_THINGS or w in FUNCTION or w in VERBS or w.endswith('ly'):
        return False
    plain = re.sub(r"\b(old|new|big|small|little)\b", ' ', str(prompt or '').lower())
    return noun_position(plain, w) and ND.assess(phrase(prompt, w), data)['fit'] != 'known'


def is_thing(want, prompt, brief=None):
    """Should the free-form path make this want? (see FUNCTION/DET/BOUNDARY/VERBS/NOT_THINGS above)"""
    words = want.lower().split()
    if not words or words[-1] in FUNCTION or words[-1] in VERBS:
        return False
    if len(words) > 1:
        return True                                 # a phrase the brief found ('floating island', 'gear machine')
    w = words[0]
    if w in NOT_THINGS or w.endswith('ly'):
        return False
    brief = brief or {}
    props = {p.get('want') for p in brief.get('props', []) if p.get('source') in ('prompt', 'default')}
    if w in props and w not in set(brief.get('unrecognised') or []):
        return True                                 # a prop the brief recognised (or a setting default)
    toks = set(re.findall(r"[a-z][a-z']*", str(prompt or '').lower()))
    if not toks & {w, w + 's', w + 'es'}:
        return True                                 # a setting/default want, not a loose word of the prompt
    return noun_position(prompt, w)


def phrase(prompt, want):
    """The want with the up-to-three describing words the user put before it ('floating lantern fish')."""
    words = re.findall(r"[a-z][a-z'-]*|[^a-z\s]", str(prompt or '').lower())
    target = want.lower().split()
    n = len(target)
    for i in range(len(words) - n + 1):
        if words[i:i + n] == target:
            j = i
            while j > 0 and i - j < 3 and re.match(r'^[a-z][a-z-]*$', words[j - 1]) and words[j - 1] not in STOP:
                j -= 1
            return ' '.join(words[j:i + n])
    return want


def material_words():
    """Every material/modifier word the composer can show (styleengine.json materials)."""
    return {x for m in load()['materials'].values() for x in m.get('words', [])}


def identity_words():
    """Describing words that change WHAT the object is (bone, coral, mushroom, stained-glass, pirate...), as opposed to
    plain materials and light (wooden, stone, golden, crystal, glowing) that a library piece of that kind already
    shows in the pack palette: only these make the user's phrase beat the nearest catalogue kind."""
    plain = set(load().get('plain_materials', []))
    return {x for k, m in load()['materials'].items() if k not in plain for x in m.get('words', [])}


def _tokens(text):
    return re.findall(r"[a-z][a-z']*", str(text or '').lower())


def _inside_only(prompt, inner, outer):
    """Every occurrence of the word sequence `inner` in the prompt lies inside an occurrence of `outer`."""
    toks, a, b = _tokens(prompt), _tokens(inner), _tokens(outer)
    if not a or not b:
        return False
    spans = [range(i, i + len(b)) for i in range(len(toks) - len(b) + 1) if toks[i:i + len(b)] == b]
    hits = [i for i in range(len(toks) - len(a) + 1) if toks[i:i + len(a)] == a]
    return bool(hits) and all(any(i in sp and i + len(a) - 1 in sp for sp in spans) for i in hits)


def cover_parts(rows, candidates, made, crafted, prompt):
    """A brief row whose words only appear as describing words of a composed phrase ('coral' in 'a coral arch',
    'fish' in 'a floating lantern fish shopkeeper') is part of that one piece, not a separate library piece."""
    covered = []
    for m in sorted(made, key=lambda x: -len(_tokens(x['words']))):
        head = _tokens(m['want'])
        desc = _tokens(m['words'])[:-len(head)] if head else []
        if not desc or m['want'] in covered:
            continue
        for r in rows:
            w = r['want']
            if w == m['want'] or w in crafted or w in covered or r.get('status') == 'not covered' \
                    or w.startswith(SKIP_WANTS) or (w in candidates and not any(x['want'] == w for x in made)):
                continue
            wt = _tokens(w)
            inside = any(desc[i:i + len(wt)] == wt for i in range(len(desc) - len(wt) + 1))
            if inside and _inside_only(prompt, w, m['words']):
                r.update(status='not covered', why='part of "%s", made as one piece (%s)' % (m['words'], m['id']))
                candidates.pop(w, None)
                covered.append(w)
                m.setdefault('covers', []).append(w)
    made[:] = [m for m in made if m['want'] not in covered]
    return covered


def cover_with_parts(rows, candidates, made, needs, prompt):
    """STYLEENGINE-2: 'a grandfather clock with a swinging pendulum': a needs_design thing named in a 'with' clause right
    after another needs_design phrase is a part of that one design (the agent builds them together; a named group in
    the script can animate it later), not a second placeholder. Composed (known) pieces are untouched."""
    toks = _tokens(prompt)
    nd = lambda m: m.get('placeholder') or m.get('design')
    covered = []
    for m in [m for m in made if nd(m)]:
        wt = _tokens(m['words'])
        if m['want'] in covered or not wt:
            continue
        for i in range(len(toks) - len(wt)):
            if toks[i:i + len(wt)] != wt or toks[i + len(wt)] != 'with':
                continue
            tail = toks[i + len(wt) + 1:i + len(wt) + 5]
            for x in [x for x in made if x is not m and nd(x) and x['want'] not in covered]:
                xt = _tokens(x['want'])
                hit = next((j for j in range(len(tail) - len(xt) + 1) if tail[j:j + len(xt)] == xt), None)
                if hit is None:
                    continue
                full = ' '.join(wt + ['with'] + tail[:hit + len(xt)])
                covered.append(x['want'])
                m.setdefault('covers', []).append(x['want'])
                candidates.pop(x['want'], None)
                for r in rows:
                    if r['want'] == x['want']:
                        r.update(status='not covered', why='part of "%s", one design (%s)' % (full, m['id']))
                for n in needs:
                    if n['name'] == m['want']:
                        n['user_words'] = full
                        n.setdefault('parts', []).append(x['want'])
    made[:] = [m for m in made if m['want'] not in covered]
    needs[:] = [n for n in needs if n['name'] not in covered]
    return covered


def free_form(root, rows, candidates, craft, pack_id, prompt='', brief=None):
    """Brief wants with no library piece (missing, or only a partial stand-in) and no candidate are COMPOSED from
    their own words; the triangle budget is the only limit (the rooms stage places what fits). A composed piece that
    fails keeps the old stand-in path (create_flow checks craft['free_form'])."""
    from . import needs_design as ND
    pd = None
    data = load()
    crafted = {c['want'] for c in craft.get('pieces', [])}
    made, skipped, needs = [], [], []
    said = set(_tokens(prompt))
    for r in rows:
        w = r['want']
        unbound = r.get('status') == 'exists' and r.get('matches') == []   # a taxonomy kind with no piece to build
        cand = candidates.get(w)
        if isinstance(cand, dict) and cand.get('needs_design') and isinstance(cand.get('recipe'), dict) \
                and w not in crafted and not w.startswith(SKIP_WANTS):
            # STYLEENGINE-2: the agent's design for a needs_design name keeps the placeholder's id, so its slot
            words = phrase(prompt, w)
            made.append({'want': w, 'words': words, 'id': 'gen:' + cand['recipe']['id'], 'form': 'agent design',
                         'class': cand['recipe'].get('class'), 'was': r.get('status'), 'notes': [],
                         'design': cand['needs_design']})
            if set(_tokens(w)) <= said:
                made[-1]['named'] = True
            needs.append(dict(ND.record(w, words, dict(compose(words, None, data)[1]), named=True, pack=pack_id,
                                        design_id=cand['recipe']['id']), status='designed by the agent',
                              design_version=cand.get('version')))
            continue
        if w in candidates or w in crafted or w.startswith(SKIP_WANTS):
            continue
        words = phrase(prompt, w)
        # a library match by KIND for a word the user described further with words the composer can show ('bone
        # throne', 'coral arch', 'pirate ship wheel'): the user's own phrase wins over the nearest catalogue kind
        richer = (r.get('status') in ('exists', 'partial') and r.get('axis') in ('kind', 'free', 'genre+kind')
                  and len(words.split()) > len(w.split()) and noun_position(prompt, w.split()[-1])
                  and bool(set(_tokens(' '.join(words.split()[:-len(w.split())]))) & identity_words()))
        # STYLEENGINE-2: ... or with words that change what the library kind piece is ('a sailing ship' is not the
        # library's shuttle, 'a jellyfish lamp' is not its lantern): the closest library piece never stands in silently
        odd = (not richer and r.get('status') in ('exists', 'partial') and r.get('axis') in ('kind', 'free', 'genre+kind')
               and noun_position(prompt, w.split()[-1])
               and bool([x for x in ND.identity_unknown(_tokens(words)[:-1], data) if x in said]))
        richer = richer or odd
        if r.get('status') not in ('missing', 'partial') and not unbound and not richer:
            continue
        if r.get('status') == 'partial' and not richer and not is_thing(w, prompt, brief) or \
                r.get('status') == 'missing' and not is_thing(w, prompt, brief):
            if not unknown_noun(w, prompt, data):                         # STYLEENGINE-2
                skipped.append(w)
                continue
        pd = pd if pd is not None else pack_dict(root, pack_id)
        recipe, info = compose(words, pd)
        recipe['id'] = slug(w, 'ff')
        named = set(_tokens(w)) <= said              # the user's own words, not a setting default
        if info.get('fit') != 'known':
            named = all(t in said or t + 's' in said or t + 'es' in said for t in _tokens(w))   # plurals count
            # STYLEENGINE-2: the composer does not truly depict this: a needs_design record for the agent, and for a
            # thing the user named a clearly marked placeholder so the game still builds (never shown as the thing)
            closest = (r.get('matches') or [None])[0] if r.get('status') in ('exists', 'partial') else None
            needs.append(ND.record(w, words, info, named=named, pack=pack_id, design_id=recipe['id'],
                                   placeholder=('gen:' + recipe['id']) if named else None, library_closest=closest))
            if not named:
                continue
            candidates[w] = {'recipe': ND.placeholder_recipe(recipe['id'], info), 'model': ND.PLACEHOLDER_MODEL}
            made.append({'want': w, 'words': words, 'id': 'gen:' + recipe['id'], 'form': 'placeholder',
                         'class': candidates[w]['recipe']['class'], 'was': 'unbound' if unbound else r.get('status'),
                         'notes': [info.get('why', '')], 'placeholder': True, 'needs_design': recipe['id'],
                         'named': True})
            if richer and r.get('status') == 'exists':
                made[-1]['instead_of'] = (r.get('matches') or [None])[0]
            continue
        candidates[w] = {'recipe': recipe, 'model': 'styleengine-words'}
        made.append({'want': w, 'words': words, 'id': 'gen:' + recipe['id'], 'form': info['form'],
                     'class': info['class'], 'was': 'unbound' if unbound else r.get('status'), 'notes': info['notes']})
        if named:
            made[-1]['named'] = True
        if richer and r.get('status') == 'exists':
            made[-1]['instead_of'] = (r.get('matches') or [None])[0]
    wants = {r['want'] for r in rows}
    for w, cand in list(candidates.items()):
        # STYLEENGINE-2: a design for a record with no asset row (a creature character no body fits) is placed as a
        # static prop; the character's talking role stays with the public cast. The agent may also have named it the
        # older way ("<want>": "gen:<id>" for a recipe it made in this project).
        if w in wants or w in crafted:
            continue
        if isinstance(cand, str) and re.fullmatch(r'gen:[a-z0-9_]{1,64}', cand):
            rp = Path(root) / 'recipes' / (cand[4:] + '.json')
            try:
                rec = json.loads(rp.read_text(encoding='utf-8')) if rp.is_file() else None
            except ValueError:
                rec = None
            if not isinstance(rec, dict) or rec.get('id') != cand[4:]:
                continue
            cand = candidates[w] = {'recipe': rec, 'model': ND.DESIGN_MODEL, 'needs_design': cand[4:]}
        if not (isinstance(cand, dict) and cand.get('needs_design') and isinstance(cand.get('recipe'), dict)):
            continue
        rows.append({'want': w, 'status': 'missing', 'axis': 'free', 'matches': [],
                     'why': 'designed by the agent as a static prop (%s)' % cand['needs_design']})
        made.append({'want': w, 'words': w, 'id': 'gen:' + cand['recipe']['id'], 'form': 'agent design',
                     'class': cand['recipe'].get('class'), 'was': 'character', 'named': True,
                     'notes': ['static prop: no rig moves it'], 'design': cand['needs_design']})
        needs.append(dict(ND.record(w, w, {'fit': 'unknown', 'form': 'creature', 'class': cand['recipe'].get('class'),
                                           'why': 'no creator64 body or rig can be it'}, named=True, pack=pack_id,
                                    role='character', design_id=cand['recipe']['id']),
                          status='designed by the agent', design_version=cand.get('version'),
                          note='a static prop in the room; the talking character is still the public cast'))
    cover_with_parts(rows, candidates, made, needs, prompt)              # STYLEENGINE-2 (needs_design pieces only)
    cover_parts(rows, candidates, made, crafted, prompt)
    covered = {m['want'] for m in made}
    needs = [n for n in needs if n['name'] in covered or not n.get('named_by_user') or n['status'] != 'placeholder in the game']
    if made:
        craft = dict(craft, free_form=made)
    if made and skipped:
        craft['free_form_skipped'] = skipped        # loose words that are not things (verbs, adverbs, abstract nouns)
    if needs:
        craft = dict(craft, needs_design=needs)
        # a skipped word that is part of a needs_design phrase ('ferris' in 'ferris wheel') is not a separate thing
        skipped = [s for s in skipped if not any(s in (n.get('user_words') or '').split() for n in needs)]
        if skipped:
            craft['free_form_skipped'] = skipped
        else:
            craft.pop('free_form_skipped', None)
    return rows, candidates, craft


def energy_wall(row):
    """A failed row whose refusal (any attempt, or the reason) is the texture-energy rule."""
    att = row.get('attempts') if isinstance(row.get('attempts'), list) else []
    text = ' '.join([str(row.get('reason', ''))] + [' '.join(a.get('errors') or []) for a in att]).lower()
    return row.get('status') == 'failed' and any(w in text for w in ENERGY)


def conform_kit(root, kit_pack, row, gids, *, seed=0, mooded=False, python_path=''):
    """A library piece refused for texture energy is rebuilt with the per-asset texture conform its failed build
    suggested (conform_hint: least extra soften/dither that the unchanged rule passes, measured on its own textures).
    Tries the first match, then the alternatives that failed, in order. Returns the new row or the old one."""
    from . import gen_tools
    tried = []
    for gid in gids:
        first = gen_tools.build(root, gid, kit_pack, seed=seed, sweep=False, python_path=python_path)
        hint = first.get('conform_hint') or {}
        if first.get('ok') or not hint.get('conform'):
            tried.append({'id': gid, 'errors': first.get('errors', [])[:2], 'conform': None})
            continue
        built = gen_tools.build(root, gid, kit_pack, seed=seed, sweep=False, python_path=python_path,
                                conform=hint['conform'])
        tried.append({'id': gid, 'conform': hint['conform'], 'ok': built['ok'], 'errors': built['errors'][:2]})
        if built['ok']:
            before = (hint.get('before') or {}).get('median_hf')
            after = ((built.get('texture_fidelity') or {}).get('set') or {}).get('median_hf')
            return dict(row, status='remapped' if mooded else 'existed', id=gid, kit_id=gid, source='kit',
                        file=built['file'], sha256=built['sha256'], tri_count=built['tri_count'], licence='MIT',
                        model='native-library', conformed={'texture': hint['conform'], 'median_hf_before': before,
                                                           'median_hf_after': after},
                        reason='texture energy %s > 0.050 conformed (%s): now %s' % (
                            before, ', '.join('%s %s' % kv for kv in sorted(hint['conform'].items())), after))
    return dict(row, conform_attempts=tried)


def fit_record(root, rooms_doc, log):
    """Decimated pieces go in the rooms record; attempts the gates refused stay in the project's local stage log
    (the not-placed row keeps its own number), so a game where no fit was made keeps its rooms file unchanged."""
    placed = {x.get('id') for x in rooms_doc.get('placed', [])}
    made = [e for e in log if e.get('made') and e.get('id') in placed]
    if made:
        rooms_doc['decimated'] = made
    failed = [dict(e, made=False, note='decimated, but no spot for it in the room') if e.get('made') else e
              for e in log if not (e.get('made') and e.get('id') in placed)]
    if failed:
        _project(root).write_json('.maker/local/styleengine/fit-attempts.json', {'attempts': failed})


def fitter(root, bundle, assets, bdoc, presets, kit_pack, log, python_path=''):
    """dress(fit=...): a piece over a room's remaining triangles is decimated to fit when it keeps >= 40% of them."""
    rows = {r.get('id'): r for r in assets.get('rows', []) if r.get('id')}

    def fit(it, budget):
        if it['tris'] <= 0 or budget < FIT_KEEP_MIN * it['tris'] or budget < 12:
            return None
        gid = it['id']
        row = rows.get(gid, {})
        b = (bdoc.get('assets') or {}).get(gid)
        if isinstance(b, dict) and b.get('glb'):
            src = str(Path(bundle) / b['glb'])
        elif row.get('file'):
            src = row['file']
        else:
            return None
        cls = row.get('class') if row.get('class') in CLASS_TRIS else None
        res = conform_asset(root, kit_pack, src, brief=it['want'], max_tris=int(budget), cls=cls,
                            out_id=slug('fit %s %d' % (gid.replace('gen:', '').replace('.', ' '), budget), ''),
                            python_path=python_path)
        entry = {'want': it['want'], 'from_id': gid, 'from_tris': it['tris'], 'budget': int(budget)}
        if not res.get('ok') or res['tri_count'] > budget:
            log.append(dict(entry, made=False, tris=res.get('tri_count'), errors=(res.get('errors') or [])[:2]))
            return None
        rid = res['id'][4:]
        if not any(p['id'] == 'cf_' + rid for p in presets):
            presets.append({'id': 'cf_' + rid, 'asset_id': res['id'], 'params_json': '{}'})
        log.append(dict(entry, made=True, id=res['id'], tris=res['tri_count']))
        return {'key': 'preset/cf_' + rid, 'id': res['id'], 'tris': res['tri_count'], 'mode': 'append',
                'fit_from': {'id': gid, 'tris': it['tris']}}
    return fit


def free_form_status(craft, rows):
    """Record on each composed piece whether the generator path made it (status, id, triangles, reason)."""
    by_want = {r['want']: r for r in rows}
    for c in craft.get('free_form', []):
        r = by_want.get(c['want'], {})
        if r.get('status') == 'generated' and str(r.get('id', '')).startswith('gen:ff_'):
            # STYLEENGINE-2: a placeholder is never "made"; an agent design is "designed"
            c.update(status='placeholder' if c.get('placeholder') else 'designed' if c.get('design') else 'made',
                     tri_count=r.get('tri_count'))
        else:
            c.update(status='not made', reason=' '.join(str(r.get('reason', '')).split())[:300],
                     stand_in=r.get('id') if r.get('status') in ('substituted', 'existed', 'remapped') else None)
    for n in craft.get('needs_design', []):
        r = by_want.get(n['name'], {})
        if n.get('placeholder') and not (r.get('status') == 'generated' and r.get('id') == n['placeholder']):
            n['status'] = ('library stand-in %s (placeholder: needs design)' % r['id']) if r.get('status') in (
                'substituted', 'existed', 'remapped') else 'not built: %s' % ' '.join(str(r.get('reason', '')).split())[:160]
        if n.get('placeholder') and r.get('tri_count'):
            n['budget']['placeholder_tris'] = r['tri_count']
    return craft
