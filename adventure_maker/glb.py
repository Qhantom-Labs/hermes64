"""Small stdlib GLB reader/normalizer. Runtime palette encoding is explicit nonstandard sRGB8."""
import hashlib, json, math, struct

def read(data):
    magic, version, length = struct.unpack_from('<4sII', data)
    if magic != b'glTF' or version != 2 or length != len(data): raise ValueError('invalid GLB')
    pos=12; doc=None; binary=b''
    while pos < length:
        n,k=struct.unpack_from('<I4s',data,pos); body=data[pos+8:pos+8+n]; pos+=8+n
        if k==b'JSON': doc=json.loads(body)
        elif k==b'BIN\0': binary=body
    if doc is None: raise ValueError('missing JSON')
    return doc, bytearray(binary)

def encode(doc, binary):
    doc['buffers']=[{'byteLength':len(binary)}]
    j=json.dumps(doc,separators=(',',':'),sort_keys=True).encode(); j+=b' '*(-len(j)%4)
    b=bytes(binary); b+=b'\0'*(-len(b)%4)
    return struct.pack('<4sII',b'glTF',2,28+len(j)+len(b))+struct.pack('<I4s',len(j),b'JSON')+j+struct.pack('<I4s',len(b),b'BIN\0')+b

def accessor(doc,binary,index):
    a=doc['accessors'][index]; v=doc['bufferViews'][a['bufferView']]
    fmt,size={5121:('B',1),5123:('H',2),5125:('I',4),5126:('f',4)}[a['componentType']]
    width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
    offset=v.get('byteOffset',0)+a.get('byteOffset',0); stride=v.get('byteStride',size*width)
    values=[struct.unpack_from('<'+fmt*width,binary,offset+i*stride) for i in range(a['count'])]
    if a.get('normalized') and fmt!='f':
        scale=255 if fmt=='B' else 65535
        values=[tuple(x/scale for x in row) for row in values]
    return values

def srgb8(data):
    doc,b=read(data)
    if doc.get('asset',{}).get('extras',{}).get('vertex_color_encoding')=='srgb8': return data
    indices=sorted({p['attributes']['COLOR_0'] for m in doc.get('meshes',[]) for p in m['primitives'] if 'COLOR_0' in p['attributes']})
    for index in indices:
        a=doc['accessors'][index]; values=accessor(doc,b,index); out=bytearray()
        for row in values:
            for i,x in enumerate(row):
                if i<3: x=12.92*x if x<=0.0031308 else 1.055*max(x,0)**(1/2.4)-0.055
                out.append(max(0,min(255,round(x*255))))
        b+=b'\0'*(-len(b)%4); vi=len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(out),'target':34962}); b+=out
        a.update(bufferView=vi,byteOffset=0,componentType=5121,normalized=True)
        a.pop('min',None); a.pop('max',None)
    doc.setdefault('asset',{}).setdefault('extras',{}).update(vertex_color_encoding='srgb8',vertex_color_note='Display-space bytes, intentionally nonstandard. Use Hermes64 N64 shader, not generic glTF material.')
    for m in doc.get('materials',[]): m.setdefault('extras',{}).setdefault('n64',{})['vertex_color_encoding']='srgb8'
    return encode(doc,b)

def placeholder(params,animal=False):
    """Static visual marker only. No rig, animation, or costume fidelity claim."""
    colour=params.get('colour','#888888'); suit=params.get('suit',{})
    boxes=[]
    if animal:
        boxes=[([0,.25,0],[.42,.3,.65],colour),([0,.48,.3],[.32,.3,.32],colour),([-.12,.69,.3],[.09,.16,.12],colour),([.12,.69,.3],[.09,.16,.12],colour),([0,.27,-.48],[.1,.1,.4],colour)]
        boxes += [([x,.09,z],[.09,.18,.1],colour) for x in (-.15,.15) for z in (-.22,.22)]
    else:
        vest=suit.get('vest_colour',colour); bottom=suit.get('trouser_colour','#30343e')
        boxes=[([0,.95,0],[.62,.65,.4],vest),([0,1.48,0],[.52,.5,.48],'#c7d3df'),([0,1.47,.245],[.36,.28,.03],'#080d18')]
        boxes += [([x,.4,0],[.22,.65,.32],bottom) for x in (-.17,.17)]
        boxes += [([x,.13,.05],[.24,.24,.42],'#171d2a') for x in (-.17,.17)]
        boxes += [([x,.83,0],[.18,.66,.23],suit.get('sweater_colour',colour)) for x in (-.43,.43)]
    pos=[]; normals=[]; colors=[]; indices=[]
    faces=[([1,0,0],[1,5,6,2]),([-1,0,0],[4,0,3,7]),([0,1,0],[3,2,6,7]),([0,-1,0],[4,5,1,0]),([0,0,1],[5,4,7,6]),([0,0,-1],[0,1,2,3])]
    for center,size,color in boxes:
        corners=[[center[i]+s[i]*size[i]/2 for i in range(3)] for s in [(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]]
        rgb=[int(color.lstrip('#')[i:i+2],16) for i in (0,2,4)]+[255]
        for norm,face in faces:
            start=len(pos); pos += [corners[i] for i in face]; normals += [norm]*4; colors += [rgb]*4
            indices += [start,start+1,start+2,start,start+2,start+3]
    doc={'asset':{'version':'2.0','extras':{'vertex_color_encoding':'srgb8','placeholder':True}},'bufferViews':[],'accessors':[],'nodes':[{'mesh':0,'name':'placeholder_cat' if animal else 'placeholder_person'}],'scenes':[{'nodes':[0]}],'scene':0,'materials':[{'name':'placeholder_marker','extensions':{'KHR_materials_unlit':{}},'extras':{'n64':{'kind':'baked_unlit','vertex_color_encoding':'srgb8'}}}],'extensionsUsed':['KHR_materials_unlit']}
    b=bytearray()
    def add(values,typ,fmt,component,normalized=False):
        b.extend(b'\0'*(-len(b)%4)); raw=b''.join(struct.pack('<'+fmt*len(v),*v) for v in values)
        vi=len(doc['bufferViews']); doc['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(raw)}); b.extend(raw)
        a={'bufferView':vi,'componentType':component,'count':len(values),'type':typ}
        if normalized: a['normalized']=True
        if typ=='VEC3': a.update(min=[min(v[i] for v in values) for i in range(3)],max=[max(v[i] for v in values) for i in range(3)])
        doc['accessors'].append(a); return len(doc['accessors'])-1
    p=add(pos,'VEC3','f',5126); n=add(normals,'VEC3','f',5126); c=add(colors,'VEC4','B',5121,True); ind=add([[i] for i in indices],'SCALAR','H',5123)
    doc['meshes']=[{'primitives':[{'attributes':{'POSITION':p,'NORMAL':n,'COLOR_0':c},'indices':ind,'material':0}]}]
    return encode(doc,b)

def inspect(data):
    d,b=read(data); tris=0
    for m in d.get('meshes',[]):
        for p in m['primitives']: tris += d['accessors'][p['indices'] if 'indices' in p else p['attributes']['POSITION']]['count']//3
    return {'sha256':hashlib.sha256(data).hexdigest(),'tri_count':tris,'bone_names':[d['nodes'][i].get('name','') for s in d.get('skins',[]) for i in s['joints']],'animations':[x.get('name','') for x in d.get('animations',[])],'vertex_color_encoding':d.get('asset',{}).get('extras',{}).get('vertex_color_encoding')}
