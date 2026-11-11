"""Blender-free character export: function API behind adventure_maker.nbchars (docs/NBCHARS-API.md)."""
import dataclasses
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

from . import _BUILDERS
from . import select as SEL

REPO = Path(__file__).resolve().parents[2]
RESTRICTED = {'cameo_visor_01': 'real-person likeness: internal only, nothing public until cleared'}
COMBAT_ROOT_MOTION = 'none (root carries the vertical grounding offset only)'


class ExportError(RuntimeError):
    pass


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _gen(root=None):
    from . import gen
    return gen.load(root)


# ------------------------------------------------------------------ re-exports
def write_scene(scene, generator=None):
    from . import writer
    return writer.write_scene(scene, generator or writer.GENERATOR)


select_exporter = SEL.select_exporter
doctor_line = SEL.doctor_line


# ------------------------------------------------------------------ cast definitions (tools/export_cast.cast)
def cast_rows(G=None):
    G = G or _gen()
    polar, forest = G.pack('polar_pod'), G.pack('forest_village')
    rows = []
    for c in polar['character_cast']:
        rows.append(dict(id=c['id'], pack='polar_pod', kind='masked', params=c['params'], stance=c['stance'],
                         props=c['props'], animal=False))
    for pk, pn in ((polar, 'polar_pod'), (forest, 'forest_village')):
        for c in pk['face_cast']:
            rows.append(dict(id=c['id'], pack=pn, kind='face', params=c['params'], stance=c['stance'], props=c['props'],
                             animal=False))
    for c in forest.get('cameo_cast', []):
        rows.append(dict(id=c['id'], pack=c.get('pack', 'cameo_visor'), kind='visor', params=c['params'],
                         stance=c['stance'], props=c['props'], animal=False))
    for pk, pn in ((polar, 'polar_pod'), (forest, 'forest_village')):
        for c in pk['animal_cast']:
            rows.append(dict(id=c['id'], pack=pn, kind='animal', params=c['params'], stance='neutral', props=[],
                             animal=True))
    return rows


def combat_extras(G=None):
    CMB = (G or _gen()).core('combat')
    return {c: {'n64_combat': dict(CMB.PHASES[c], keys=16, fps=15, interpolation='STEP', root_motion=COMBAT_ROOT_MOTION)}
            for c in CMB.COMBAT_CLIPS}


# ------------------------------------------------------------------ builders
def character_bytes(row, *, combat=None, layout='published', G=None):
    """-> (glb bytes, scene). combat None = the published policy: the 16 non-visor humanoids carry the 6 combat
    clips; layout 'published' = r21 base (7 clips) + core/graft.py append (the published byte layout), 'single' =
    one export with all 13 clips (what a fresh Blender export of the donor gives)."""
    from . import assemble as A
    from . import writer as W
    G = G or _gen()
    PO = G.core('pose')
    if combat is None:
        combat = (not row['animal']) and row.get('kind') != 'visor'
    if row['animal'] or not combat:
        sc = A.character(row['pack'], row['params'], row['animal'], seed=row.get('seed', 19), stance=row.get('stance'),
                         props=row.get('props', []), G=G)
        return W.write_scene(sc), sc
    CMB = G.core('combat')
    extras = combat_extras(G)
    full = A.character(row['pack'], row['params'], False, seed=row.get('seed', 19), stance=row.get('stance'),
                       props=row.get('props', []), clips=PO.HCLIPS + CMB.COMBAT_CLIPS, G=G)
    for c in full.clips:
        if c.name in extras:
            c.extras = None
    if layout == 'single':
        sc = dataclasses.replace(full, clips=[dataclasses.replace(c, extras=extras.get(c.name)) for c in full.clips])
        return W.write_scene(sc), sc
    base = dataclasses.replace(full, clips=[c for c in full.clips if c.name in PO.HCLIPS])
    raw = G.core('graft').graft(W.write_scene(base), W.write_scene(full), CMB.COMBAT_CLIPS, extras)
    return raw, full


def enemy_bytes(pack, eid, G=None):
    from . import assemble as A
    from . import writer as W
    sc = A.enemy(pack, eid, G=G or _gen())
    return W.write_scene(sc), sc


def prop_bytes(pack, kind, G=None):
    from . import assemble as A
    from . import writer as W
    G = G or _gen()
    sc = A.weapon(pack, G=G) if kind == 'weapon' else A.projectile(pack, G=G)
    return W.write_scene(sc), sc


# ------------------------------------------------------------------ records
def _audit(G, raw, kind, n_clips):
    import tempfile
    GLB = G.core('glb')
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / 'x.glb'
        p.write_bytes(raw)
        return GLB.GLB(p).audit(kind=kind, n_clips=n_clips)


