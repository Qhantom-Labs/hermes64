"""What the bundled plugin can share: seed hub entries built from the repository's own manifests.

Shared by tools/catalog.py (asset catalog), tools/hub.py (seed registry) and the hub runtime
(``hub install`` rebuilds a bundled entry's archive on demand and checks it against the
committed sha256; ``hub pack <catalog-id>`` packs one bundled asset). Everything here is
derived from manifests and files that already exist; display names come from
catalog/names.json, and thumbnails are only ever crops of existing renders (THUMBS).
"""
import json
from pathlib import Path
import re

from . import hub_archive, genre_kits
from .hub_index import CONTRACT, pretty

ROOT = Path(__file__).resolve().parents[1]
AUTHOR = 'Qhantom Labs'
VERSION = '1.0.0'
KIT_PACKS = ('forest_village', 'polar_pod', 'stone_dungeon', 'stone_dungeon_torchlit')
# DUNGEONKIT (MERGE5): the stone_dungeon builds live in a side manifest so kits/manifest.json stays unchanged and
# under its strict-JSON size limit (docs/DUNGEONKIT-HUB-ENTRIES.md).
SIDE_MANIFESTS = {'stone_dungeon': 'kits/library/dungeonkit-manifest.json',
                  'stone_dungeon_torchlit': 'kits/library/dungeonkit-manifest.json'}
KIT_FAMILIES = (
    ('architecture', ('arch.',), 'walls, floors, doors, windows, roofs, stairs, bridges, a tower and room shells'),
    ('furniture', ('furn.', 'soft.'), 'beds, seats, tables, lamps, shelves, chests, a hearth, rugs and cushions'),
    ('nature', ('nature.',), 'trees, bushes, rocks and grass'),
    ('props', ('prop.',), 'keys, books, signs, tools, devices and vessels'),
    ('terrain', ('terrain.', 'sky.', 'fx.'), 'ground patches, yards, water, far hills, a sky dome and particles'),
    ('vehicles', ('vehicle.',), 'a rowboat and a small craft'),
    ('dungeon_architecture', ('dgn.',), 'corridors, room shells, doorways, locked doors, stairs, pillars, pits, bridges, '
                                        'window slits, ceilings and rubble'),
    ('dungeon_props', ('dprop.',), 'sconces, braziers, chests, pots, switches, pressure plates, a carved push block, '
                                   'statues, banners, cobwebs, crates, rune tablets and crystals'),
    ('cave', ('cave.',), 'organic rock walls, floors, stalactites, boulders, a cave mouth, ledges and cliffs'),
    ('temple', ('tmpl.',), 'columns, altars, carved reliefs, a boss door, a dais, an obelisk and inlaid floors'),
    ('lake', ('lake.',), 'water, shores, a dock, a stepping-stone bridge, reeds, lilies, a waterfall and the lake bed'))
ITEM_PREFIXES = ('furn.', 'prop.', 'soft.', 'vehicle.', 'nature.')
STYLE_WORDS = {'n64_v0': ['village', 'harbour', 'lantern', 'warm'], 'forest_village': ['forest', 'village', 'woodland'],
               'polar_pod': ['polar', 'snow', 'habitat', 'sci-fi'], 'n64_base': ['base', 'classic', 'neutral', 'low-poly'],
               'warm_desert_example': ['desert', 'warm', 'sand'], 'polar_pod_example': ['polar', 'habitat', 'cool'],
               'stone_dungeon': ['dungeon', 'stone', 'cave', 'temple', 'lake', 'fog'],
               'stone_dungeon_torchlit': ['dungeon', 'stone', 'torch', 'warm', 'cave', 'lake']}
PROFILES = {'n64_base': 'profiles/n64_base/profile.json', 'warm_desert_example': 'profiles/examples/warm_desert/profile.json',
            'polar_pod_example': 'profiles/examples/polar_pod/profile.json'}
