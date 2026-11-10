"""Real KITS 3.1 build/cache integration and immutable runtime binding snapshots."""
from pathlib import Path
import hashlib, json
from .builders import select as select_builder, identity as builder_identity, command as build_command
from .glb import srgb8, inspect
from .glb_validate import validate as validate_glb
from .packs import fingerprint
from .safety import fail, encode, strict_json

def data(c,path): return strict_json(c.shipped(path).read_bytes())
def digest(b): return hashlib.sha256(b).hexdigest()
def source_fingerprint(c):
    # kits/core/*.json is generator input too (the shared N64 look convention drives texture painting)
    paths=[c.shipped('kits/build.py')]+sorted(c.shipped('kits/core').glob('*.py'))+sorted(c.shipped('kits/core').glob('*.json'))+sorted(c.shipped('kits/validate').glob('*.py'))
    return digest(b''.join(p.name.encode()+p.read_bytes() for p in paths))

def merged(base, over):
    """Recursive dict merge (over wins); lists and scalars are replaced whole."""
    out=dict(base)
    for k,v in (over or {}).items():
        out[k]=merged(out[k],v) if isinstance(v,dict) and isinstance(out.get(k),dict) else v
    return out

def n64_look(c, view):
    """Shared N64 look convention (kits/core/n64_look.json) under the pack's explicit view.json "n64" overrides."""
    path=c.root/'kits/core/n64_look.json'
    base=data(c,'kits/core/n64_look.json') if path.is_file() else {}
    return merged(base, view.get('n64') or {})

def build(c, game_path, folder, seed, pack):
    from .runner import locate
    manifest=data(c,'kits/manifest.json')
    if manifest.get('contract_version')!='3.1.0': fail('component_protocol','Expected KITS 3.1.0')
    kit_pack=pack['kit_pack_id']; recipe=data(c,'kits/packs/'+kit_pack+'/pack.json')
    game=c.project.read_json(game_path)
    # Geometry defaults are theme-agnostic. Scale at room assembly; all themed materials are pack data.
    requests=[{'id':'arch.floor_module','params':{'shape':'rect','width':3.0,'depth':3.0},'semantic':'_floor'},
              {'id':'arch.wall_module','params':{'opening':'none'},'semantic':'_wall'}]
    requests += [{'id':p['asset_id'],'params':strict_json(p['params_json']),'semantic':'preset/'+p['id']} for p in pack['presets']]
    generator_hash=source_fingerprint(c); built=0; hits=0; records=[]; overrides={}
    builder = select_builder(c.settings)
    tool = 'python' if builder == 'python' else 'blender'
    exe=locate(tool,c.settings.get(tool+'_path','')); script=c.shipped('kits/build.py')
    for req in requests:
        kits=[k for k in manifest['kits'] if k['id']==req['id']]
        if len(kits)!=1: fail('component_protocol','Unknown kit '+req['id'])
        key=digest(encode({'request':req,'seed':seed,'pack':recipe,'generator':generator_hash,'builder':builder_identity(builder),'encoding':'srgb8-v1'}))
        base='.maker/cache/assets/'+key; out=c.project.path(base+'.glb'); side=base+'.json'
        if out.exists() and c.project.path(side).exists():
            report=c.project.read_json(side)
            if digest(out.read_bytes())!=report['sha256']: fail('cache_integrity','Cached GLB changed')
            hits+=1
        else:
            out.parent.mkdir(parents=True,exist_ok=True)
            tex=c.project.path('.maker/cache/textures'); tex.mkdir(parents=True,exist_ok=True)
            argv=build_command(builder,exe,script,['--id',req['id'],'--pack',kit_pack,'--params',json.dumps(req['params'],sort_keys=True),'--seed',str(seed),'--out',str(out),'--tex-dir',str(tex)])
            result=c.runner.run(argv,c.project.root,timeout=180)
            c.project.write_json(folder+'/'+req['semantic'].replace('/','-')+'.'+builder+'.process.json',dict(result,argv=argv))
            if result['returncode']!=0: fail('asset_failed',builder+' builder failed (check '+tool+'_path): '+result['stdout'][-1600:]+result['stderr'][-400:])
            sidecar=c.project.read_json(base+'.glb.json')
            if sidecar.get('status')!='passed' or digest(out.read_bytes())!=sidecar.get('sha256'): fail('asset_failed','Builder validation/hash failed')
            original=digest(out.read_bytes()); converted=srgb8(out.read_bytes()); c.project.write_bytes(base+'.glb',converted)
            report={'source_sha256':original,**inspect(converted),'validation':sidecar['validation'],'generator_sha256':generator_hash,'request':req}
            if report['tri_count']>kits[0]['tri_limit']: fail('asset_failed','Independent triangle budget exceeded')
            structural=validate_glb(converted,base+'.glb',kits[0]['tri_limit'])
            report['structure']={'ok':structural.ok,'errors':[i['code']+' '+i['path'] for i in structural.issues if i['severity']=='error'][:8]}
            if not structural.ok: fail('asset_failed','GLB structural validation failed: '+'; '.join(report['structure']['errors']))
            c.project.write_json(side,report); built+=1
        records.append(dict(report,file=base+'.glb'))
        overrides[req['semantic']]={'path':str(out),'sha256':report['sha256'],'tri_count':report['tri_count']}
    binding=data(c,'packs/'+pack['id']+'/bindings.json') if (c.root/'packs'/pack['id']/'bindings.json').is_file() else data(c,'packs/'+kit_pack+'/bindings.json')
    shell_report=build_shells(c,game,pack,seed,folder,exe,script,generator_hash,recipe,manifest,binding,overrides,records)
    built+=shell_report['built']; hits+=shell_report['cache_hits']
    for ref,row in binding['assets'].items():
        p=c.shipped(row['glb']); raw=p.read_bytes(); measured=inspect(raw)
        if measured['sha256']!=row['sha256']: fail('asset_integrity','Binding hash mismatch '+ref)
        if measured['vertex_color_encoding']!='srgb8': fail('asset_encoding','Expected explicit sRGB8')
        structural=validate_glb(raw,row['glb'])
        if not structural.ok: fail('asset_integrity','GLB structural validation failed for '+ref+': '+'; '.join(i['code']+' '+i['path'] for i in structural.issues if i['severity']=='error')[:400])
    report={'status':'passed','game_hash':game['game_hash'],'pack_sha256':fingerprint(pack),'built':built,'cache_hits':hits,'records':records,'binding_assets_verified':len(binding['assets']),'room_shells':shell_report['rooms'],
            'style_validation':{'status':'passed','scope':'GLB integrity + structural validation (adventure_maker/glb_validate.py), measured triangle counts, encoding; source per-asset texture/palette/topology validators. Rendered room budgets checked by screenshot pass. Character fidelity excluded.'},'character_status':'placeholders; no rig/animation acceptance'}
    c.project.write_json('.maker/assets/current.json',{'pack_sha256':fingerprint(pack),'overrides':overrides})
    if (c.root/'bindings.json').is_file():
        runtime=c.prepare_runtime(game_path,folder)
        cast=c.project.read_json(folder+'/runtime/bindings.json')['characters']
        real=sum(Path(row['path']).is_file() and not row.get('placeholder',True) for row in cast)
        report['runtime_path']=str(runtime.relative_to(c.project.root))
        report['character_status']={'status':'bound' if real==len(cast) else 'fallback_available',
                                    'real_selectors':real,'fallback_selectors':len(cast)-real,
                                    'scope':'hash-verified actor runtime; rendered room acceptance requires open/screenshots'}
    c.project.write_json(folder+'/assets/report.json',report)
    return report