def character_record(G, row, raw, sc, rel):
    gates = G.core('gates')
    conn = G.core('connectivity')
    a = sc.info['generator']
    animal = row['animal']
    au = _audit(G, raw, 'quad' if animal else 'human', len(sc.clips) if not animal else 7)
    gm = gates.mesh(a)
    cn = conn.check_poses(a, sc.info['stance'] if not animal else None)
    if not cn['pass']:
        gm = dict(gm, **{'pass': False, 'errors': list(gm['errors']) + ['connectivity: ' + '; '.join(cn['fails'][:4])]})
    rec = {'id': row['id'], 'pack': row['pack'], 'kind': row['kind'], 'topology': sc.info['topology'],
           'skeleton': sc.info['skeleton'], 'stance': row.get('stance'), 'props': list(row.get('props', [])),
           'params': sc.info['params'], 'file': rel, 'sha256': au['sha256'], 'bytes': au['bytes'],
           'tris_glb_total': au['tris'], 'tris_body': gm['tris'], 'tris_body_glb': au['tris_body'],
           'tris_props': au['tris_props'], 'budget': {'body': '<700' if not animal else '<=300', 'prop_each': '<=200'},
           'mesh_vertices_glb': au['mesh_vertices'], 'joints': au['bones'], 'clips': [x['name'] for x in au['animations']],
           'clip_interpolation': sorted({i for x in au['animations'] for i in x['interpolation']}),
           'audit_pass': au['pass'], 'audit_errors': au['errors'], 'gate_pass': gm['pass'], 'gate_errors': gm['errors'],
           'geometry_sha256': gm['geometry_sha256'], 'topology_sha256': gm['topology_sha256'],
           'connectivity': {'pass': cn['pass'], 'max_gap_m': cn['max_gap'], 'max_at': cn['max_at'], 'tol_m': cn['tol']},
           'exporter': 'python'}
    if not animal and len(sc.clips) > 7:
        WP = G.core('weapon'); PO = G.core('pose')
        rec['combat'] = {'clips': [c for c in G.core('combat').COMBAT_CLIPS],
                         'weapon': WP.WEAPON_ID, 'weapon_grip': WP.grip_gltf(a.bones, PO.body_metrics(a))}
    if row['id'] in RESTRICTED:
        rec['restricted'] = RESTRICTED[row['id']]
    return rec


# ------------------------------------------------------------------ export entry points
def _check_exporter(exporter, settings):
    s = SEL.select_exporter(dict(settings or {}, character_exporter=exporter))
    if s['exporter'] is None:
        raise ExportError(s['reason'])
    return s


def export_cast(out_dir, *, only=None, exporter='auto', settings=None, layout='published', root=None, log=print):
    """The published cast (16 combat humanoids with 13 clips, the visor cameo when its restricted code is present,
    12 animals) -> <out>/<pack>/<id>.glb + <out>/manifest.json."""
    s = _check_exporter(exporter, settings)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if s['exporter'] == 'blender':
        return _blender_export(s['blender'], out, 'cast', only)
    G = _gen(root)
    only = set(only or [])
    man = []
    for row in cast_rows(G):
        if only and row['id'] not in only:
            continue
        t0 = time.time()
        try:
            raw, sc = character_bytes(row, layout=layout, G=G)
        except Exception as e:   # noqa: BLE001
            from .assemble import AssemblyError
            if isinstance(e, AssemblyError) and row['kind'] == 'visor':
                log('SKIP %-16s %s' % (row['id'], e))
                man.append({'id': row['id'], 'pack': row['pack'], 'kind': row['kind'], 'skipped': str(e)})
                continue
            raise
        rel = '%s/%s.glb' % (row['pack'], row['id'])
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        rec = character_record(G, row, raw, sc, rel)
        man.append(rec)
        log('EXPORT %-16s %-14s body %4d clips %2d audit %s gate %s %s %.1fs' % (
            row['id'], row['pack'], rec['tris_body_glb'], len(rec['clips']), rec['audit_pass'], rec['gate_pass'],
            rec['sha256'][:12], time.time() - t0))
    doc = {'count': len([m for m in man if 'skipped' not in m]), 'characters': man, 'exporter': 'python',
           'layout': layout}
    (out / 'manifest.json').write_text(json.dumps(doc, indent=1, sort_keys=True), encoding='utf-8')
    return doc