# Pack-bound example games (a game entry must lock a style pack). game id -> (entry id, spec, thumbnail, what it mixes)
GAME_SOURCES = {
    'reedland_mixed': ('game.reedland_relay', 'examples/gameplay-reedland-runtime/spec.json', 'game-reedland',
                       'a timed course, an arena fight and region gates'),
    'reedland_regions': ('game.reedland_region_gates', 'examples/gameplay-reedland-regions/spec.json', None,
                         'region gates that open as you learn abilities'),
}
STARTER_CAST = ('fv_scribe', 'fv_warden', 'new_arrival', 'tavi')   # adventure_maker/newgame.py CAST
# Thumbnails are crops of renders that already exist in the repository; nothing is re-rendered.
# name: (source PNG, (x, y, w, h) crop, honest source label). Output is 160x120, area-averaged.
THUMBS = {
    'game-thaw': ('goldens/thaw/pod_bay.png', (0, 0, 320, 240), 'in-game capture of Thaw (blessed golden frame)'),
    'game-last_light': ('goldens/last_light/lamp_room.png', (0, 0, 320, 240), 'in-game capture of The Last Light (blessed golden frame)'),
    'game-reedland': ('evidence/modrt/contact-sheet.png', (22, 30, 280, 210), 'in-game capture of Reedland Relay (module runtime evidence)'),
    'style-polar_pod': ('goldens/thaw/snow_field.png', (0, 0, 320, 240), 'in-game capture of Thaw, which uses Polar Pod'),
    'style-n64_v0': ('goldens/last_light/fog_street.png', (0, 0, 320, 240), 'in-game capture of The Last Light, which uses Lantern Village'),
    'character-new_arrival': ('evidence/merge/character-captures/thaw/conversation_pit-closeup.png', (0, 0, 320, 240),
                              'in-game close-up from Thaw'),
    'character-fv_scribe': ('evidence/merge/character-captures/last_light/keepers_cottage-closeup.png', (0, 0, 320, 240),
                            'in-game close-up from The Last Light'),
    'character-fv_warden': ('evidence/merge/character-captures/last_light/fog_street-closeup.png', (0, 0, 320, 240),
                            'in-game close-up from The Last Light'),
    # Wide in-game frames where the character is the room's only other person (characters.json), cropped by hand.
    'character-tavi': ('evidence/merge/character-captures/thaw/pod_bay-clean.png', (47, 92, 80, 60),
                       'in-game capture of Thaw (cropped)'),
    'character-neri': ('evidence/merge/character-captures/thaw/workstation-clean.png', (89, 71, 88, 66),
                       'in-game capture of Thaw (cropped)'),
    'character-luma': ('evidence/merge/character-captures/thaw/dome_shelter-clean.png', (128, 80, 80, 60),
                       'in-game capture of Thaw (cropped)'),
    'style-stone_dungeon': ('docs/dungeonkit/thumb-gatehall-cold.png', (0, 0, 320, 240),
                            'in-game capture of The Drowned Gate (stone_dungeon)'),
    'style-stone_dungeon_torchlit': ('docs/dungeonkit/thumb-gatehall.png', (0, 0, 320, 240),
                                     'in-game capture of The Drowned Gate (stone_dungeon_torchlit)'),
}
# Parity renders exist only for the forest/polar builds (the dungeon packs use committed in-game captures above).
for _kit in ('arch.tower', 'arch.room_shell', 'furn.table', 'nature.tree', 'prop.book'):
    for _pack in ('forest_village', 'polar_pod'):
        THUMBS['kit-%s-%s' % (_kit, _pack)] = (
            'evidence/noblender/parity-04/render/%s__%s__0-blender.png' % (_kit, _pack), (40, 30, 240, 180),
            'kit render (Blender preview of the shipped model)')
THUMBS['style-forest_village'] = ('evidence/noblender/parity-04/render/nature.tree__forest_village__0-blender.png',
                                  (40, 30, 240, 180), 'kit render of a Forest Village tree (not a game capture)')
# Catalog asset -> thumbnail, and hub entry -> thumbnail (same images, kept per tree).
CATALOG_THUMBS = {'game:thaw': 'game-thaw', 'game:last_light': 'game-last_light', 'game:reedland_mixed': 'game-reedland',
                  'style:pack/polar_pod': 'style-polar_pod', 'style:pack/n64_v0': 'style-n64_v0',
                  'style:pack/forest_village': 'style-forest_village',
                  'style:pack/stone_dungeon': 'style-stone_dungeon',
                  'style:pack/stone_dungeon_torchlit': 'style-stone_dungeon_torchlit',
                  'character:polar_pod/new_arrival': 'character-new_arrival',
                  'character:forest_village/fv_scribe': 'character-fv_scribe',
                  'character:forest_village/fv_warden': 'character-fv_warden',
                  'character:polar_pod/tavi': 'character-tavi', 'character:polar_pod/neri': 'character-neri',
                  'character:polar_pod/luma': 'character-luma',
                  'kit:arch.tower': 'kit-arch.tower-forest_village', 'kit:arch.room_shell': 'kit-arch.room_shell-polar_pod',
                  'kit:furn.table': 'kit-furn.table-polar_pod', 'kit:nature.tree': 'kit-nature.tree-forest_village',
                  'kit:prop.book': 'kit-prop.book-forest_village'}
FAMILY_THUMBS = {'architecture': 'arch.tower', 'furniture': 'furn.table', 'nature': 'nature.tree', 'props': 'prop.book'}

# MERGE6 additions follow the dungeon side-manifest route. No unfinished pack is auto-discovered.
KIT_PACKS += tuple(genre_kits.PACKS)
ITEM_PREFIXES += genre_kits.ITEM_PREFIXES
SIDE_MANIFESTS.update({pid: row['manifest'] for pid, row in genre_kits.PACKS.items()})
KIT_FAMILIES += tuple((fid, prefixes, blurb) for fid, prefixes, _name, blurb in genre_kits.FAMILIES)
STYLE_WORDS.update({pid: row['words'] for pid, row in genre_kits.PACKS.items()})
THUMBS.update({'style-' + pid: (row['thumbnail'], row['crop'], 'in-game capture of ' + row['scene'])
               for pid, row in genre_kits.PACKS.items()})
