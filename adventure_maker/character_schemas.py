"""Full validation schema of hermes64_character. Advertised through wire.py (compact copy, MERGE4); handle() validates this."""
ID = {'type': 'string', 'pattern': '^[a-z][a-z0-9_]{0,47}$'}
PATH = {'type': 'string', 'pattern': '^[A-Za-z0-9_./-]{1,200}$', 'maxLength': 200}
EDIT = {'type': 'object', 'additionalProperties': False, 'required': ['kind'],
        'properties': {'kind': {'enum': ['height', 'build', 'hair', 'color', 'swap', 'face', 'prop', 'name']},
                       'value': {'type': 'number', 'minimum': 0, 'maximum': 4},
                       'head': {'type': 'number'}, 'shoulders': {'type': 'number'}, 'waist': {'type': 'number'},
                       'legs': {'type': 'number'}, 'age': {'enum': ['child', 'teen', 'adult', 'elder']},
                       'style': ID, 'color': ID, 'slot': ID, 'role': ID,
                       'part': {'type': 'string', 'pattern': '^[a-z]+\\.[a-z0-9_]{1,40}$'},
                       'preset': {'type': 'string', 'pattern': '^face\\.[a-z0-9_]{1,40}$'},
                       'expression': {'enum': ['neutral', 'blink', 'talk_a', 'talk_b', 'smile', 'worried', 'surprised', 'sleepy']},
                       'eyes': ID, 'beard': {'type': 'string', 'pattern': '^beard\\.[a-z_]{1,20}$'},
                       'display': {'type': 'string', 'minLength': 1, 'maxLength': 48}, 'placeholder': {'type': 'boolean'}}}

CHARACTER_SCHEMA = {
    'name': 'hermes64_character',
    'description': ('House-style characters from recipes: propose three variants with contact sheets for the user to '
                    'pick, edit with typed edits, build the chosen one (GLB, clips, every gate incl. the rig kit), '
                    'list/info parts, bind a character to the project cast, locomotion = bake run + walk for a body '
                    '(docs/LOCOMOTION.md). Never auto-adopts. Local Blender; '
                    'writes only inside the project. Details: skill hermes64:hermes64-characters.'),
    'parameters': {
        'type': 'object', 'additionalProperties': False, 'required': ['action'],
        'properties': {
            'action': {'enum': ['propose', 'build', 'edit', 'list', 'info', 'bind', 'locomotion']},
            'project': {'type': 'string', 'pattern': '^[a-z0-9][a-z0-9_-]{0,63}$'},
            'brief': {'type': 'string', 'minLength': 3, 'maxLength': 400},
            'references': {'type': 'array', 'items': PATH, 'maxItems': 4},
            'style': ID,
            'recipe': PATH,
            'edits': {'type': 'array', 'items': EDIT, 'minItems': 1, 'maxItems': 8},
            'render': {'type': 'boolean'},
            'id': {'type': 'string', 'pattern': '^[a-z][a-z0-9_.]{0,63}$'},
            'glb': PATH,
            'display_name': {'type': 'string', 'minLength': 1, 'maxLength': 48},
            'placeholder': {'type': 'boolean'},
            'source': {'enum': ['generated', 'cameo_pack', 'community']},
            'what': {'enum': ['parts', 'bodies', 'styles', 'recipes', 'cast']},
            'legacy': {'type': 'boolean'},
            # WAIVER (docs/WAIVER.md): bind waive=true owner_approved=<the owner's name> brief=<the owner's words>
            'waive': {'type': 'boolean'},
            'owner_approved': {'type': 'string', 'minLength': 1, 'maxLength': 80},
        },
    },
}
