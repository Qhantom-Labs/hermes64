"""Provider-neutral schema for hermes64_cover; cover_tools validates action-specific requirements again."""
from .schemas import obj, text, ID

NUM = lambda low, high: {'type': 'number', 'minimum': low, 'maximum': high}
VEC3 = {'type': 'array', 'items': NUM(-60, 60), 'minItems': 3, 'maxItems': 3}
COLOR = text(7, pattern=r'^#[0-9a-fA-F]{6}$')
LABEL = text(32, pattern=r"^[A-Za-z0-9][A-Za-z0-9 .,'!?&:-]*$")
EXPORT_NAMES = ['box-1x', 'box-2x', 'banner', 'square', 'card-alpha', 'studio-art']
PROFILES = ['n64_base', 'polar_pod_example', 'warm_desert_example']

EDIT = obj({
    'op': {'type': 'string', 'enum': ['move', 'nudge', 'replace', 'add', 'remove', 'lighting', 'camera', 'title',
                                      'particles', 'pose', 'finish', 'reframe']},
    'target': text(60, pattern=r'^(hero|prop|cast):[a-z0-9_-]{1,48}$'),
    'by': VEC3, 'to': VEC3, 'at': VEC3, 'yaw': NUM(-360, 360), 'scale': NUM(0.2, 4),
    'direction': {'type': 'string', 'enum': ['left', 'right', 'forward', 'back', 'up', 'down']},
    'metres': NUM(0.05, 30),
    'kind': {'type': 'string', 'enum': ['hero', 'prop', 'cast', 'none', 'snow', 'fireflies', 'dust', 'embers', 'petals']},
    'kit': text(64, pattern=r'^[a-z][a-z0-9_]*(?:[./][a-z0-9_]+){0,3}$'),
    'id': ID, 'clip': text(24, pattern=r'^[a-z][a-z_]{0,23}$'), 'frame': {'type': 'integer', 'minimum': 0, 'maximum': 47},
    'mood': {'type': 'string', 'enum': ['night', 'dusk', 'day', 'dawn', 'interior']},
    'key_energy': NUM(0, 1), 'ambient_energy': NUM(0, 1), 'fill_energy': NUM(0, 1),
    'key_azimuth_deg': NUM(-180, 180), 'key_elevation_deg': NUM(5, 85),
    'fog_near_m': NUM(0, 60), 'fog_far_m': NUM(4, 160), 'fog_density': NUM(0, 0.95),
    'glow_strength': NUM(0, 0.9), 'stars': {'type': 'integer', 'minimum': 0, 'maximum': 400},
    'aurora_strength': NUM(0, 0.8), 'clouds': NUM(0, 1), 'exposure': NUM(0.3, 1.0),
    'focal_mm': NUM(18, 85), 'distance_m': NUM(2, 45), 'azimuth_deg': NUM(-180, 180), 'elevation_deg': NUM(-12, 65),
    'roll_deg': NUM(-8, 8), 'framing': {'type': 'string', 'enum': ['poster', 'banner', 'square']}, 'target_point': VEC3,
    'top': NUM(0, 0.9), 'bottom': NUM(0.1, 1), 'subjects': {'type': 'string', 'enum': ['all', 'cast', 'hero']},
    'text': text(28, pattern=r"^[A-Za-z0-9][A-Za-z0-9 .,'!?&:-]*$"), 'subtitle': {'type': 'string', 'maxLength': 32},
    'placement': {'type': 'string', 'enum': ['top', 'bottom']}, 'letter': {'type': 'string', 'enum': ['block', 'wedge', 'tall']},
    'size': {'type': 'string', 'enum': ['m', 'l', 'xl']}, 'fill': COLOR, 'fill2': COLOR, 'outline': COLOR, 'shadow': COLOR,
    'count': {'type': 'integer', 'minimum': 0, 'maximum': 400}, 'color': COLOR, 'size_m': NUM(0.02, 0.25),
    'vignette': NUM(0, 0.35), 'contrast': NUM(0.9, 1.25), 'saturation': NUM(0.85, 1.3), 'lift': NUM(0, 0.12),
    'band_edge': {'type': 'string', 'enum': ['bottom', 'left', 'right', 'top', 'none']}, 'mark': {'type': 'boolean'},
}, ['op'])

COVER_SCHEMA = {
    'name': 'hermes64_cover',
    'description': ('Staged box-art covers for a Hermes64 project. propose writes THREE composition variants (scene '
                    'files + preview renders + gate verdicts) for a human to pick, never adopting one; edit applies typed '
                    'edits (move/nudge/replace/add/remove/lighting/camera/title/particles/pose/finish/reframe) to a scene; '
                    'render makes the final renders of a chosen scene and runs the cover gate; export finishes box art '
                    '(box 245x170 1x/2x, banner 1280x640, square 1080x1080, transparent-edged card, Studio art) from a '
                    'passed render and adopts it as the project cover only when adopt=true is passed on the user\'s '
                    'explicit choice; list shows scenes, renders, exports and the adopted cover. Local windowed Godot '
                    'through the sandboxed runner; writes only inside the project; no network.'),
    'parameters': obj({
        'action': {'type': 'string', 'enum': ['propose', 'render', 'edit', 'export', 'list']},
        'project': ID,
        'seed': {'type': 'integer', 'minimum': 0, 'maximum': 2147483647},
        'style_profile': {'type': 'string', 'enum': PROFILES},
        'scene': ID,
        'edits': {'type': 'array', 'items': EDIT, 'minItems': 1, 'maxItems': 12},
        'new_id': ID,
        'preview': {'type': 'boolean'},
        'sizes': {'type': 'array', 'items': {'type': 'string', 'enum': EXPORT_NAMES}, 'minItems': 1, 'maxItems': 6},
        'adopt': {'type': 'boolean'},
        'title': LABEL,
    }, ['action', 'project']),
}