def view_data(c, pack):
    base=pack['id'] if (c.root/'packs'/pack['id']/'view.json').is_file() else pack['kit_pack_id']
    return data(c,'packs/'+base+'/view.json') if (c.root/'packs'/base/'view.json').is_file() else {}

def build_shells(c, game, pack, seed, folder, exe, script, generator_hash, recipe, manifest, binding, overrides, records):
    """Per-room kit landscapes/shells (pack data -> arch.room_shell per interior room, terrain.yard per exterior room)
    through the same kit pipeline, validators and cache as every other asset. Candidates fall back to safer
    variants; a room whose candidates are all rejected keeps the legacy look (reported), so a pack/room combination
    can never fail the build."""
    builder = select_builder(c.settings)
    from .shells import plan_game as plan_shells
    from .yards import plan_game as plan_yards
    view = view_data(c, pack)
    plans = {}
    for rid, pl in plan_shells(game, view.get('shells') or {}, manifest, binding).items():
        plans['shell/' + rid] = {'id': 'arch.room_shell', 'room': rid, 'row': 'shell_plan', 'extra': 'openings', 'candidates': pl['candidates']}
    for rid, pl in plan_yards(game, view.get('yards') or {}).items():
        plans['yard/' + rid] = {'id': 'terrain.yard', 'room': rid, 'row': 'yard_plan', 'extra': 'exits', 'candidates': pl['candidates']}
    limits = {k['id']: k['tri_limit'] for k in manifest['kits']}
    rooms = {sem: {'status': 'legacy', 'reason': 'no candidates'} for sem in sorted(plans)}
    built = hits = 0
    pending = {sem: 0 for sem in plans if plans[sem]['id'] in limits}
    for sem in plans:
        if plans[sem]['id'] not in limits:
            rooms[sem] = {'status': 'legacy', 'reason': 'kit %s not in this bundle' % plans[sem]['id']}
    tex = c.project.path('.maker/cache/textures'); tex.mkdir(parents=True, exist_ok=True)
    outdir = c.project.path('.maker/cache/assets'); outdir.mkdir(parents=True, exist_ok=True)
    while pending:
        jobs = []; keyed = {}
        for sem in sorted(pending):
            pl = plans[sem]
            cand = pl['candidates'][pending[sem]]
            req = {'id': pl['id'], 'params': cand['params'], 'semantic': sem}
            key = digest(encode({'request': req, 'seed': seed, 'pack': recipe, 'generator': generator_hash, 'builder': builder_identity(builder), 'encoding': 'srgb8-v1'}))
            keyed[sem] = (key, req, cand)
            if not c.project.path('.maker/cache/assets/' + key + '.json').exists() and not any(j['out'] == key + '.glb' for j in jobs):
                jobs.append({'id': req['id'], 'pack': pack['kit_pack_id'], 'params': req['params'], 'seed': seed, 'out': key + '.glb'})
        if jobs:
            jp = '.maker/cache/room-kit-jobs-' + digest(encode(jobs))[:16] + '.json'; c.project.write_json(jp, jobs)
            argv = build_command(builder, exe, script, ['--batch', str(c.project.path(jp)),
                                                        '--out-dir', str(outdir), '--tex-dir', str(tex)])
            result = c.runner.run(argv, c.project.root, timeout=180)
            c.project.write_json(folder + '/room-kits-' + str(len(records)) + '.' + builder + '.process.json', dict(result, argv=argv))
            for job in jobs:
                key = job['out'][:-4]; base = '.maker/cache/assets/' + key; out = c.project.path(base + '.glb')
                sidecar = c.project.read_json(base + '.glb.json') if c.project.path(base + '.glb.json').exists() else {'status': 'rejected'}
                if sidecar.get('status') != 'passed' or not out.exists() or digest(out.read_bytes()) != sidecar.get('sha256'):
                    c.project.write_json(base + '.json', {'status': 'failed', 'kit_status': sidecar.get('status'), 'error': sidecar.get('error'),
                                                          'validation': {k: v.get('reason') for k, v in (sidecar.get('validation') or {}).items() if not v.get('ok')}})
                    continue
                original = digest(out.read_bytes()); converted = srgb8(out.read_bytes()); c.project.write_bytes(base + '.glb', converted)
                report = {'status': 'passed', 'source_sha256': original, **inspect(converted), 'validation': sidecar['validation'],
                          'generator_sha256': generator_hash, 'request': {'id': job['id'], 'params': job['params']}, 'meta': sidecar.get('meta', {})}
                structural = validate_glb(converted, base + '.glb', limits[job['id']])
                report['structure'] = {'ok': structural.ok, 'errors': [i['code'] + ' ' + i['path'] for i in structural.issues if i['severity'] == 'error'][:8]}
                if report['tri_count'] > limits[job['id']] or not structural.ok: report['status'] = 'failed'
                c.project.write_json(base + '.json', report); built += 1
        for sem, (key, req, cand) in list(keyed.items()):
            pl = plans[sem]
            base = '.maker/cache/assets/' + key; report = c.project.read_json(base + '.json')
            if report.get('status') == 'passed' and c.project.path(base + '.glb').exists() and digest(c.project.path(base + '.glb').read_bytes()) == report['sha256']:
                if not any(j['out'] == key + '.glb' for j in jobs): hits += 1
                records.append(dict(report, file=base + '.glb'))
                overrides[sem] = {'path': str(c.project.path(base + '.glb')), 'sha256': report['sha256'], 'tri_count': report['tri_count'],
                                  'meta': report['meta'], pl['row']: {pl['extra']: cand[pl['extra']], 'params': cand['params']}}
                rooms[sem] = {'status': 'built', 'kit': pl['id'], 'candidate': pending[sem], 'plan': cand['params'].get('plan'),
                              'tri_count': report['tri_count']}
                del pending[sem]
            else:
                pending[sem] += 1
                rooms[sem] = {'status': 'legacy', 'reason': 'kit rejected every candidate', 'last': report.get('error') or report.get('validation')}
                if pending[sem] >= len(pl['candidates']): del pending[sem]
    return {'built': built, 'cache_hits': hits, 'rooms': rooms}