CATALOG_THUMBS.update({'style:pack/' + pid: 'style-' + pid for pid in genre_kits.PACKS})


def read_json(root, rel):
    return json.loads((Path(root) / rel).read_text(encoding='utf-8'))


def names(root=ROOT):
    return read_json(root, 'catalog/names.json')


def person(table, cid):
    row = table['people'].get(cid)
    if isinstance(row, dict):
        return row['name'], bool(row.get('placeholder', True))
    return cid.replace('_', ' ').title(), True


def sound_name(table, sid):
    override = table.get('sounds', {}).get(sid)
    if override:
        return override
    parts = [p for p in sid.split('.') if p not in ('core', 'h64', 'creature')]
    number = parts.pop() if parts and parts[-1].isdigit() else None
    text = ' '.join(p.replace('_', ' ') for p in parts).title()
    text = re.sub(r'\bUi\b', 'UI', text)
    return (text + (' %d' % int(number) if number else '')).strip()[:80] or sid


def item_name(table, kit_id):
    return table['items'].get(kit_id) or kit_id.split('.', 1)[-1].replace('_', ' ').title()


def bound_characters(root=ROOT):
    """(character_id, pack) pairs bound by bindings.json for public release, in file order."""
    rows = read_json(root, 'bindings.json')['characters']
    seen = []
    for row in rows:
        if row.get('public_release') and not row.get('internal_only') and not row.get('placeholder'):
            key = (row['character_id'], row['character_pack'])
            if key not in seen:
                seen.append(key)
    return seen


MIT_TEXT = ('MIT License\n\nCopyright (c) %s\n\nPermission is hereby granted, free of charge, to any person obtaining a copy of '
            'this software and associated documentation files (the "Software"), to deal in the Software without restriction, '
            'including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell '
            'copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following '
            'conditions:\n\nThe above copyright notice and this permission notice shall be included in all copies or substantial '
            'portions of the Software.\n\nTHE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, '
            'INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND '
            'NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER '
            'LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE '
            'SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.\n')


def licence_text(licence, author, root=ROOT):
    """Bundled assets carry the repository's own licence files; anyone else's pack names its author."""
    if licence == 'MIT' and author == AUTHOR:
        return (Path(root) / 'LICENSE').read_bytes()
    if licence == 'MIT':
        return (MIT_TEXT % author).encode('utf-8')
    if licence == 'CC0-1.0' and author == AUTHOR:
        return (Path(root) / 'audio/expansion/CC0.txt').read_bytes()
    urls = {'CC-BY-4.0': 'https://creativecommons.org/licenses/by/4.0/legalcode',
            'CC-BY-SA-4.0': 'https://creativecommons.org/licenses/by-sa/4.0/legalcode',
            'Apache-2.0': 'https://www.apache.org/licenses/LICENSE-2.0', 'BSD-2-Clause': 'https://opensource.org/license/bsd-2-clause',
            'BSD-3-Clause': 'https://opensource.org/license/bsd-3-clause', 'ISC': 'https://opensource.org/license/isc-license-txt'}
    return ('SPDX-License-Identifier: %s\nLicence text: %s\nAuthor: %s\n' % (licence, urls.get(licence, ''), author)).encode('utf-8')


def readme(meta, style, tier):
    made_for = 'any style' if style == 'any' else '%s games' % style.replace('_', ' ')
    lines = ['# ' + meta['name'], '', meta['summary'], '',
             '- Id: `%s` (version %s)' % (meta['id'], meta['version']),
             '- Kind: ' + meta['kind'], '- Licence: %s (see LICENSE.txt)' % meta['licence'],
             '- Author: ' + meta['author'], '- Made for: ' + made_for,
             '- Checked: %s (%s; %s)' % (tier['label'], tier['proof'], tier['style']), '',
             'Install into a Hermes64 game: `/hermes64 hub install %s <game>`' % meta['id'], '',
             'Data only. Every file is listed with its sha256 in HUB.json.', '']
    return '\n'.join(lines).encode('utf-8')


def tier(label, proof='n/a', playtest='not run', style='not run', human='not reviewed'):
    return {'label': label, 'proof': proof, 'playtest': playtest, 'style': style, 'human': human}


def clean_tags(tags, limit=16):
    out = []
    for tag in tags:
        tag = re.sub(r'[^a-z0-9-]+', '-', str(tag).lower()).strip('-')[:32]
        if tag and tag not in out:
            out.append(tag)
    return sorted(out)[:limit]


