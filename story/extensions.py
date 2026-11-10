"""Version-gated 1.1.0 schema extensions; no weakening of 1.0.0 validation."""


def extended(value):
    return isinstance(value, dict) and value.get('contract_version') in ('1.1.0', '1.2.0')


def validate_params(params, path, enabled):
    from .validation import obj, text, strings, ident, fail, vector
    optional = tuple(k for k in ('suit', 'coat', 'dialogue_tags') if enabled and isinstance(params, dict) and k in params)
    obj(params, ('costume', 'colour', 'voice_tags') + optional, path + '/params')
    text(params['costume'], path + '/costume')
    text(params['colour'], path + '/colour')
    strings(params['voice_tags'], path + '/voice_tags')
    if 'coat' in params:
        ident(params['coat'], path + '/coat')
    if 'dialogue_tags' in params:
        strings(params['dialogue_tags'], path + '/dialogue_tags')
    if 'suit' in params:
        suit = params['suit']
        fields = ('hood', 'vest_pattern', 'vest_colour', 'sweater_colour', 'sweater_wear',
                  'trouser_colour', 'trouser_wear', 'trouser_volume', 'gloves', 'boots', 'accessories')
        obj(suit, fields, path + '/suit')
        for k in fields:
            if k in ('vest_pattern', 'sweater_wear', 'trouser_wear', 'gloves', 'boots'):
                ident(suit[k], path + '/suit/' + k)
            elif k not in ('trouser_volume', 'accessories'):
                text(suit[k], path + '/suit/' + k)
        vector([suit['trouser_volume']], path + '/suit/trouser_volume', 1)
        if suit['trouser_volume'] <= 0:
            fail(path + '/suit/trouser_volume', 'must be positive')
        strings(suit['accessories'], path + '/suit/accessories')


def validate_collectibles(spec, ix, logic):
    from .validation import obj, integer, ident, text, reference, asset, fail
    seen_flags = set(ix['flags'])
    for g in spec['collectible_groups']:
        p = 'collectible_groups/' + g['id']
        obj(g, ('id', 'name', 'kind', 'required'), p)
        text(g['name'], p + '/name')
        ident(g['kind'], p + '/kind')
        integer(g['required'], p + '/required')
    for c in spec['collectibles']:
        p = 'collectibles/' + c['id']
        obj(c, ('id', 'group', 'room', 'name', 'label', 'text', 'asset', 'character', 'dialogue', 'follower_flag', 'conditions'), p)
        reference(c['group'], ix['collectible_groups'], p + '/group')
        reference(c['room'], ix['rooms'], p + '/room')
        for k in ('name', 'label', 'text'):
            text(c[k], p + '/' + k)
        asset(c['asset'], p + '/asset')
        for k, domain in [('character', 'characters'), ('dialogue', 'dialogues')]:
            if c[k] != '':
                reference(c[k], ix[domain], p + '/' + k)
        if c['follower_flag'] != '':
            ident(c['follower_flag'], p + '/follower_flag')
            if c['follower_flag'] in seen_flags:
                fail(p + '/follower_flag', 'duplicate/overlapping derived follower flag')
            seen_flags.add(c['follower_flag'])
        logic(c['conditions'], p + '/conditions')