def combat_cues(c, game):
    """COMBAT lane: the catalog cues a combat game can play (readability defaults + archetype telegraph audio), staged
    as 'cue:<catalog id>' rows with the catalog's own sha256. Games without a combat module stage nothing new."""
    modules = (game.get('gameplay') or {}).get('modules') or []
    combat = next((m for m in modules if m.get('id') == 'combat'), None)
    if combat is None:
        return {}
    profile = strict_json(c.shipped('runtime/godot/modules/combat/readability.json').read_bytes())
    wanted = {profile['telegraph'].get('audio', '')}
    wanted.update(v for k, v in profile['feedback'].items() if k.endswith('_audio'))
    wanted.update(row.get('audio', '') for row in profile.get('templates', {}).values())
    # Fixed runtime cues: blocks/armour/deflects, projectile launch and shockwave impact (combat/runtime.gd).
    wanted.update(('core.combat.block.metal', 'core.combat.projectile.energy', 'core.combat.explosion.small'))
    for archetype in combat.get('entities', {}).get('archetypes', []):
        wanted.add((archetype.get('robot') or {}).get('cue', ''))
        for pattern in (archetype.get('boss') or {}).get('patterns', []):
            wanted.add(pattern.get('cue', ''))
    catalog = {row['id']: row for row in data(c, 'audio/catalog.json')['assets']}
    out = {}
    for cue in sorted(w for w in wanted if w):
        row = catalog.get(cue)
        if row is None:
            fail('audio_cue', 'Unknown catalog cue ' + cue)
        path = c.shipped('audio/' + row['file'])
        raw = path.read_bytes()
        if digest(raw) != row['sha256']:
            fail('asset_integrity', 'Catalog cue changed: ' + cue)
        out['cue:' + cue] = {'path': str(path), 'sha256': row['sha256']}
    return out