def _recipe(rid, kind, name, summary, tags, licence, style, files, generated=None, tier_row=None, catalog_ids=(),
            thumb=None, palette=None, story=None, profile=None):
    row = {'id': rid, 'kind': kind, 'name': name[:60], 'summary': summary[:160], 'tags': clean_tags(tags),
           'licence': licence, 'style': style, 'files': dict(files), 'generated': dict(generated or {}),
           'tier': tier_row or tier('validated'), 'catalog_ids': sorted(catalog_ids), 'thumb': thumb}
    if palette:
        row['palette'] = palette[:32]
    if story:
        row['story'] = story
    if profile:
        row['profile'] = profile
    return row


def style_recipes(root, table):
    out = []
    for pid in ('n64_v0',) + KIT_PACKS:
        pack = read_json(root, 'packs/%s/pack.json' % pid)
        files = {name: 'packs/%s/%s' % (pid, name) for name in ('pack.json', 'view.json', 'look.json', 'bindings.json')
                 if (Path(root) / 'packs' / pid / name).is_file()}
        out.append(_recipe(
            'style.' + pid, 'style', table['styles'][pid],
            '%s theme pack: palette, materials, fog and kit bindings for %s kits. Select it to restyle a game.'
            % (table['styles'][pid], pack['kit_pack_id'].replace('_', ' ')),
            ['theme-pack', pack['kit_pack_id'].replace('_', '-')] + STYLE_WORDS[pid], 'MIT', pack['kit_pack_id'], files,
            tier_row=tier('data-checked', style='pack data validated (not a render)'),
            catalog_ids=['style:pack/' + pid], thumb='style-' + pid, palette=pack['palette']))
    for pid, rel in PROFILES.items():
        doc = read_json(root, rel)
        colours = [c for c in doc['sections']['palette']['colors'].values() if re.fullmatch(r'#[0-9A-F]{6}', c)]
        parent = doc.get('extends')
        out.append(_recipe(
            'style.' + pid, 'style', table['styles'][pid], doc['description'][:160],
            ['style-profile', 'data-only'] + STYLE_WORDS[pid], 'MIT', 'any', {'profile.json': rel},
            tier_row=tier('data-only', style='profile data valid; game builds do not read profiles yet'),
            catalog_ids=['style:profile/' + pid], palette=colours,
            profile=('extends %s@%s' % (parent['id'], parent['version'])) if parent else '%s@%s' % (pid, doc['version'])))
    return out


def side_kits(root, pack):
    """kits/manifest.json-shaped kit rows for a pack whose builds live in a side manifest (DUNGEONKIT)."""
    side = read_json(root, SIDE_MANIFESTS[pack])
    rows = {}
    for b in side['builds']:
        if b['variant'] != pack:
            continue
        k = side['kits'][b['id']]
        kit = rows.setdefault(b['id'], {'id': b['id'], 'class': k['class'], 'description': k['description'],
                                         'tri_limit': k['tri_limit'], 'version': k['version'], 'builds': []})
        # Side-manifest glb paths start at kits/, textures at kits/library/ (the main manifest's conventions).
        kit['builds'].append({'pack': pack, 'glb': b['glb'][len('kits/'):], 'preset': b['preset'], 'sha256': b['sha256'],
                              'tri_count': b['tris'], 'textures': [{'file': t} for t in b['textures']]})
    return list(rows.values())


def catalog_kits(root=ROOT, include_validation=False):
    """All committed kit ids, coalescing shared generators (e.g. sky.backdrop) across exact variants.

    Side manifests retain their own size limits and provenance; never flatten them into kits/manifest.json.
    Runtime callers do not depend on source-only GLB sidecars (excluded from installed plugins).
    The authoring catalog builder opts into real sidecar validation; texture hashes always come from files.
    """
    rows = {k['id']: k for k in read_json(root, 'kits/manifest.json')['kits']}
    for pack in SIDE_MANIFESTS:
        for kit in side_kits(root, pack):
            kit['source_manifest'] = SIDE_MANIFESTS[pack]
            for build in kit['builds']:
                if include_validation:
                    sidecar = read_json(root, 'kits/' + build['glb'] + '.json')
                    build['validation'] = {key: value['ok'] for key, value in sidecar['validation'].items()}
                for tex in build['textures']:
                    import hashlib
                    tex['sha256'] = hashlib.sha256((Path(root) / 'kits/library' / tex['file']).read_bytes()).hexdigest()
            if kit['id'] in rows:
                existing = {(b['pack'], b['preset']) for b in rows[kit['id']]['builds']}
                rows[kit['id']]['builds'].extend(b for b in kit['builds'] if (b['pack'], b['preset']) not in existing)
            else:
                rows[kit['id']] = kit
    return list(rows.values())


