"""Rig contract instances (rigs/<rig_id>/rig.json, schema contracts/rig/1.0.0.json): loading + stdlib checks."""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RIGS = REPO / 'rigs'
SCHEMA_ID = 'hermes64-rig/1.0.0'


class RigError(ValueError):
    pass


def skin_order(parents):
    """Joint order of the contract = depth-first pre-order from the root, children sorted by name (the order Blender's
    glTF exporter writes skin joints in)."""
    kids = {}
    roots = []
    for b, p in parents.items():
        if p is None:
            roots.append(b)
        else:
            kids.setdefault(p, []).append(b)
    out = []

    def visit(b):
        out.append(b)
        for c in sorted(kids.get(b, [])):
            visit(c)
    for r in sorted(roots):
        visit(r)
    return out


class Rig:
    def __init__(self, doc, path=None):
        self.doc = doc
        self.path = path
        self.id = doc['id']
        self.version = doc['version']
        self.kind = doc['kind']
        self.bones = [b['name'] for b in doc['bones']]
        self.parents = {b['name']: b['parent'] for b in doc['bones']}
        self.rest = {b['name']: tuple(b['rest_world']) for b in doc['bones']}
        self.rest_local = {b['name']: tuple(b['rest_translation']) for b in doc['bones']}
        self.clips = doc['clips']
        self.budgets = doc.get('budgets', {})
        self.seams = doc.get('seams', [])
        self.sockets = doc.get('sockets', [])
        self.limits = doc.get('joint_limits', {})
        self.proportions = doc.get('proportions', {})
        self.silhouette = doc.get('silhouette', {})
        self.dir = Path(path).parent if path else None

    @property
    def tag(self):
        return '%s@%s' % (self.id, self.version)

    def required_clips(self, combat=False):
        out = list(self.clips.get('required', []))
        if combat:
            out += list(self.clips.get('combat', []))
        return out

    def translation_bones(self):
        return list(self.clips.get('channels', {}).get('translation', []))

    def rotation_bones(self):
        rule = self.clips.get('channels', {}).get('rotation', '')
        if 'except root' in rule:
            return [b for b in self.bones if self.parents[b] is not None]
        return list(self.bones)


def check_doc(doc):
    """Stdlib structural check of a rig.json document -> list of problems."""
    probs = []

    def need(k, typ, where=doc, path=''):
        if k not in where:
            probs.append('missing %s%s' % (path, k))
            return False
        if not isinstance(where[k], typ):
            probs.append('%s%s has wrong type' % (path, k))
            return False
        return True
    if doc.get('schema') != SCHEMA_ID:
        probs.append('schema must be %s' % SCHEMA_ID)
    for k, t in (('id', str), ('version', str), ('kind', str), ('bones', list), ('clips', dict), ('skin', dict),
                 ('conventions', dict), ('budgets', dict)):
        need(k, t)
    if probs:
        return probs
    names = [b.get('name') for b in doc['bones']]
    if len(set(names)) != len(names):
        probs.append('duplicate bone names')
    parents = {b.get('name'): b.get('parent') for b in doc['bones']}
    roots = [n for n, p in parents.items() if p is None]
    if len(roots) != 1:
        probs.append('exactly one root bone required')
    for n, p in parents.items():
        if p is not None and p not in parents:
            probs.append('bone %s has unknown parent %s' % (n, p))
    if not probs and skin_order(parents) != names:
        probs.append('bones are not in contract joint order (DFS pre-order, children sorted by name)')
    for i, b in enumerate(doc['bones']):
        if b.get('index') != i:
            probs.append('bone %s index mismatch' % b.get('name'))
        for k in ('rest_translation', 'rest_world'):
            v = b.get(k)
            if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, (int, float)) for x in v)):
                probs.append('bone %s %s must be 3 numbers' % (b.get('name'), k))
    c = doc['clips']
    for k in ('required', 'fps', 'keys', 'interpolation', 'channels'):
        if k not in c:
            probs.append('clips.%s missing' % k)
    if c.get('fps') != 15 or c.get('keys') != 16 or c.get('interpolation') != 'STEP':
        probs.append('clips must be 15 fps, 16 keys, STEP')
    if doc['skin'].get('max_influences') != 4:
        probs.append('skin.max_influences must be 4')
    return probs


def list_rigs(root=None):
    root = Path(root or RIGS)
    return sorted(p.parent.name for p in root.glob('*/rig.json'))


def load_rig(rig, root=None):
    if isinstance(rig, Rig):
        return rig
    root = Path(root or RIGS)
    if isinstance(rig, (str, Path)) and str(rig).endswith('.json'):
        path = Path(rig)
    else:
        path = root / str(rig) / 'rig.json'
    if not path.is_file():
        raise RigError('unknown rig %r (no %s)' % (rig, path))
    doc = json.loads(path.read_text(encoding='utf-8'))
    probs = check_doc(doc)
    if probs:
        raise RigError('invalid rig %s: %s' % (path, '; '.join(probs)))
    return Rig(doc, path)
