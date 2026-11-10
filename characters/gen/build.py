"""Blender 5.2 entry point for the character system (headless, argv-only, no network).

    blender --background --factory-startup --disable-autoexec --python characters/gen/build.py -- \
        --job <job.json> --out <dir>

A job is a list of fully compiled build items (adventure_maker/character_recipe.compile_build): resolved generator
parameters, an inline palette pack (or a vendored pack id), stance, props, clip list and output file name. Nothing
here interprets recipes, briefs or style profiles; the same item always produces the same bytes.

Item kinds:
  person / masked  core.blender.assemble (face-head v3 or masked hood v2 topology) + held clips
  animal           core.blender.assemble(animal=True) + the 7 animal clips
  enemy            core.combat_blender.assemble_enemy (cairn_dasher / reed_warden)
  robot            ext.robot_blender.assemble_robot (mechanical family on human16_v1, boss variants)
An item may ask for review renders ({"render": {"views": [...]}}): front / three-quarter / side PNGs with a
transparent background, rendered after the export from the idle key 0 pose (the GLB is already written).
Writes <out>/<item.out> plus <out>/build-report.json (sha256, bytes, triangle counts, clips per item).
"""
import hashlib
import json
import os
import sys
from pathlib import Path

GEN = Path(__file__).resolve().parent
sys.path.insert(0, str(GEN))
if os.environ.get('COMBAT_GRIP_TILT_DEG') is not None:
    # core/weapon.py reads this at import time; an ambient value would change bytes silently.
    raise SystemExit('BUILD REFUSED: COMBAT_GRIP_TILT_DEG must not be set in the build environment')

import bpy  # noqa: E402,F401
from core import blender as B  # noqa: E402
from core import combat_blender as CB  # noqa: E402
from core import roles as RL  # noqa: E402
from core import glb as GLB  # noqa: E402

_LOADPACK = B.loadpack
_LOAD_ROLES = RL.load_roles
INLINE = {}


def _loadpack(name):
    if name in INLINE:
        return json.loads(json.dumps(INLINE[name]['pack']))
    return _LOADPACK(name)


def _load_roles(pack):
    if pack['id'] in INLINE:
        return dict(INLINE[pack['id']].get('combat_roles', {}))
    return _LOAD_ROLES(pack)


B.loadpack = _loadpack
RL.load_roles = _load_roles


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build_item(item, out):
    kind = item['kind']
    pack_id = item['pack_id']
    tex = out / 'textures' / pack_id
    path = out / item['out']
    path.parent.mkdir(parents=True, exist_ok=True)
    B.clear()
    info = {'id': item['id'], 'kind': kind, 'file': item['out']}
    hover = 0.
    if kind in ('person', 'masked', 'animal'):
        animal = kind == 'animal'
        clips = item.get('clips')
        legacy = clips is None
        rig, ob, a, pk = B.assemble(pack_id, item['params'], animal, seed=int(item.get('seed', 19)), folder=tex,
                                    actions=legacy, stance=item.get('stance'), prop_list=item.get('props', []))
        if not legacy:
            CB.make_actions_clips(rig, ob, a, clips)
        if item.get('weapon'):
            CB.add_weapon(rig, a, pk, pack_id, tex)
        info.update(topology=rig['topology'], skeleton=rig['skeleton'], params_json=rig['params_json'],
                    tris_body=len(a.faces), stance=rig['stance'])
        audit_kind = 'quad' if animal else 'human'
        height = max(v[2] for v in a.vertices)
        extent = (max(v[1] for v in a.vertices) - min(v[1] for v in a.vertices)) if animal else 0.
        n_clips = len(clips) if clips else 7

        def poser():
            B.pose(rig, ob, a, 'idle', 0.)
    elif kind == 'enemy':
        rig, ob, m, pk, roles, fell = CB.assemble_enemy(pack_id, item['enemy'], tex, actions=True)
        info.update(topology=m.topology, skeleton=m.rig, tris_body=len(m.faces), roles=roles, roles_fallback=fell)
        audit_kind = None
        height = max(v[2] for v in m.vertices)
        extent = 0.
        n_clips = 7

        def poser():
            CB.enemy_pose(rig, ob, m, 'idle', 0.)
    elif kind == 'robot':
        from ext import robot_blender as RB
        rig, ob, m = RB.assemble_robot(pack_id, item['robot'], tex)
        info.update(topology=m.topology, skeleton=m.rig, tris_body=len(m.faces), tris_crown=m.crown_tris,
                    hover_m=round(getattr(m, 'hover', 0.), 6), robot_body=m.body, params_json=rig['params_json'])
        audit_kind = None
        height = max(v[2] for v in m.vertices)
        extent = 0.
        hover = getattr(m, 'hover', 0.)
        n_clips = len(json.loads(rig['clips']))

        def poser():
            RB._pose(rig, ob, m, 'idle', 0.)
    else:
        raise SystemExit('BUILD REFUSED: unknown item kind ' + str(kind))
    B.export(path)
    raw = path.read_bytes()
    au = GLB.GLB(path).audit(kind=audit_kind, n_clips=n_clips)
    info.update(sha256=sha(raw), bytes=len(raw), tris_glb_total=au['tris'], tris_props=au['tris_props'],
                clips=[x['name'] for x in au['animations']], audit_errors=au['errors'], height_m=round(height, 4))
    if item.get('render') is not None:
        from ext import review_render as RR
        poser()
        views = tuple(item['render'].get('views', list(RR.VIEWS)))
        info['renders'] = RR.render_views(out / 'renders', item['id'], height, views, hover=hover, extent=extent)
        room = item['render'].get('room')
        if room:
            info['renders']['room'] = RR.render_room(out / 'renders', item['id'], height, room['floor'], room['wall'],
                                                     hover=hover)
    return info


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    if len(argv) != 4 or argv[0] != '--job' or argv[2] != '--out':
        raise SystemExit('usage: build.py -- --job <job.json> --out <dir>')
    job = json.loads(Path(argv[1]).read_text())
    out = Path(argv[3])
    out.mkdir(parents=True, exist_ok=True)
    if job.get('schema') != 'hermes64-charsys-job/1':
        raise SystemExit('BUILD REFUSED: unknown job schema')
    for pid, entry in job.get('packs', {}).items():
        INLINE[pid] = entry
    report = {'schema': 'hermes64-charsys-build-report/1', 'items': []}
    for item in job['items']:
        info = build_item(item, out)
        report['items'].append(info)
        print('BUILT %-24s %-8s %s body %s clips %d' % (info['id'], info['kind'], info['sha256'][:12],
                                                      info.get('tris_body'), len(info['clips'])), flush=True)
    (out / 'build-report.json').write_text(json.dumps(report, indent=1, sort_keys=True))
    print('BUILD COMPLETE %d' % len(report['items']), flush=True)


if __name__ == '__main__':
    main()
