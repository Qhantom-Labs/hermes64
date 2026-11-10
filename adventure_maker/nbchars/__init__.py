"""Blender-free character export: the vendored generator -> skinned + animated GLB in pure Python + numpy.

Public API (stable; docs/NBCHARS-API.md):
    build_item(item, out_dir, *, packs=None, exporter='auto', settings=None) -> info dict
    build_job(job, out_dir, *, exporter='auto', settings=None) -> build report
    export_cast(out_dir, *, only=None, exporter='auto', settings=None, layout='published') -> manifest
    export_combat(out_dir, *, only=None, exporter='auto', settings=None) -> record
    write_scene(scene) -> bytes
    register_builder(kind, fn)
    select_exporter(settings, numpy=None, blender=None) -> {'exporter', 'reason', 'numpy', 'parity'}
    doctor_line(settings, numpy=None, blender=None) -> str
Scene model classes: Scene, SceneRig, SceneMesh, SceneMaterial, SceneSocket, SceneClip (props = sockets with a mesh).
"""
def _robot_builder(item, pack):
    """CHARSYS robots (kind 'robot'): the port of ext/robot_blender.py in adventure_maker/character_robot.py, imported
    on first use (registered here so a job file builds robots in any process, the CLI included)."""
    from ..character_robot import robot_scene
    return robot_scene(item, pack)


_BUILDERS = {'robot': _robot_builder}


def register_builder(kind, fn):
    """Register a scene builder for an item kind (e.g. CHARSYS 'robot'): fn(item, pack) -> Scene."""
    _BUILDERS[kind] = fn


def _api(name):
    def call(*a, **kw):
        from . import api
        return getattr(api, name)(*a, **kw)
    call.__name__ = name
    return call


build_item = _api('build_item')
build_job = _api('build_job')
export_cast = _api('export_cast')
export_combat = _api('export_combat')
write_scene = _api('write_scene')
select_exporter = _api('select_exporter')
doctor_line = _api('doctor_line')


def __getattr__(name):
    if name in ('Scene', 'SceneRig', 'SceneMesh', 'SceneMaterial', 'SceneSocket', 'SceneClip'):
        from . import scene
        return getattr(scene, name)
    raise AttributeError(name)