def kit_recipes(root, table):
    manifest = read_json(root, 'kits/manifest.json')
    out = []
    for pack in KIT_PACKS:
        kits = side_kits(root, pack) if pack in SIDE_MANIFESTS else manifest['kits']
        for family, prefixes, blurb in KIT_FAMILIES:
            files, rows, ids = {}, [], []
            for kit in kits:
                if not kit['id'].startswith(prefixes):
                    continue
                builds = [b for b in kit['builds'] if b['pack'] == pack]
                if not builds:
                    continue
                ids.append('kit:' + kit['id'])
                models = []
                for build in builds:
                    arc = 'models/' + Path(build['glb']).name
                    files[arc] = 'kits/' + build['glb']
                    textures = []
                    for tex in build['textures']:
                        tarc = 'textures/' + Path(tex['file']).name
                        files[tarc] = 'kits/library/' + tex['file']
                        textures.append(tarc)
                    models.append({'model': arc, 'preset': build['preset'], 'sha256': build['sha256'],
                                   'tris': build['tri_count'], 'textures': textures})
                rows.append({'id': kit['id'], 'name': item_name(table, kit['id']), 'class': kit['class'],
                             'description': kit['description'], 'tri_limit': kit['tri_limit'], 'version': kit['version'],
                             'builds': models})
            if not rows:
                continue
            title = '%s %s' % (table['styles'][pack], table['kit_families'][family])
            generated = {'kit.json': {'schema': 'hermes64-kit-family/1', 'pack': pack, 'family': family,
                                      'contract_version': manifest['contract_version'], 'kits': rows}}
            thumb = 'kit-%s-%s' % (FAMILY_THUMBS[family], pack) if family in FAMILY_THUMBS else None
            if thumb not in THUMBS:
                thumb = None   # no parity render for this pack (the dungeon packs); the entry lists without a preview
            out.append(_recipe(
                'kit.%s.%s' % (pack, family), 'kit', title,
                '%d low-poly %s models for %s games: %s.' % (sum(len(r['builds']) for r in rows), family.replace('_', ' '),
                                                            table['styles'][pack], blurb),
                ['kit', family, pack.replace('_', '-')] + [r['id'].split('.', 1)[1].replace('_', '-') for r in rows][:10],
                'MIT', pack, files, generated,
                tier('validated', style='kit gate passed: budget, naming, palette, topology'), ids, thumb))
    return out


def character_recipes(root, table):
    manifest = {(row['pack'], row['id']): row for row in read_json(root, 'characters/manifest.json')['characters']}
    bindings = read_json(root, 'bindings.json')['characters']
    out = []
    for cid, pack in bound_characters(root):
        row = manifest[(pack, cid)]
        creature = row['kind'] == 'animal'
        name, placeholder = (table['creatures'].get(cid, cid), False) if creature else person(table, cid)
        variants = [{'variant': b['authored_variant'], 'body_id': b['body_id'], 'base_rig_id': b['base_rig_id'],
                     'params': b['params']} for b in bindings if b['character_id'] == cid and b['character_pack'] == pack]
        info = {'schema': 'hermes64-character/1', 'id': cid, 'name': name, 'placeholder_name': placeholder, 'pack': pack,
                'kind': 'creature' if creature else 'person', 'body': row['kind'], 'model': 'models/%s.glb' % cid,
                'sha256': row['sha256'], 'tris': {'body': row['measured']['body_triangles'], 'total': row['measured']['total_triangles']},
                'budget': row['budget'], 'clips': row['clips'], 'joints': row['joints'], 'props': row['props'],
                'variants': variants}
        tags = ['creature' if creature else 'person', row['kind'], pack.replace('_', '-')] + row['clips'][:4]
        if creature:
            tags += [cid.split('_')[0]]
        if cid == 'new_arrival':
            tags += ['qhantom', 'lead']
        out.append(dict(_recipe(
            'character.%s.%s' % (pack, cid), 'character', name,
            'Animated %s for %s games: %d triangles, %d clips%s.' % (
                'creature' if creature else 'person', table['styles'][pack], row['measured']['total_triangles'],
                len(row['clips']), '; placeholder name' if placeholder else ''),
            tags, 'MIT', pack, {'models/%s.glb' % cid: row['glb']}, {'character.json': info},
            tier('validated', style='character audit and gate passed'), ['character:%s/%s' % (pack, cid)],
            CATALOG_THUMBS.get('character:%s/%s' % (pack, cid))), rig=rig_ref(root, 'quad16_v1' if creature else 'human16_v1')))
    return out


def rig_ref(root, rig_id):
    """'<rig id>@<version>' of a bundled rig kit contract (rigs/<id>/rig.json): the hub entry's compat.rig."""
    return '%s@%s' % (rig_id, read_json(root, 'rigs/%s/rig.json' % rig_id)['version'])