def export_combat(out_dir, *, only=None, exporter='auto', settings=None, root=None, log=print):
    """Enemies (2 per pack) + weapon + projectile per pack -> <out>/{enemies,props}/<pack>/<id>.glb + export.json."""
    s = _check_exporter(exporter, settings)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if s['exporter'] == 'blender':
        return _blender_export(s['blender'], out, 'combat', only)
    G = _gen(root)
    EN = G.core('enemies')
    only = set(only or [])
    rec = {'enemies': [], 'props': [], 'exporter': 'python'}
    for pn in ('polar_pod', 'forest_village'):
        for eid in EN.ENEMY_IDS:
            if only and eid not in only:
                continue
            raw, sc = enemy_bytes(pn, eid, G)
            rel = 'enemies/%s/%s.glb' % (pn, eid)
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(raw)
            rec['enemies'].append({'id': eid, 'pack': pn, 'file': rel, 'sha256': _sha(raw), 'bytes': len(raw),
                                   'rig': sc.info['skeleton'], 'topology': sc.info['topology'],
                                   'template': sc.info['template'], 'tris_body': sc.info['tris_body'],
                                   'roles': sc.info['roles'], 'roles_fallback': sc.info['roles_fallback']})
            log('EXPORT enemy %-12s %-14s %s tris %d' % (eid, pn, _sha(raw)[:12], sc.info['tris_body']))
        for kind, pid in (('weapon', G.core('weapon').WEAPON_ID), ('projectile', G.core('enemy_props').PROJ_ID)):
            if only and pid not in only:
                continue
            raw, sc = prop_bytes(pn, kind, G)
            rel = 'props/%s/%s.glb' % (pn, pid)
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(raw)
            rec['props'].append({'id': pid, 'kind': kind, 'pack': pn, 'file': rel, 'sha256': _sha(raw), 'bytes': len(raw),
                                 'tris': sc.info['tris'], 'roles': sc.info['roles'], 'roles_fallback': sc.info['roles_fallback']})
            log('EXPORT %s %-12s %-14s %s' % (kind, pid, pn, _sha(raw)[:12]))
    (out / 'export.json').write_text(json.dumps(rec, indent=1, sort_keys=True), encoding='utf-8')
    return rec


def _blender_export(blender, out, what, only):
    """The `blender` exporter: the original pipeline, run under Blender (oracle / fallback)."""
    script = REPO / 'tools' / 'nbchars_blender_export.py'
    argv = [blender, '--background', '--factory-startup', '--disable-autoexec', '--python', str(script), '--',
            '--gen', str(REPO / 'characters' / 'gen'), '--out', str(out), '--what', what]
    if only:
        argv += ['--only', ','.join(sorted(only))]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0:
        raise ExportError('blender exporter failed (exit %d): %s' % (p.returncode, p.stderr[-800:]))
    f = out / ('manifest.json' if what == 'cast' else 'export.json')
    return json.loads(f.read_text(encoding='utf-8'))


# ------------------------------------------------------------------ CHARSYS build items / jobs
def build_item(item, out_dir, *, packs=None, exporter='auto', settings=None, root=None):
    """One compiled CHARSYS build item -> <out>/<item.out> + info row (characters/gen/build.py semantics)."""
    s = _check_exporter(exporter, settings)
    if s['exporter'] == 'blender':
        raise ExportError('build_item with the blender exporter: run characters/gen/build.py under Blender (CHARSYS)')
    from . import assemble as A
    from . import writer as W
    G = _gen(root)
    for pid, entry in (packs or {}).items():
        G.inline[pid] = entry
    out = Path(out_dir)
    kind = item['kind']
    if kind in ('person', 'masked', 'animal'):
        animal = kind == 'animal'
        sc = A.character(item['pack_id'], item['params'], animal, seed=int(item.get('seed', 19)), stance=item.get('stance'),
                         props=item.get('props', []), clips=item.get('clips'), G=G)
        if item.get('weapon'):
            sc.sockets.append(A.weapon_socket(G, sc, item['pack_id']))
    elif kind == 'enemy':
        sc = A.enemy(item['pack_id'], item['enemy'], G=G)
    elif kind in _BUILDERS:
        sc = _BUILDERS[kind](item, G.pack(item['pack_id']))
    else:
        raise ExportError('no scene builder for item kind %r (register one with nbchars.register_builder)' % kind)
    raw = W.write_scene(sc)
    path = out / item['out']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    info = {'id': item['id'], 'kind': kind, 'file': item['out'], 'sha256': _sha(raw), 'bytes': len(raw),
            'clips': sorted(c.name for c in sc.clips), 'exporter': 'python'}
    if sc.rig is not None:
        info.update(skeleton=sc.rig.skeleton, topology=sc.rig.extras.get('topology'), tris_body=int(len(sc.body.faces)))
        if 'params_json' in sc.rig.extras:
            info['params_json'] = sc.rig.extras['params_json']
        if 'stance' in sc.rig.extras:
            info['stance'] = sc.rig.extras['stance']
    return info


def build_job(job, out_dir, *, exporter='auto', settings=None, root=None):
    if job.get('schema') != 'hermes64-charsys-job/1':
        raise ExportError('unknown job schema %r' % job.get('schema'))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = {'schema': 'hermes64-charsys-build-report/1', 'items': [], 'exporter': 'python'}
    for item in job['items']:
        report['items'].append(build_item(item, out, packs=job.get('packs'), exporter=exporter, settings=settings,
                                          root=root))
    (out / 'build-report.json').write_text(json.dumps(report, indent=1, sort_keys=True), encoding='utf-8')
    return report


def environment():
    from . import pycompat
    import zlib
    out = {'python': sys.version.split()[0], 'numpy': SEL.numpy_version(), 'zlib': zlib.ZLIB_VERSION,
           'zlib_runtime': getattr(zlib, 'ZLIB_RUNTIME_VERSION', None)}
    out.update(pycompat.describe())
    return out
