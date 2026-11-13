"""Static Asset -> runtime GLB, using the existing numpy geometry/UV/light/texture code.

The binary writer itself is stdlib. No bpy, mathutils or subprocess. Coordinate
conversion is the proper rotation (x,y,z)->(x,z,-y); UV v becomes 1-v. Colours are
explicit display-space bytes, exactly as the runtime's Blender srgb8 adapter.
"""
import hashlib
import math
from pathlib import Path

import numpy as np

from . import bake, png
from .glbwrite import Writer, f32
from .palette import srgb_to_linear
from .packs import TEXTURED_KINDS
from .texgen import make_texture, alpha_mask
from .triangulate import polygon3d


def yup(p):
    return (f32(p[0]), f32(p[2]), f32(-p[1]))


def normals(mesh):
    """Angle-weighted vertex normals; flat polygon loops keep their face normal.

Do not use bake.corner_normals here: its welded/55-degree light model is not
Blender's mesh shading normal model.
"""
    v = np.asarray(mesh.v, dtype=np.float32).astype(np.float64)
    fn = bake.face_normals(v, mesh.f)
    vn = np.zeros_like(v)
    for fi, face in enumerate(mesh.f):
        if not mesh.s[fi]:
            continue
        for j, vi in enumerate(face):
            a, b = v[face[j-1]]-v[vi], v[face[(j+1)%len(face)]]-v[vi]
            la, lb = np.linalg.norm(a), np.linalg.norm(b)
            angle = math.acos(float(np.clip(np.dot(a,b)/max(la*lb,1e-30),-1,1)))
            vn[vi] += fn[fi]*angle
    lengths = np.linalg.norm(vn, axis=1)
    vn /= np.maximum(lengths[:,None], 1e-30)
    return [[vn[vi] if mesh.s[fi] else fn[fi] for vi in face] for fi,face in enumerate(mesh.f)]


class Materials:
    def __init__(self, writer, pack, tex_dir, extras=None, conform=None):
        self.w, self.pack, self.tex_dir = writer, pack, Path(tex_dir)
        # STYLEENGINE: per-asset texture conform (extra soften passes / dither) for every textured role; None (every
        # asset without a conform block) paints exactly as before.
        self.conform = conform
        self.cache, self.written = {}, {}
        # DUNGEONKIT (additive): generator-declared runtime hints per role (asset.meta["material_extras"], e.g. the lake
        # kit's water vertex wobble or a waterfall's own scroll). Only known keys, merged into extras.n64; generators that
        # declare nothing export byte-identical GLBs.
        self.extras = {r: {k: v for k, v in (e or {}).items() if k in ('scroll', 'wobble', 'alpha')}
                       for r, e in (extras or {}).items()}
        self.w.doc.update(materials=[], images=[], textures=[], samplers=[{'magFilter':9729,'minFilter':9987}])

    def get(self, role):
        if role in self.cache:
            return self.cache[role]
        spec = self.pack.mat(role)
        kind = spec['kind']
        info = {'kind':kind,'role':role,'pack':self.pack.id,'vertex_color_encoding':'srgb8'}
        if spec.get('tile_m'):
            info['tile_m'] = float(spec['tile_m'])
        m = {'name':'mat_%s_%s'%(self.pack.id,role), 'extras':{'n64':info}}
        if spec.get('double_sided', False) or kind == 'card_alpha':
            m['doubleSided'] = True
        if kind in ('chrome_env','glass_env'):
            tint = srgb_to_linear(np.array(self.pack.pal.rgb(spec['tint']))/255.)
            m['pbrMetallicRoughness'] = {'baseColorFactor':[f32(x) for x in tint]+[1],
                                       'roughnessFactor': f32(.2 if kind=='chrome_env' else .05)}
            info.update(env=spec['env'],tint=spec['tint'])
        elif kind in TEXTURED_KINDS:
            tex = spec['texture']
            if self.conform:
                from .conform import conformed_texture_spec
                tex = conformed_texture_spec(tex, self.conform.get('soften', 0), self.conform.get('dither'))
            arr = make_texture(tex,self.pack.pal,self.pack.seed_id,role)
            if kind == 'card_alpha':
                a = alpha_mask(spec['texture'].get('alpha','disc'),arr.shape[0],self.pack.seed_id,role)
                arr = np.concatenate([arr,a[:,:,None]],2)
            name = 'tex_%s_%s'%(self.pack.id,role)
            raw = png.encode(arr)
            self.tex_dir.mkdir(parents=True,exist_ok=True)
            path = self.tex_dir/(name+'.png')
            if not path.exists() or path.read_bytes()!=raw:
                path.write_bytes(raw)
            self.written[name] = {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(), 'size':[int(arr.shape[1]),int(arr.shape[0])]}
            i = len(self.w.doc['images'])
            self.w.doc['images'].append({'bufferView':self.w.view(raw),'mimeType':'image/png','name':name})
            self.w.doc['textures'].append({'source':i,'sampler':0})
            m['extensions'] = {'KHR_materials_unlit':{}}
            self.w.doc['extensionsUsed'] = ['KHR_materials_unlit']
            m['pbrMetallicRoughness'] = {'baseColorTexture':{'index':i},'metallicFactor':0,'roughnessFactor':.9}
            info['texture'] = name
            if kind == 'water':
                info['scroll'] = [f32(x) for x in spec.get('scroll',[.02,.01])]
                for k, v in self.extras.get(role, {}).items():
                    info[k] = [f32(x) for x in v] if isinstance(v, (list, tuple)) else f32(v)
            if kind == 'card_alpha':
                m.update(alphaMode='MASK')  # glTF's default alphaCutoff is 0.5, as in Blender.
        else:
            raise ValueError('unsupported material kind '+kind)
        i = len(self.w.doc['materials'])
        self.w.doc['materials'].append(m)
        self.cache[role] = i
        return i