def sound_recipes(root, table):
    legacy = read_json(root, 'audio/catalog.json')['assets']
    expansion = read_json(root, 'audio/expansion/catalog.json')['assets']
    out = []

    def pack(key, rows, licence, tier_row, summary, tags):
        files, listing = {}, []
        for asset in rows:
            arc = 'sounds/' + Path(asset['file']).name
            files[arc] = asset['path']
            listing.append({'id': asset['id'], 'name': sound_name(table, asset['id']), 'file': arc, 'sha256': asset['sha256'],
                            'seconds': asset['duration'], 'loop': bool(asset['loop']), 'category': asset['category']})
        info = {'schema': 'hermes64-sound-pack/1', 'licence': licence, 'sounds': listing}
        out.append(_recipe('sound.' + key, 'sound', table['sound_packs'][key], summary, tags, licence, 'any', files,
                           {'sounds.json': info}, tier_row, ['sound:' + a['id'] for a in rows]))

    wave1 = [dict(a, path='audio/' + a['file']) for a in legacy if a.get('provenance') == 'wave1_frozen']
    pack('habitat_wave1', wave1, 'MIT', tier('owner-approved', human='owner listened and approved this set'),
         '%d original low-fi sounds from Thaw: habitat ambience, footsteps, cats, UI, pickups and two music loops.' % len(wave1),
         ['sfx', 'music', 'ambience', 'footsteps', 'cat', 'ui', 'habitat', 'low-fi'])
    cache = Path(root) / 'audio/expansion/cache'
    cached = [dict(a, file=a['id'] + '.wav', path='audio/expansion/cache/%s.wav' % a['id'])
              for a in expansion if (cache / (a['id'] + '.wav')).is_file()]
    pack('footsteps_ui', cached, 'CC0-1.0', tier('machine-checked', human='not human-approved'),
         '%d CC0 sounds: walking on %d surfaces plus menu cues.' % (len(cached), sum(a['category'] == 'footsteps' for a in cached)),
         ['sfx', 'footsteps', 'ui', 'menu', 'cc0', 'surfaces'])
    core = [dict(a, path='audio/' + a['file']) for a in legacy if a.get('provenance') == 'core_generated']
    for category in sorted({a['category'] for a in core}):
        rows = [a for a in core if a['category'] == category]
        label = table['sound_packs'][category]
        examples = []
        for asset in rows:
            words = sound_name(table, asset['id']).lower().split()
            word = ' '.join(w for w in words[1:] if not w.isdigit()) or words[0]
            if word not in examples:
                examples.append(word)
        pack(category, rows, 'MIT', tier('machine-checked', human='not human-approved'),
             ('%d original procedural sounds: %s%s.' % (len(rows), ', '.join(examples[:4]),
                                                       ' and more' if len(examples) > 4 else ''))[:160],
             ['sfx', category, 'core'] + sorted({t for a in rows for t in a.get('tags', []) if t not in (
                 'low-fi', 'soft', 'synthetic', 'approximation', 'optional-module')})[:8])
        out[-1]['name'] = label
    return out


def game_recipes(root, table):
    out = []
    for gid, (rid, rel, thumb, mixes) in GAME_SOURCES.items():
        spec = read_json(root, rel)
        binding = spec['metadata']['hermes64_pack']
        pack = read_json(root, 'packs/%s/pack.json' % binding['id'])
        files = {'source/spec.json': rel, 'packs/%s/pack.json' % binding['id']: 'packs/%s/pack.json' % binding['id']}
        authoring = ('Author source with Hermes64 tools. Compile and check after every edit. Never hand-edit generated '
                     'revisions.\n')
        kinds = [module['id'] for module in spec['gameplay']['modules']]
        out.append(_recipe(
            rid, 'game', table['games'][gid],
            'A small STORY 1.2 adventure in %d rooms with %s. Installs as a new game you can compile, check and edit.'
            % (len(spec['rooms']), mixes),
            ['game', 'modules', 'sample', 'village'] + kinds, 'MIT', pack['kit_pack_id'], files,
            {'AUTHORING.md': authoring},
            tier('validated', proof='conditional, accepted by its module policy', style='not run'),
            ['game:' + gid], thumb, story=spec['contract_version']))
    return out


def recipes(root=ROOT):
    table = names(root)
    rows = style_recipes(root, table) + kit_recipes(root, table) + character_recipes(root, table) + \
        sound_recipes(root, table) + game_recipes(root, table)
    optional, _pending = cameo(root)
    if optional:
        rows.append(optional)
    return sorted(rows, key=lambda r: r['id'])


CAMEO_NOTICE = ("Likeness included with Teknium's consent (relayed by the owner) for games made with Hermes64; not for "
                'impersonation, endorsement or misleading use. See LICENSE-CAMEO.md.')


def removed_optional(entry_id, root=ROOT):
    """True for a bundled entry of the optional cameo pack after its folder was deleted from this install: deleting
    cameo/ is the one-step removal, so the hub stops listing (and cannot rebuild) the entry."""
    return entry_id.startswith('character.cameo.') and not (Path(root) / 'cameo/cameo.json').is_file()