def imported_audio(c):
    """AUDIOPIPE: the project's own imported music/voice/cues (audio/slots.json + audio/import/manifest.json), lowered
    to runtime audio.json rows. Projects without slots stage nothing new. Hashes are re-checked: a changed file
    fails the build instead of silently playing something else. Presentation only; story data is untouched."""
    if not c.project.path('audio/slots.json').is_file():
        return {}
    from . import audio_import as ai
    folder = c.project.path('audio/import')
    if not (folder / 'manifest.json').is_file():
        fail('audio_import', 'audio/slots.json exists but nothing was imported (hermes64_audio action=import)')
    manifest, problems = ai.verify(folder)
    if problems:
        fail('asset_integrity', 'Imported audio changed: ' + '; '.join(problems[:5]))
    slots = ai.validate_slots(c.project.read_json('audio/slots.json'), manifest['assets'])
    return ai.runtime_rows(slots, manifest['assets'], folder)

def runtime_snapshot(c, game, folder):
    from .packs import Packs
    pack=Packs(c.settings,c.project).selected(game)
    pack_id=pack['id']; kit_pack=pack['kit_pack_id']
    base=pack_id if (c.root/'packs'/pack_id/'bindings.json').is_file() else kit_pack
    bindings=data(c,'packs/'+base+'/bindings.json'); mapping={}
    for ref,row in bindings['assets'].items():
        path=c.shipped(row['glb']); raw=path.read_bytes()
        if digest(raw)!=row['sha256']: fail('asset_integrity','Hash differs for '+ref)
        mapping[ref]=dict(row,path=str(path),**inspect(raw))
    cached=c.project.path('.maker/assets/current.json')
    if cached.exists():
        cached=c.project.read_json('.maker/assets/current.json')
        if cached['pack_sha256']==fingerprint(pack): mapping.update(cached['overrides'])
    else:
        mapping['_floor']=mapping['arch.floor_module']; mapping['_wall']=mapping['arch.wall_module']
    # Runtime refuses altered GLBs; compiled story identifiers/parameters are never mutated.
    characters=data(c,'kits/bindings.json')['characters']
    for row in characters:
        path=c.shipped(row['glb'])
        if digest(path.read_bytes())!=row['sha256']: fail('asset_integrity','Character binding changed')
        row['path']=str(path)
    theme=data(c,'packs/'+base+'/view.json'); theme['pack_id']=pack_id
    theme['n64']=n64_look(c,theme)
    theme['fog']={'color':pack['lighting']['fog_colour'],'near':pack['lighting']['fog_start'],'far':pack['lighting']['fog_end']}
    theme['env_root']=str(c.shipped('kits/library/'+kit_pack+'/env'))
    sound={}
    for event,rel in pack['sound_palette'].items():
        path=c.shipped(rel); sound[event]={'path':str(path),'sha256':digest(path.read_bytes())}
    sound.update(combat_cues(c, game))
    sound.update(imported_audio(c))
    c.project.write_json(folder+'/runtime/audio.json',sound)
    c.project.write_json(folder+'/runtime/bindings.json',{'assets':mapping,'characters':characters})
    c.project.write_json(folder+'/runtime/theme.json',theme)