def build(asset, pack, out, tex_dir):
    if asset.character:
        raise ValueError('Python builder cannot export skins/armatures; use builder=blender and configure blender_path (Blender required)')
    w = Writer()
    w.doc['asset']['extras'] = {'vertex_color_encoding':'srgb8', 'vertex_color_note':
        'Display-space bytes, intentionally nonstandard. Use Hermes64 N64 shader, not generic glTF material.'}
    w.doc.update(nodes=[],meshes=[],scenes=[{'name':'Scene','nodes':[]}],scene=0)
    mf = Materials(w,pack,tex_dir,asset.meta.get('material_extras'),asset.meta.get('texture_conform'))
    rig = bake.asset_rig(pack.light_rig, asset)  # DUNGEONKIT: opt-in baked point lights / ray AO (pack data)
    nodes = sorted(asset.nodes,key=lambda node:node.name)  # Blender exports objects in name order.
    by_name = {n.name:i for i,n in enumerate(nodes)}
    if len(by_name)!=len(nodes):
        raise ValueError('duplicate node name')
    # Check complete hierarchy before writing files; origins are world-space pivots.
    for n in nodes:
        seen = {n.name}
        p = n.parent
        while p is not None:
            p = p.name if hasattr(p,'name') else p
            if p not in by_name or p in seen:
                raise ValueError('invalid node parent or hierarchy cycle')
            seen.add(p)
            p = nodes[by_name[p]].parent
    ramp = [pack.pal.rgb(i) for i in pack.light_ramp]
    for ni,node in enumerate(nodes):
        mesh = node.mesh
        uv = bake.corner_uvs(mesh,lambda r:float(pack.mat(r).get('tile_m',1)))
        light = bake.bake_corner_light(mesh,rig,len(ramp),lambda r:pack.mat(r)['kind'])
        nr = normals(mesh)
        roles = list(dict.fromkeys(mesh.r))
        primitives = []
        for role in roles:
            positions, norms, uvs, colours, indices, cache = [], [], [], [], [], {}
            for fi, face in enumerate(mesh.f):
                if mesh.r[fi] != role:
                    continue
                corners = []
                for ci,vi in enumerate(face):
                    p = yup([f32(mesh.v[vi][j]-node.origin[j]) for j in range(3)])
                    # Blender glTF exporter rounds loop normals to 4 decimal
                    # places, then normalizes float32, before split/dedup.
                    nn = np.round(np.asarray(nr[fi][ci], dtype=np.float32), 4)
                    nn /= max(float(np.linalg.norm(nn)), 1e-30)
                    n = yup(nn)
                    u = (f32(uv[fi][ci][0]), f32(1-f32(uv[fi][ci][1])))
                    c = tuple(int(x) for x in ramp[light[fi][ci]])+(255,)
                    # Original vertex ID participates in Blender's split/dedup key.
                    key = (vi,p,n,u,c)
                    if key not in cache:
                        cache[key] = len(positions)
                        positions.append(p); norms.append(n); uvs.append(u); colours.append(c)
                    corners.append(cache[key])
                for tri in polygon3d([mesh.v[v] for v in face]):
                    indices.extend(corners[c] for c in tri)
            attrs = {name:w.accessor(rows,typ,ct,normalized) for name,rows,typ,ct,normalized in [
                ('POSITION',positions,'VEC3',5126,False), ('NORMAL',norms,'VEC3',5126,False),
                ('TEXCOORD_0',uvs,'VEC2',5126,False), ('COLOR_0',colours,'VEC4',5121,True)]}
            idx = w.accessor([(i,) for i in indices],'SCALAR',5123 if len(positions)<65536 else 5125,target=34963)
            primitives.append({'attributes':attrs,'indices':idx,'material':mf.get(role)})
        w.doc['meshes'].append({'name':node.name+'_mesh','primitives':primitives})
        row = {'mesh':ni,'name':node.name}
        parent = node.parent.name if hasattr(node.parent,'name') else node.parent
        origin = node.origin
        if parent is not None:
            po = nodes[by_name[parent]].origin
            origin = tuple(origin[i]-po[i] for i in range(3))
        t = yup(origin)
        if any(t):
            row['translation'] = list(t)
        w.doc['nodes'].append(row)
    for ni,node in enumerate(nodes):
        parent = node.parent.name if hasattr(node.parent,'name') else node.parent
        if parent is None:
            w.doc['scenes'][0]['nodes'].append(ni)
        else:
            w.doc['nodes'][by_name[parent]].setdefault('children',[]).append(ni)
    raw = w.encode()
    Path(out).parent.mkdir(parents=True,exist_ok=True)
    Path(out).write_bytes(raw)
    return raw, {'textures':mf.written,'animations':False}
