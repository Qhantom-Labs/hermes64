"""Builder policy and fixed argv shared by single and batch asset builds."""
from .safety import fail

# Promotion is deliberately gated on docs/NOBLENDER-PARITY.md, not availability.
DEFAULT_BUILDER = 'blender'


def select(settings, needs_armature=False):
    builder = settings.get('builder') or DEFAULT_BUILDER
    if builder not in ('auto','python','blender'):
        fail('configuration','builder must be python, blender or auto')
    if builder == 'auto':
        return 'blender' if needs_armature else 'python'
    if builder == 'python' and needs_armature:
        fail('missing_capability','New character armatures need Blender; change builder to auto or blender and configure blender_path. Prebuilt cast needs neither.')
    return builder


def identity(builder):
    return builder + ':static-v1:srgb8-v1'


def command(builder, executable, script, args):
    prefix = ([executable,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--']
              if builder=='blender' else [executable,'-B',str(script)])
    return prefix + ['--builder',builder] + list(args)