def cameo(root=ROOT):
    """(recipe, None) when the optional cameo pack is assembled, (None, pending note) when it is not, (None, None) if removed."""
    if not (Path(root) / 'cameo/cameo.json').is_file():
        return None, None
    info = read_json(root, 'cameo/cameo.json')
    name, _placeholder = person(names(root), info['id'])
    rid = 'character.cameo.' + info['id']
    model = Path(root) / 'cameo' / info['model']
    if info.get('status') != 'available' or not model.is_file():
        return None, {'id': rid, 'name': name, 'kind': 'character',
                      'note': ('Optional cameo pack, pending assembly: the model is not on this branch yet. Steps in '
                               'cameo/README.md; it will list as public-with-notice under cameo/LICENSE-CAMEO.md.')}
    recipe = _recipe(rid, 'character', name, 'Optional cameo character for games made with Hermes64: %d triangles; read '
                     'the notice first.' % info['tris'], ['person', 'cameo', 'likeness', 'optional'], 'MIT',
                     'any', {'models/%s' % info['model']: 'cameo/' + info['model'], 'LICENSE-CAMEO.md': 'cameo/LICENSE-CAMEO.md'},
                     {'character.json': {'schema': 'hermes64-character/1', 'id': info['id'], 'name': name, 'pack': 'cameo',
                                         'kind': 'person', 'model': 'models/' + info['model'], 'sha256': info['expected_sha256'],
                                         'notice': 'LICENSE-CAMEO.md'}},
                     tier('validated', style='character audit and gate passed (lane-characters r21)'),
                     ['character:cameo/' + info['id']])
    recipe['visibility'] = 'public-with-notice'
    recipe['notice'] = CAMEO_NOTICE
    recipe['rig'] = rig_ref(root, info.get('rig', 'human16_v1'))
    return recipe, None


def recipe_by_id(rid, root=ROOT):
    for row in recipes(root):
        if row['id'] == rid:
            return row
    return None


def single_recipe(ref, root=ROOT):
    """A recipe for ONE bundled asset named by its catalog id: kit:<id>[/<pack>], character:<pack>/<id>,
    sound:<id>, or a style/game catalog id that maps to exactly one seed entry. None if unknown."""
    table = names(root)
    kind, _, rest = (ref or '').partition(':')
    if kind == 'kit':
        kit_id, _, pack = rest.partition('/')
        kit = next((k for k in catalog_kits(root) if k['id'] == kit_id), None)
        if kit is None:
            return None
        builds = [b for b in kit['builds'] if not pack or b['pack'] == pack]
        if not builds:
            return None
        packs = sorted({b['pack'] for b in builds})
        files, models = {}, []
        for build in builds:
            arc = 'models/' + Path(build['glb']).name
            files[arc] = 'kits/' + build['glb']
            textures = []
            for tex in build['textures']:
                files['textures/' + Path(tex['file']).name] = 'kits/library/' + tex['file']
                textures.append('textures/' + Path(tex['file']).name)
            models.append({'model': arc, 'pack': build['pack'], 'preset': build['preset'], 'sha256': build['sha256'],
                           'tris': build['tri_count'], 'textures': textures})
        name = item_name(table, kit_id)
        info = {'schema': 'hermes64-kit/1', 'id': kit_id, 'name': name, 'class': kit['class'], 'version': kit['version'],
                'description': kit['description'], 'tri_limit': kit['tri_limit'], 'builds': models}
        style = packs[0] if len(packs) == 1 else 'any'
        where = table['styles'][packs[0]] if len(packs) == 1 else ' and '.join(table['styles'][p] for p in packs)
        rid = 'kit.' + kit_id.replace('.', '_') + ('.' + pack if pack else '')
        return _recipe(rid, 'kit', name, '%d low-poly model%s for %s games: %s.' % (
            len(models), '' if len(models) == 1 else 's', where, kit['description'][:80].rstrip('.')),
            ['kit', kit['class'], kit_id.split('.')[0]] + packs, 'MIT', style, files, {'kit.json': info},
            tier('validated', style='kit gate passed: budget, naming, palette, topology'), ['kit:' + kit_id])
    if kind == 'character':
        pack, _, cid = rest.partition('/')
        for row in character_recipes(root, table):
            if row['catalog_ids'] == ['character:%s/%s' % (pack, cid)]:
                return row
        row = next((r for r in read_json(root, 'characters/manifest.json')['characters']
                    if r['pack'] == pack and r['id'] == cid and r['public_release'] and not r['internal_only']), None)
        if row is None:
            return None
        creature = row['kind'] == 'animal'
        name, placeholder = (table['creatures'].get(cid, cid), False) if creature else person(table, cid)
        info = {'schema': 'hermes64-character/1', 'id': cid, 'name': name, 'placeholder_name': placeholder, 'pack': pack,
                'kind': 'creature' if creature else 'person', 'body': row['kind'], 'model': 'models/%s.glb' % cid,
                'sha256': row['sha256'], 'tris': {'body': row['measured']['body_triangles'],
                                                  'total': row['measured']['total_triangles']},
                'budget': row['budget'], 'clips': row['clips'], 'joints': row['joints'], 'props': row['props'], 'variants': []}
        return _recipe('character.%s.%s' % (pack, cid), 'character', name, 'Animated %s for %s games, not bound to a body '
                       'preset yet: %d triangles%s.' % ('creature' if creature else 'person', table['styles'][pack],
                                                       row['measured']['total_triangles'],
                                                       '; placeholder name' if placeholder else ''),
                       ['creature' if creature else 'person', row['kind'], pack, 'unbound'], 'MIT', pack,
                       {'models/%s.glb' % cid: row['glb']}, {'character.json': info},
                       tier('validated', style='character audit and gate passed'), ['character:%s/%s' % (pack, cid)])
    if kind == 'sound':
        legacy = {a['id']: dict(a, path='audio/' + a['file'], licence='MIT')
                  for a in read_json(root, 'audio/catalog.json')['assets']}
        for a in read_json(root, 'audio/expansion/catalog.json')['assets']:
            cached = 'audio/expansion/cache/%s.wav' % a['id']
            if (Path(root) / cached).is_file():
                legacy[a['id']] = dict(a, file=a['id'] + '.wav', path=cached)
        asset = legacy.get(rest)
        if asset is None:
            return None
        arc = 'sounds/' + Path(asset['file']).name
        name = sound_name(table, rest)
        approved = asset.get('provenance') == 'wave1_frozen'
        info = {'schema': 'hermes64-sound-pack/1', 'licence': asset['licence'], 'sounds': [
            {'id': rest, 'name': name, 'file': arc, 'sha256': asset['sha256'], 'seconds': asset['duration'],
             'loop': bool(asset['loop']), 'category': asset['category']}]}
        return _recipe('sound.' + rest.replace('.', '_'), 'sound', name, 'One %s %s sound, %.1f seconds.' % (
            'looping' if asset['loop'] else 'one-shot', asset['category'], asset['duration']),
            ['sfx', asset['category'], 'loop' if asset['loop'] else 'one-shot'], asset['licence'], 'any', {arc: asset['path']},
            {'sounds.json': info}, tier('owner-approved', human='owner listened and approved this set') if approved else
            tier('machine-checked', human='not human-approved'), ['sound:' + rest])
    hits = [row for row in recipes(root) if row['catalog_ids'] == [ref]]
    return hits[0] if len(hits) == 1 else None


