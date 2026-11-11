"""CYBERKIT interiors: six architectural shells and ten reusable furniture/transport pieces.

Walls use the relief-sheet method, not stacked boxes. Open n/s sockets match the normal room door datum.
All geometry is original, palette-role bound and built through the shared validated Python pipeline.
"""
import math
from . import cykit as C
from . import meshkit as K
from . import schema as S
from .asset import Node, register
from .gen_cyberkit_tower import slot_rect

V = '1.0.0'
SLOT = S.enum('a', list(C.SLOTS))


def done(m, cards=None, meta=None, ground=True):
    return C.finish([Node('body', m, 'solid'), Node('details', cards or K.Mesh(), 'card')],
                    meta or C.grid_meta('free'), ground=ground)


def shell(P, seed, kind):
    sx, sy = P['cells_x'], P['cells_y']
    w, d = sx * C.CELL, sy * C.CELL
    h = 4.5
    # A bituminous service deck, not the luminous interior slab pattern. The existing dark blotch role
    # supplies broad painted scuffs while keeping roof/garden/city as distinct physical value masses.
    floor_role = 'dirt' if kind == 'rooftop' else 'floor'
    night = P.get('finish', 'day') == 'night'
    dm = float(P.get('door_m', 6.0))          # door centre from the plot-side shell edge (cell 1 by default)
    if night:
        floor_role = NIGHT_FLOOR.get(kind, 'trim')
    if P.get('deck', 'service') == 'calm':
        floor_role = CALM_FLOOR                # plain dark deck: floor telegraphs (lines, rings, fans) read against it
    st = 4 if night else 2                     # night arenas: coarser floor grid keeps big rooms inside budget
    body = C.grid_floor(C.stations(-w/2, w/2, st), C.stations(-d/2, d/2, st), lambda x, y: True, role=floor_role)
    walls, trim, cards, ceiling = K.Mesh(), K.Mesh(), K.Mesh(), K.Mesh()
    socks = []
    rooftop = kind == 'rooftop'
    wall_body = NIGHT_WALL.get(kind, 'wall_alt') if night else ('stone' if kind in ('subway', 'lobby') else 'wall_alt')
    for side, length, px, py, yaw in (('n', w, -w/2, d/2-0.5, 0),
                                     ('s', w, w/2, -d/2+0.5, 180),
                                     ('e', d-1, w/2-0.5, d/2-0.5, -90),
                                     ('w', d-1, -w/2+0.5, -d/2+0.5, 90)):
        cap_trim = (0.0, 0.0) if side in ('n', 's') else (0.185, 0.185)
        if rooftop:
            centre=dm if side=='n' else length-dm
            cuts = [(centre-1.4, centre+1.4, 1.1)] if side in ('n', 's') else []
            wall = C.wall_sheet(length, prof=C.profile('stone', height=1.1), height=1.1, extra_z=(), cap_trim=cap_trim,
                                openings=cuts)
            if cuts:
                socks.append(C.sock('door',(-w/2+dm,d/2-0.5 if side=='n' else -d/2+0.5,0),side,width_m=2.0))
        else:
            # Door centre follows cell 1 (6 m from plot boundary) unless door_m says otherwise (centred arena shells).
            centre = dm if side == 'n' else length-dm
            cuts = [(centre-1.4, centre+1.4, 3.4)] if side in ('n', 's') else []
            wall = C.wall_sheet(length, prof=C.profile(wall_body),
                                openings=cuts, height=h, cap_trim=cap_trim)
            if cuts:
                x = -w/2+dm
                socks.append(C.sock('door', (x, d/2-0.5 if side == 'n' else -d/2+0.5, 0), side,
                                    width_m=2.0, height_m=3.0))
                # The closed interior owns its dark cutaway backing. The reusable transition frame stays open
                # so an outdoor street/roof connection is not an arbitrary opaque rectangle in open air.
                tunnel=C.face_card(centre,0.1,0,2.1,3.08,'opening')
                cards.merge(C.place(tunnel,px,py,yaw_deg=yaw))
        walls.merge(C.place(wall, px, py, yaw_deg=yaw))
    if night:
        nodes, lamps = night_finish(P, kind, w, d, h, body, walls, trim, cards)
        return C.finish(nodes, C.grid_meta('cell_block_centre', [sx, sy], socks, room_kind=kind, bake_lights=lamps),
                        cx=False, cy=False, ground=False)
    if not rooftop:
        ceiling = C.grid_floor([-w/2, 0, w/2], [-d/2, 0, d/2], lambda x, y: True, z=h, role='ceiling', flip=True)
        # Long recessed light coves frame the room rather than filling it with neon.
        for x in (-w/2+0.7, w/2-0.7):
            cards.merge(C.strip((x, -d/2+0.8, h-0.45), (x, d/2-0.8, h-0.45), 0.10, 'light',
                                 (0,0,-1), slot_rect(P['accent'])))
    if kind == 'club':
        trim.merge(C.cham_prism(0, 1.5, -0.04, 0.08, 5.8, 4.2, 0.6, 'trim', top='ice'))
        for x in (-2.8, 2.8):
            cards.merge(C.strip((x,-0.3,0.09),(x,3.3,0.09),0.07,'light',(0,0,1),slot_rect(P['accent'])))
    elif kind == 'subway':
        # Dark rail trough and two slim rails beside the walking platform, no floating full train shell.
        body.merge(C.flat_card(w/2-1.8,0,0.006,2.0,d-1,'metal'))
        for x in (w/2-2.4,w/2-1.2):
            trim.merge(C.slab(x,0,0.01,0.10,d-1,0.10,'rail',c=0.02))
    elif kind == 'lobby':
        for x in (-w/2+1.2,w/2-1.2):
            trim.merge(C.frustum(x,0,0,4.45,0.5,0.32,8,'trim'))
    elif kind == 'den':
        trim.merge(C.slab(-w/2+0.7,0,0,0.45,d-1.5,0.35,'body_alt'))
    elif rooftop:
        trim.merge(C.taper(-w/2+2.3,d/2-2.2,0,3.8,3.4,3.2,3.1,2.9,0.35,0.3,'wall',top='roof'))
    nodes = [Node('floor',body,'shell'),Node('walls',walls,'shell'),Node('ceiling',ceiling,'shell'),Node('trim',trim,'solid'),Node('lights',cards,'card')]
    lamps=[C.light((0,0,8),18.0,0.8)] if rooftop else [C.light((0,d/2-1.2,3.2),6.0,1.2),C.light((0,-d/2+1.2,3.2),6.0,1.2),
                              C.light((w/2-1.2,0,3.2),6.0,1.2),C.light((-w/2+1.2,0,3.2),6.0,1.2)]
    return C.finish(nodes,C.grid_meta('cell_block_centre',[sx,sy],socks,room_kind=kind,bake_lights=lamps),cx=False,cy=False,ground=False)


