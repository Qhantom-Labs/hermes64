"""Small independent GLB reader and exported-artifact audit (stdlib)."""
import json,struct,hashlib,math
from pathlib import Path

class GLB:
    def __init__(self,path):
        self.data=Path(path).read_bytes();magic,version,length=struct.unpack_from('<4sII',self.data)
        if magic!=b'glTF' or version!=2 or length!=len(self.data):raise ValueError('invalid GLB')
        n,typ=struct.unpack_from('<II',self.data,12);self.doc=json.loads(self.data[20:20+n]);off=20+n
        self.bin=b''
        if off<len(self.data):n,typ=struct.unpack_from('<II',self.data,off);self.bin=self.data[off+8:off+8+n]
    def accessor(self,index):
        a=self.doc['accessors'][index];b=self.doc['bufferViews'][a['bufferView']]
        fm={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}[a['componentType']]
        count={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']];fmt='<'+fm*count
        stride=b.get('byteStride',struct.calcsize(fmt));start=b.get('byteOffset',0)+a.get('byteOffset',0)
        v=[struct.unpack_from(fmt,self.bin,start+i*stride) for i in range(a['count'])]
        if a.get('normalized'):
            den={5120:127,5121:255,5122:32767,5123:65535}[a['componentType']];v=[tuple(max(-1,x/den) for x in row) for row in v]
        return v
    def audit(self,kind=None,n_clips=7):
        """kind 'human'/'quad' enables the body budget check (STEER-5 §5); every rigid prop node is checked against
        its own budget (<= 200 tris) and body/prop triangles are reported separately."""
        d=self.doc;prims=[p for m in d.get('meshes',[]) for p in m['primitives']]
        animations=[];errors=[]
        for an in d.get('animations',[]):
            sam=an['samplers'];times=[v[0] for s in sam for v in self.accessor(s['input'])]
            interpolation=sorted({s.get('interpolation','LINEAR') for s in sam})
            animations.append({'name':an['name'],'samplers':len(sam),'interpolation':interpolation,'duration':max(times)-min(times),'key_times':sorted({round(t,7) for t in times})})
            if interpolation!=['STEP']:errors.append('non_step_animation')
        tris=sum(d['accessors'][p['indices']]['count']//3 for p in prims)
        # Skinned body primitives need joints/weights; rigid props (kit_acc_*) are unskinned mesh nodes parented to a
        # joint node (round 12: audit no longer assumes every primitive is skinned).
        nodes=d.get('nodes',[]);skinned_meshes={n['mesh'] for n in nodes if 'mesh' in n and 'skin' in n}
        joints=set(d['skins'][0]['joints']) if d.get('skins') else set()
        parent={c:i for i,n in enumerate(nodes) for c in n.get('children',[])}
        for mi,m in enumerate(d.get('meshes',[])):
            for p in m['primitives']:
                need=['POSITION','NORMAL','TEXCOORD_0','COLOR_0']+(['JOINTS_0','WEIGHTS_0'] if mi in skinned_meshes else [])
                if any(k not in p['attributes'] for k in need):errors.append('missing_attributes')
                if mi in skinned_meshes:
                    for w in self.accessor(p['attributes']['WEIGHTS_0']):
                        if abs(sum(w)-1)>.001:errors.append('unnormalized_skin');break
        for i,n in enumerate(nodes):
            if 'mesh' in n and 'skin' not in n and parent.get(i) not in joints:errors.append('rigid_prop_not_on_joint')
        if len(d.get('skins',[]))!=1 or len(d['skins'][0]['joints'])!=16:errors.append('skin_not_16')
        # lane-combat-art: n_clips=13 for the combat cast (7 shared + 6 combat clips); default 7 keeps the r21 audit
        if len(animations)!=n_clips:errors.append('missing_clips')
        names=[n.get('name','') for n in d.get('nodes',[])]
        if 'kit_body' not in names:errors.append('bad_mesh_name')
        mt=lambda mi:sum(d['accessors'][p['indices']]['count']//3 for p in d['meshes'][mi]['primitives'])  # noqa: E731
        tris_body=sum(mt(n['mesh']) for n in nodes if 'mesh' in n and 'skin' in n)
        tris_props={n.get('name','node%d'%i):mt(n['mesh']) for i,n in enumerate(nodes) if 'mesh' in n and 'skin' not in n}
        if kind=='human' and tris_body>=700:errors.append('body_over_budget')
        if kind=='quad' and tris_body>300:errors.append('body_over_budget')
        if any(v>200 for v in tris_props.values()):errors.append('prop_over_budget')
        return {'pass':not errors,'errors':errors,'sha256':hashlib.sha256(self.data).hexdigest(),'bytes':len(self.data),'tris':tris,
          'tris_body':tris_body,'tris_props':tris_props,
          'mesh_vertices':sum(d['accessors'][p['attributes']['POSITION']]['count'] for p in prims),
          'bones':[d['nodes'][i]['name'] for i in d['skins'][0]['joints']], 'animations':animations,
          'materials':[{k:m[k] for k in ('name','extensions','extras','pbrMetallicRoughness') if k in m} for m in d.get('materials',[])],
          'samplers':d.get('samplers',[]),'image_count':len(d.get('images',[]))}

if __name__=='__main__':
    import sys
    for p in sys.argv[1:]:print(json.dumps(GLB(p).audit(),indent=2))