def build(recipe, root=ROOT, version=VERSION, author=AUTHOR, source='bundled', plugin=None):
    """Deterministic (archive bytes, hub entry) for a recipe; reads only bundled files."""
    from .hub_index import plugin_version, validate_entry
    plugin = plugin or plugin_version(root)
    files = {}
    for arc, rel in recipe['files'].items():
        files[arc] = (Path(root) / rel).read_bytes()
    for arc, value in recipe['generated'].items():
        files[arc] = pretty(value) if isinstance(value, (dict, list)) else value.encode('utf-8')
    files.update(recipe.get('blobs') or {})   # project-made packs: bytes read (and checked) by the hub runtime
    meta = {'id': recipe['id'], 'name': recipe['name'], 'version': version, 'kind': recipe['kind'],
            'licence': recipe['licence'], 'author': author}
    files['README.md'] = readme(dict(meta, summary=recipe['summary']), recipe['style'], recipe['tier'])
    files['LICENSE.txt'] = licence_text(recipe['licence'], author, root)
    blob, manifest = hub_archive.build(files, meta)
    compat = {'contract': CONTRACT, 'plugin': '>=' + plugin, 'style': recipe['style']}
    for key in ('story', 'profile', 'rig'):
        if recipe.get(key):
            compat[key] = recipe[key]
    rows = manifest['files']
    entry = dict(meta, summary=recipe['summary'], tags=recipe['tags'], size=len(blob), sha256=hub_archive.sha256(blob),
                 files=rows, compat=compat, tier=dict(recipe['tier']),
                 download='archives/%s-%s.zip' % (recipe['id'], version), created_by='hermes64 ' + plugin,
                 source=source, visibility=recipe.get('visibility', 'public'), catalog_ids=list(recipe['catalog_ids']),
                 budget={'tris_max': max([r.get('tris', 0) for r in rows] or [0]), 'bytes': sum(r['bytes'] for r in rows)})
    if recipe.get('palette'):
        entry['palette'] = list(recipe['palette'])
    if recipe.get('notice'):
        entry['notice'] = recipe['notice']
    if recipe.get('thumb'):
        entry['preview'] = 'previews/%s.png' % recipe['id']
        entry['preview_source'] = THUMBS[recipe['thumb']][2]
    return blob, validate_entry(entry)