# ---- Night finish (CYBERPOLISH). Opt-in through presets; the default 'day' builds are byte-identical to before.
# Dark floors keep characters readable (the cast is lit warm/pale against navy), each interior gets its own ceiling.
NIGHT_FLOOR = {'club': 'body_alt', 'subway': 'step', 'server': 'trim', 'rooftop': 'dirt', 'lobby': 'step'}
# Calm deck (ROOF lane, opt-in 'deck': 'calm'): the same painted ground role (the style gate reads it as ground and
# wants its large-scale variation) under a dimmer overhead bake light, so the deck's luma spread drops and amber floor
# telegraphs keep a measured contrast against it (tools.telegraph_contrast). A flatter non-ground role ('cap') was
# tried and failed the exterior ground gates (no ground in view, 49% flat frame).
CALM_FLOOR = 'dirt'
CALM_DECK_LIGHT = 0.3
NIGHT_WALL = {'club': 'wall_alt', 'subway': 'stone', 'server': 'body_alt', 'lobby': 'stone'}


def night_finish(P, kind, w, d, h, body, walls, trim, cards):
    a = slot_rect(P['accent'])
    up, down = (0, 0, 1), (0, 0, -1)
    ceiling, rig = K.Mesh(), K.Mesh()
    cx, cy = C.stations(-w/2, w/2, 4), C.stations(-d/2, d/2, 4)     # 4 m ceiling grid so lamp pools reach it
    wx = w/2-0.95                                # proud of the inner wall relief and plinth
    if kind == 'rooftop':
        # Tower top: lit parapet coping all round, no ceiling.
        for (x0, y0), (x1, y1) in (((-w/2+0.6, d/2-0.6), (w/2-0.6, d/2-0.6)), ((-w/2+0.6, -d/2+0.6), (w/2-0.6, -d/2+0.6)),
                                   ((w/2-0.6, -d/2+0.6), (w/2-0.6, d/2-0.6)), ((-w/2+0.6, -d/2+0.6), (-w/2+0.6, d/2-0.6))):
            cards.merge(C.strip((x0, y0, 1.12), (x1, y1, 1.12), 0.08, 'light', up, a))
        trim.merge(C.taper(-w/2+2.3, d/2-2.2, 0, 3.8, 3.4, 3.2, 3.1, 2.9, 0.35, 0.3, 'wall', top='roof'))
        nodes = [Node('floor', body, 'shell'), Node('walls', walls, 'shell'), Node('trim', trim, 'solid'), Node('lights', cards, 'card')]
        calm = P.get('deck', 'service') == 'calm'
        return nodes, [C.light((0, 0, 8), 18.0 + 2*w/4, CALM_DECK_LIGHT if calm else 0.6)]
    if kind == 'club':
        # Dark ceiling with two nested neon frames over the floor, wall neon ribs alternating cyan / magenta,
        # a violet skirting glow and a raised dance floor inlaid with a neon grid.
        ceiling = C.grid_floor(cx, cy, lambda x, y: True, z=h, role='trim', flip=True)
        for (rw, rd), slot in (((w-6.0, d-6.0), 'b'), ((w-10.0, d-10.0), 'c')):
            q = slot_rect(slot)
            pts = [(-rw/2, -rd/2), (rw/2, -rd/2), (rw/2, rd/2), (-rw/2, rd/2)]
            for i in range(4):
                (x0, y0), (x1, y1) = pts[i], pts[(i+1) % 4]
                cards.merge(C.strip((x0, y0, h-0.06), (x1, y1, h-0.06), 0.24, 'light', down, q))
        n = max(2, int(d // 4))
        for side in (-1, 1):
            for i in range(n):
                y = -d/2 + (i+0.5) * d/n
                q = slot_rect('abc'[(i + (side > 0)) % 3])
                cards.merge(C.strip((side*wx, y, 0.45), (side*wx, y, 3.7), 0.2, 'light', (-side, 0, 0), q))
            cards.merge(C.strip((side*wx, -d/2+1.0, 0.22), (side*wx, d/2-1.0, 0.22), 0.16, 'light', (-side, 0, 0), slot_rect('c')))
        fw, fd = min(8.0, w-8.0), min(6.0, d-8.0)
        trim.merge(C.cham_prism(0, 0, -0.04, 0.06, fw, fd, 0.6, 'trim', top='frame'))
        for k in range(-2, 3):
            cards.merge(C.strip((k*fw/5, -fd/2+0.4, 0.07), (k*fw/5, fd/2-0.4, 0.07), 0.1, 'light', up, slot_rect('a' if k % 2 else 'b')))
        lamps = [C.light((0, 0, 3.0), w*0.35, 1.5), C.light((-w/2+1.5, 0, 2.5), 6.0, 1.0), C.light((w/2-1.5, 0, 2.5), 6.0, 1.0),
                 C.light((0, d/2-1.5, 3.0), 6.0, 0.9), C.light((0, -d/2+1.5, 3.0), 6.0, 0.9)]
    elif kind == 'subway':
        # Tiled vault read: cross ribs every 4 m below a tiled ceiling, one continuous cool strip light along the
        # platform, amber hazard line on the platform edge, dark rail trough with two rails.
        ceiling = C.grid_floor(cx, cy, lambda x, y: True, z=h, role='stone', flip=True)
        for i in range(1, int(d // 4)):
            y = -d/2 + 4*i
            rig.merge(C.slab(0, y, h-0.5, w-1.2, 0.35, 0.5, 'trim', c=0.06))
        cards.merge(C.strip((-w/2+3.5, -d/2+0.8, h-0.55), (-w/2+3.5, d/2-0.8, h-0.55), 0.22, 'light', down, slot_rect('c')))
        cards.merge(C.strip((w/2-4.6, -d/2+0.8, h-0.55), (w/2-4.6, d/2-0.8, h-0.55), 0.14, 'light', down, a))
        body.merge(C.flat_card(w/2-1.8, 0, 0.006, 2.0, d-1, 'metal'))
        for x in (w/2-2.4, w/2-1.2):
            trim.merge(C.slab(x, 0, 0.01, 0.10, d-1, 0.10, 'rail', c=0.02))
        body.merge(C.flat_card(w/2-3.15, 0, 0.008, 0.45, d-1.2, 'band'))
        cards.merge(C.strip((w/2-2.88, -d/2+0.8, 0.02), (w/2-2.88, d/2-0.8, 0.02), 0.05, 'light', up, slot_rect('c')))
        lamps = [C.light((-w/2+3.5, y, 3.6), 7.0, 0.8) for y in (-d/4, d/4)] + [C.light((w/2-4.0, 0, 3.0), 7.0, 0.75),
                 C.light((0, 0, 3.6), 7.0, 0.6)]
    elif kind == 'server':
        # Lit tile ceiling with three cable trays and cyan strip lights; dark panel floor, amber keep-clear line, amber skirting.
        ceiling = C.grid_floor(cx, cy, lambda x, y: True, z=h, role='ice', flip=True)
        for x in (-w/3, 0.0, w/3):
            rig.merge(C.slab(x, 0, h-0.55, 0.6, d-1.6, 0.12, 'rail', c=0.03))
            cards.merge(C.strip((x+0.45, -d/2+0.9, h-0.5), (x+0.45, d/2-0.9, h-0.5), 0.3, 'light', down, a))
        for side in (-1, 1):
            cards.merge(C.strip((side*wx, -d/2+1.0, 0.3), (side*wx, d/2-1.0, 0.3), 0.26, 'light', (-side, 0, 0), slot_rect('c')))
            cards.merge(C.strip((side*wx, -d/2+1.0, 3.0), (side*wx, d/2-1.0, 3.0), 0.22, 'light', (-side, 0, 0), a))
        # amber keep-clear line in front of the terminal wall (a warm accent on a cold floor)
        body.merge(C.flat_card(0, d/2-2.6, 0.008, w-6.0, 0.6, 'band'))
        for x in (-2.6, 2.6):          # cyan floor guide lines from the entry to the terminal wall
            cards.merge(C.strip((x, -d/2+2.0, 0.012), (x, d/2-3.0, 0.012), 0.5, 'light', up, a))
        lamps = [C.light((x, y, 3.0), 6.5, 1.1) for x in (-w/3, w/3) for y in (-d/4, d/4)] + [C.light((0, d/2-1.5, 3.0), 7.0, 1.0),
                 C.light((0, 0, 3.0), 6.0, 1.2)]
    else:
        ceiling = C.grid_floor(cx, cy, lambda x, y: True, z=h, role='ceiling', flip=True)
        for x in (-w/2+0.7, w/2-0.7):
            cards.merge(C.strip((x, -d/2+0.8, h-0.45), (x, d/2-0.8, h-0.45), 0.10, 'light', down, a))
        lamps = [C.light((0, 0, 3.4), w*0.4, 0.6)]
    nodes = [Node('floor', body, 'shell'), Node('walls', walls, 'shell'), Node('ceiling', ceiling, 'shell'),
             Node('trim', trim, 'solid'), Node('rig', rig, 'shell'), Node('lights', cards, 'card')]
    return nodes, lamps


def register_shell(kind, description):
    @register('cyroom.'+kind,V,'shell',{'cells_x':S.integer(3,3,5),'cells_y':S.integer(3,3,5),'accent':SLOT,
              'finish':S.enum('day',['day','night'],'night: dark floor, per-kind ceiling and neon (arena presets)'),
              'door_m':S.num(6.0,6.0,10.0,'door centre from the shell edge in metres'),
              'deck':S.enum('service',['service','calm'],'calm: plain dark floor and dimmer deck light so floor telegraphs read (arena presets)')},description,
              origin='room_floor')
    def build(P,seed):
        return shell(P,seed,kind)
    return build


club = register_shell('club','Low club shell: recessed coves, raised chamfered dance floor, open door sockets.')
apartment = register_shell('apartment','Apartment shell: painted panel walls, shadow skirting and recessed coves.')
den = register_shell('den','Hacker den shell with a service plinth, painted panel walls and light coves.')
subway = register_shell('subway','Subway shell with tiled walls, rail trough, two rails and safe walking platform.')
lobby = register_shell('lobby','Corporate lobby shell with tapered octagonal columns and tiled relief walls.')
rooftop = register_shell('rooftop','Rooftop deck with low relief parapets and a tapered stairhead, open to the skyline.')
server = register_shell('server','Server hall shell: dark panel walls; night finish adds a panel floor, lit tile ceiling, cable trays and cyan strip lights.')


@register('cyroom.chair',V,'furniture',{'kind':S.enum('office',['office','captive']),'accent':SLOT},
          'Seat for scenes: a swivel office chair, or a heavy bolted captive chair with high back, arm cuffs and a lit '
          'status band (a scene prop, no gore).',origin='floor_center')
def chair(P,seed):
    q=K.Mesh()
    if P['kind']=='captive':
        m=C.taper(0,0,0,0.1,0.9,0.9,0.8,0.8,0.08,0.06,'metal')                    # bolted floor plate
        m.merge(C.taper(0,0,0.1,0.42,0.34,0.34,0.26,0.26,0.05,0.04,'body'))       # pedestal
        m.merge(C.slab(0,-0.02,0.42,0.62,0.6,0.1,'leather',c=0.08))              # seat pad
        m.merge(C.taper(0,0.30,0.42,1.55,0.62,0.14,0.52,0.12,0.05,0.04,'body_alt'))   # high back
        for sx in (-1,1):
            m.merge(C.slab(sx*0.36,-0.02,0.52,0.1,0.56,0.12,'body',c=0.03))      # arms
            q.merge(C.flat_card(sx*0.36,-0.16,0.645,0.12,0.14,'band'))             # cuff bands
        q.merge(C.strip((-0.24,0.225,0.75),(0.24,0.225,0.75),0.05,'light',(0,-1,0),slot_rect(P['accent'])))
    else:
        m=C.cyl(0,0,0,0.3,0.05,6,'body')
        m.merge(C.cyl(0,0,0.05,0.04,0.38,6,'chrome'))
        m.merge(C.slab(0,0,0.43,0.5,0.48,0.09,'leather',c=0.06))
        m.merge(C.taper(0,0.24,0.5,1.0,0.46,0.08,0.4,0.07,0.04,0.03,'leather'))
        q.merge(C.strip((-0.18,0.195,0.92),(0.18,0.195,0.92),0.03,'light',(0,-1,0),slot_rect(P['accent'])))
    return done(m,q)


@register('cyroom.bar',V,'furniture_large',{'accent':SLOT},'Chamfered long club bar, overhanging top and inset lit lip.',origin='floor_center')
def bar(P,seed):
    m=C.taper(0,0,0,1.12,4.4,1.1,4.0,0.9,0.3,0.2,'body_alt',top='wood')
    m.merge(C.slab(0,-0.1,1.10,4.7,1.25,0.14,'trim',c=0.22))
    q=C.strip((-1.9,-0.58,0.85),(1.9,-0.58,0.85),0.09,'light',(0,-1,0),slot_rect(P['accent']))
    return done(m,q)


@register('cyroom.booth',V,'furniture',{'accent':SLOT},'Curved segmented padded club booth around a small pedestal table.',origin='floor_center')
def booth(P,seed):
    rings=[]
    section=[(0.95,0.0),(1.6,0.0),(1.6,0.95),(1.43,1.08),(1.30,0.5),(0.95,0.5)]
    for k in range(9):
        a=math.radians(20+17.5*k)
        rings.append([(rad*math.cos(a),rad*math.sin(a),z) for rad,z in section])
    m=K.loft(rings,'leather',smooth=True)
    m.merge(C.cyl(0,0,0,0.12,0.7,6,'post'))
    m.merge(C.cyl(0,0,0.7,0.65,0.10,8,'wood'))
    return done(m)


@register('cyroom.sofa',V,'furniture',{'width':S.num(2.2,1.4,3.0)},'Tapered upholstered sofa with rounded chamfered arms and padded back.',origin='floor_center')
def sofa(P,seed):
    w=P['width']
    m=C.taper(0,0,0,0.46,w,0.9,w-0.12,0.85,0.16,0.14,'leather')
    m.merge(C.slab(0,0,0.42,w-0.32,0.7,0.15,'cushion',c=0.15))
    m.merge(C.taper(0,0.36,0.38,1.03,w,0.23,w-0.1,0.16,0.06,0.05,'leather'))
    for sx in (-1,1):
        m.merge(C.slab(sx*(w/2-0.1),0,0.4,0.22,0.9,0.34,'leather',c=0.06))
    return done(m)


@register('cyroom.desk',V,'furniture',{'screens':S.integer(2,1,3),'accent':SLOT},'Workstation with chamfered desktop, tapered supports and original monitor glyph displays.',origin='floor_center')
def desk(P,seed):
    m=C.slab(0,0,0.74,2.2,0.95,0.12,'body',c=0.12)
    for x in (-0.8,0.8):
        m.merge(C.taper(x,0,0,0.76,0.32,0.65,0.23,0.5,0.06,0.05,'body_alt'))
    q=K.Mesh()
    for k in range(P['screens']):
        x=(k-(P['screens']-1)/2)*0.62
        m.merge(C.slab(x,0.20,0.9,0.59,0.16,0.53,'frame',c=0.035))
        q.merge(C.face_card(x,0.11,0.95,0.51,0.43,'book',C.cell_uv('book','monitor'),lift=0.015))
    return done(m,q)


@register('cyroom.bed',V,'furniture',{},'Low apartment bed with bevelled frame, painted quilt and pillow.',origin='floor_center')
def bed(P,seed):
    m=C.slab(0,0,0,1.5,2.2,0.3,'body_alt',c=0.18)
    m.merge(C.slab(0,-0.05,0.3,1.4,2.0,0.18,'quilt',c=0.16))
    m.merge(C.slab(0,0.72,0.48,0.95,0.43,0.16,'cushion',c=0.15))
    m.merge(C.taper(0,1.03,0,0.9,1.5,0.2,1.4,0.14,0.06,0.04,'body'))
    return done(m)


@register('cyroom.locker',V,'furniture',{'doors':S.integer(3,1,4)},'Chamfered station lockers with inset shutter doors and handles.',origin='floor_center')
def locker(P,seed):
    n=P['doors'];m=C.slab(0,0,0,n*0.55,0.55,1.9,'body',c=0.08)
    for i in range(n):
        x=(i-(n-1)/2)*0.55
        m.merge(C.slab(x,-0.285,0.13,0.47,0.035,1.62,'door',c=0.015))
        m.merge(C.rod((x+0.13,-0.32,0.9),(x+0.13,-0.32,1.1),0.018,4,'metal'))
    return done(m)


@register('cyroom.platform',V,'shell',{'cells':S.integer(3,1,4),'accent':SLOT},'Station platform tile: raised bevelled edge with tactile hazard line and lit coping.',origin='room_floor')
def platform(P,seed):
    l=P['cells']*4
    m=C.slab(0,0,-0.25,4,l,0.25,'stone',c=0.06,top='sand')
    q=C.flat_card(1.55,0,0.012,0.32,l-0.1,'band')
    q.merge(C.strip((1.98,-l/2+0.1,-0.08),(1.98,l/2-0.1,-0.08),0.06,'light',(1,0,0),slot_rect(P['accent'])))
    return C.finish([Node('platform',m,'solid'),Node('coping',q,'card')],C.grid_meta('cell_block_centre',[1,P['cells']]),ground=False)


@register('cyroom.train',V,'vehicle',{'accent':SLOT,'form':S.enum('stub',['stub','carriage'],'carriage: long car with lit window band')},
          'Static chamfered transit carriage with sloped nose and painted windows, no real logos.',origin='floor_center')
def train(P,seed):
    if P.get('form')=='carriage':
        return carriage(P)
    rings=[]
    for y,w,z0,z1 in ((-4.5,1.05,0.25,2.2),(-3.2,1.35,0.2,3.1),(3.5,1.35,0.2,3.1),(4.2,1.1,0.3,2.8)):
        rings.append([(-w,y,z0),(w,y,z0),(w,y,z1-0.4),(w-0.35,y,z1),(-w+0.35,y,z1),(-w,y,z1-0.4)])
    m=K.loft(rings,'hull',smooth=False)
    q=K.Mesh()
    for side in (-1,1):
        for y in (-2,0,2):
            q.merge(C.face_card(side*1.365,y,1.5,1.5,0.95,'glass',facing='+x' if side>0 else '-x'))
    return done(m,q)


WIN_UV = (0.01, 0.76, 0.5, 0.99)     # one lit row of the shared window-light (fire) atlas, about four windows


def carriage(P):
    """A 14 m car standing in the trough: dark skirt and bogies, chamfered body, lit window band (warm interior light
    seen through glass), two door leaves per side, a livery neon line and a lit nose with headlamps. Long axis = y."""
    L=14.0;hw=1.25
    rings=[]
    for y,w,z0,z1 in ((-L/2,0.95,0.55,2.6),(-L/2+0.9,hw,0.45,3.35),(L/2-0.9,hw,0.45,3.35),(L/2,0.95,0.55,2.6)):
        rings.append([(-w,y,z0),(w,y,z0),(w,y,z1-0.55),(w-0.4,y,z1),(-w+0.4,y,z1),(-w,y,z1-0.55)])
    m=K.loft(rings,'hull',smooth=False)
    m.merge(C.slab(0,0,0.0,2.1,L-1.6,0.5,'metal',c=0.1))                          # skirt / bogies
    for y in (-L/2+2.4,L/2-2.4):
        m.merge(C.slab(0,y,0.0,2.3,1.8,0.42,'body',c=0.12))
    q=K.Mesh();acc=slot_rect(P['accent'])
    for side in (-1,1):
        f='+x' if side>0 else '-x';x=side*(hw+0.02)
        for y in (-4.9,-2.5,2.5,4.9):                                              # lit window band
            q.merge(C.face_card(x,y,1.55,2.0,0.85,'fire',WIN_UV,facing=f))
        for y in (-0.75,0.75):
            q.merge(C.face_card(x,y,0.6,1.3,2.1,'door',facing=f))
        q.merge(C.strip((x,-L/2+1.0,1.25),(x,L/2-1.0,1.25),0.22,'light',(side,0,0),acc))      # livery line
        q.merge(C.strip((x*0.86,-L/2+1.2,3.12),(x*0.86,L/2-1.2,3.12),0.12,'light',(side,0,0),slot_rect('b')))
    for y,f in ((-L/2-0.01,'-y'),(L/2+0.01,'+y')):
        q.merge(C.face_card(0,y,1.6,1.3,0.6,'glass',facing=f))
        for x in (-0.6,0.6):
            q.merge(C.face_card(x,y,0.9,0.28,0.16,'light',slot_rect('c'),facing=f))
    return done(m,q)


@register('cyroom.canopy',V,'structure',{'cells':S.integer(2,1,3),'accent':SLOT},'Station canopy on raked tapered columns, folded roof and recessed light strip.',origin='floor_center')
def canopy(P,seed):
    l=P['cells']*4;m=K.Mesh()
    for y in (-l/2+0.5,l/2-0.5):
        m.merge(C.taper(0,y,0,3.8,0.5,0.5,0.3,0.3,0.08,0.05,'trim'))
    roof=C.wedge(0,0,3.7,4.2,l,0.3,0.16,'roof',c=0.1)
    roof.r[0]='ceiling'  # the downward-facing canopy soffit is a lit painted ceiling, not black roof membrane
    m.merge(roof)
    q=C.strip((0,-l/2+0.2,3.68),(0,l/2-0.2,3.68),0.15,'light',(0,0,-1),slot_rect(P['accent']))
    return done(m,q)


@register('cyroom.turnstile',V,'furniture',{'accent':SLOT},'Transit turnstile with tapered reader pedestal and three-bar hub.',origin='floor_center')
def turnstile(P,seed):
    m=C.taper(0,0,0,1.05,0.4,1.0,0.35,0.9,0.09,0.08,'body')
    for k in range(3):
        a=k*K.TAU/3
        m.merge(C.rod((0.18,0,0.7),(0.75,0.42*math.sin(a),0.7+0.42*math.cos(a)),0.035,4,'chrome'))
    q=C.flat_card(0,0,1.06,0.22,0.3,'book',C.cell_uv('book','monitor'))
    return done(m,q)


@register('cyroom.portal',V,'arch',{'accent':SLOT},'Chamfered transit doorway frame: tapered jambs, bevelled lintel, narrow inset light strips.',origin='opening')
def portal(P,seed):
    m=K.Mesh();q=K.Mesh()
    for x in (-1.2,1.2):
        m.merge(C.taper(x,-0.3,0,3.25,0.4,0.7,0.34,0.65,0.06,0.05,'frame'))
        q.merge(C.strip((x,-0.66,0.25),(x,-0.66,2.95),0.06,'light',(0,-1,0),slot_rect(P['accent'])))
    m.merge(C.slab(0,-0.3,3.05,2.8,0.7,0.35,'trim',c=0.08))
    return C.finish([Node('frame',m,'solid'),Node('light',q,'card')],
                    C.grid_meta('door_anchor',None,[C.sock('door',(0,0,0),'s',width_m=2.0)]),cx=False,cy=False)
