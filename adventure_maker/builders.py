"""Builder policy and fixed argv shared by single and batch asset builds."""
from .safety import Fault, fail

# ZEROSETUP: the default is `auto`. Strict Python-vs-Blender parity is still BLOCKED (docs/NOBLENDER-PARITY.md:
# 12/12 Godot captures pass, strict mesh parity does not), so `auto` keeps Blender wherever Blender is installed
# (no change in output for those machines) and only falls back to the Python builder when Blender is missing.
DEFAULT_BUILDER = 'auto'
PARITY_NOTE = ('Python builder: strict mesh parity with Blender is not proven (docs/NOBLENDER-PARITY.md); '
               'rendered Godot captures match on the fixed 12-pair subset')


def blender_available(settings):
    from .runner import locate
    try:
        locate('blender', settings.get('blender_path', '') or '')
        return True
    except Fault:
        return False


def effective(settings):
    """The builder setting as used: absent, None or blank means DEFAULT_BUILDER ('auto', as plugin.yaml documents);
    case and surrounding spaces are ignored. Every reader goes through this (BFIX: no reader may treat blank as blender)."""
    value = (settings or {}).get('builder')
    return str(value).strip().lower() if value is not None and str(value).strip() else DEFAULT_BUILDER


def select(settings, needs_armature=False, blender_present=None):
    """Concrete builder for this build.

    blender  always Blender (fails later if it is missing; that message names builder=auto).
    python   always the Python builder (needs numpy in python_path); never for new armatures.
    auto     Blender when it is found, otherwise Python for static kits. New armatures still need Blender.
    """
    builder = effective(settings)
    if builder not in ('auto','python','blender'):
        fail('configuration','builder must be python, blender or auto')
    if builder == 'auto':
        present = blender_available(settings) if blender_present is None else blender_present
        if present:
            return 'blender'
        if needs_armature:
            fail('missing_capability','New character armatures need Blender and Blender was not found. Prebuilt cast '
                 'and the Blender-free character exporter (character_exporter=auto) need neither.')
        return 'python'
    if builder == 'python' and needs_armature:
        fail('missing_capability','New character armatures need Blender; change builder to auto or blender and configure blender_path. Prebuilt cast needs neither.')
    return builder


def explain(settings, blender_present=None, numpy_present=None):
    """One plain line: which builder `auto`/the setting will use on this machine and what it depends on."""
    builder = effective(settings)
    present = blender_available(settings) if blender_present is None else blender_present
    chosen = select(dict(settings, builder=builder), blender_present=present)
    if chosen == 'blender':
        return ('builder=%s: Blender builds room models' % builder) + ('' if present else ' but Blender was not found; set builder to auto')
    line = 'builder=%s: the Python builder makes room models (Blender %s). %s' % (
        builder, 'found but not requested' if present else 'not found', PARITY_NOTE)
    if numpy_present is False:
        line += '. It needs numpy in python_path, which is missing'
    return line


def identity(builder):
    return builder + ':static-v1:srgb8-v1'


def command(builder, executable, script, args):
    prefix = ([executable,'--background','--factory-startup','--disable-autoexec','--python',str(script),'--']
              if builder=='blender' else [executable,'-B',str(script)])
    return prefix + ['--builder',builder] + list(args)
