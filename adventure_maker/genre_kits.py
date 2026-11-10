"""Explicitly integrated genre-kit metadata. Not an auto-discovery/approval of unfinished packs.

MERGE6 exposes these exact pack ids to new games by owner instruction. Cast/rig art is reused unchanged.
Numerical/art caveats live in each lane's KIT-RESULT; hub tiers remain data/build checked, not owner-approved.
"""
GENRES = {
    'scifikit': {
        'packs': {
            'space_station': ('Space Station', ['sci-fi', 'space', 'station', 'clean', 'stars'],
                              'docs/scifikit/thumb-bridge.png', (0, 0, 320, 240), 'Tessera Relay bridge', 'tech.crate'),
            'alien_world': ('Alien World', ['sci-fi', 'alien', 'planet', 'crystal', 'flora'],
                            'docs/scifikit/thumb-landing.png', (0, 0, 320, 240), 'Corva Landing', 'alien.crystal'),
        },
        'families': (
            ('station_architecture', ('stn.',), 'Station Architecture', 'corridors, airlocks, decks, bridge and hangar shells'),
            ('tech_props', ('tech.',), 'Tech Props', 'consoles, holo-tables, cryo pods, crates, tanks, vents and terminals'),
            ('ships', ('ship.',), 'Ships & Vehicles', 'shuttles, haulers, rovers, escape pods and drones'),
            ('alien_nature', ('alien.',), 'Alien Flora, Rock & Crystal', 'crystals, cap trees, fronds, geodes and rock spires'),
            ('planet_terrain', ('planet.',), 'Planet Terrain', 'interlocking surface tiles, craters, dunes, ridges and mesas'),
            ('space_sky', ('skyx.',), 'Space Sky', 'star domes, planets, nebulae and horizon rings'),
        ),
        'cast': ('new_arrival', 'tavi'),
    },
    'ancientkit': {
        'packs': {
            'ancient_ruins': ('Ancient Ruins', ['ancient', 'ruins', 'desert', 'temple'],
                              'docs/ancientkit/best6.png', (8, 40, 320, 240), 'The Sun Road (ancient_ruins)', 'relic.tablet'),
            'jungle_temple': ('Jungle Temple', ['jungle', 'temple', 'ruins', 'overgrown'],
                              'docs/ancientkit/best6.png', (336, 302, 320, 240), 'The Sun Road (jungle_temple)', 'relic.tablet'),
        },
        'families': (
            ('ruin', ('ruin.',), 'Ruin Architecture', 'carved walls, columns, pyramids, stairs, gates, arches and courts'),
            ('relic', ('relic.',), 'Carving Props', 'statues, altars, braziers, urns, tablets, pressure plates and dials'),
            ('wild', ('wild.',), 'Desert & Jungle Nature', 'palms, jungle trees, ferns, vines, dunes, rocks and oasis pools'),
            ('land', ('land.',), 'Desert & Jungle Terrain & Sky', 'ground tiles, cliffs, slopes, causeways, terraces and skies'),
        ),
        'cast': ('fv_scribe', 'fv_warden'),
    },
    'medievalkit': {
        'packs': {pid: (name, words, 'docs/medievalkit/thumb-' + pid + '.png', (0, 0, 320, 240),
                        "The Wayfarer's Audience square (" + pid + ')', 'mprop.crate')
                  for pid, name, words in (
                      ('medieval_village', 'Medieval Village', ['medieval', 'village', 'timber', 'thatch', 'day']),
                      ('medieval_village_dusk', 'Medieval Village (dusk)', ['medieval', 'village', 'dusk', 'lantern', 'sunset']),
                      ('medieval_village_night', 'Medieval Village (night)', ['medieval', 'village', 'night', 'moonlight']),
                      ('medieval_village_snow', 'Medieval Village (snow)', ['medieval', 'village', 'snow', 'winter']),
                      ('castle_keep', 'Castle Keep', ['medieval', 'castle', 'stone', 'keep', 'throne', 'torch']))},
        'families': (
            ('medieval_village_architecture', ('vlg.',), 'Village Architecture', 'cottages, taverns, mills, chapels and village interiors'),
            ('medieval_castle', ('cst.',), 'Castle', 'towers, gatehouses, portcullises, halls, cells and throne sets'),
            ('medieval_props', ('mprop.',), 'Medieval Props', 'storage, carts, furniture, weapons, tableware and lanterns'),
            ('medieval_nature', ('mnat.',), 'Medieval Nature', 'trees, orchards, hedges, farm crops, rocks, flowers and logs'),
            ('medieval_terrain', ('mter.',), 'Medieval Terrain', 'ground and paths, hills, banks, water and distant backdrops'),
        ),
        'cast': ('fv_scribe', 'fv_warden'),
    },
    'westernkit': {
        'packs': {
            'frontier_town': ('Frontier Town', ['western', 'frontier', 'desert', 'town', 'noon', 'wood'],
                              'docs/westernkit/thumb-main_street.png', (0, 0, 320, 240), 'Redwater (frontier_town)', 'wprop.crate'),
            'frontier_town_golden': ('Frontier Town (golden hour)', ['western', 'frontier', 'golden-hour', 'warm', 'sunset'],
                                     'docs/westernkit/thumb-main_street-golden.png', (0, 0, 320, 240), 'Redwater (golden hour)', 'wprop.crate'),
            'frontier_town_night': ('Frontier Town (night)', ['western', 'frontier', 'night', 'lantern', 'stars'],
                                    'docs/westernkit/thumb-main_street-night.png', (0, 0, 320, 240), 'Redwater (night)', 'wprop.crate'),
            'canyon_mesa': ('Canyon Mesa', ['western', 'canyon', 'mesa', 'red-rock', 'desert', 'scrub'],
                            'docs/westernkit/thumb-canyon_pass.png', (0, 0, 320, 240), 'Redwater canyon (canyon_mesa)', 'wprop.crate'),
        },
        'families': (
            ('frontier_town', ('wtown.',), 'Town Architecture', 'false-front buildings, boardwalks, porches, balconies and interiors'),
            ('frontier_rail', ('wrail.',), 'Frontier Rail', 'track, platforms, stations, bridges, railcars and locomotives'),
            ('frontier_mine', ('wmine.',), 'Frontier Mine', 'timbered tunnels, mine track, portals, ore carts and mine machinery'),
            ('frontier_props', ('wprop.',), 'Frontier Props', 'barrels, crates, wagons, saloon furniture, signs, lanterns and campfires'),
            ('canyon_terrain', ('wland.', 'wsky.'), 'Canyon Terrain & Sky', 'canyon walls, mesas, arches, ground, desert plants, oasis and skies'),
        ),
        'cast': ('fv_scribe', 'fv_warden'),
        'item_prefixes': ('wprop.',),
    },
    # L5 CYBER-ROOMS: merged from cyberkit-lane 03be2ccb. ART REVIEW OPEN (plan 03 gate G3): numeric style/N64
    # checks pass (round 41); no owner art approval is claimed. Thumbnails are real-runtime round-41 frames.
    'cyberkit': {
        'packs': {
            'neon_city_night': ('Neon City Night', ['cyber', 'cyberpunk', 'neon', 'city', 'night', 'rain'],
                                'docs/cyberkit/best-6.png', (8, 40, 320, 240),
                                'Night Relay street (neon_city_night, round 41; art review open)', 'cydress.crates'),
            'cyber_blue_grid': ('Cyber Blue Grid', ['cyber', 'cyberpunk', 'grid', 'network', 'hologram', 'blue'],
                                'docs/cyberkit/best-6.png', (336, 40, 320, 240),
                                'Night Relay roof (cyber_blue_grid, round 41; art review open)', 'cydress.crates'),
            'neon_dawn': ('Neon Dawn', ['cyber', 'cyberpunk', 'neon', 'dawn', 'skyline'],
                          'docs/cyberkit/best-6.png', (336, 322, 320, 240),
                          'Night Relay street (neon_dawn, round 41; art review open)', 'cydress.crates'),
        },
        'families': (
            ('cyber_towers', ('cytower.',), 'Cyber Towers', 'drum, setback, needle, twin and wedge towers, crowns, facades and skybridges'),
            ('cyber_streets', ('cystreet.',), 'Cyber Streets', 'roads, crossings, elevated roads, rail, ramps, alleys and plazas'),
            ('cyber_signs', ('cysign.',), 'Cyber Signs', 'original glyph signs, billboards, banners, holo signs and storefronts'),
            ('cyber_tech', ('cytech.',), 'Cyber Tech', 'terminals, racks, vending, conduits, drones, hover-cars and street lights'),
            ('cyber_rooms', ('cyroom.',), 'Cyber Interiors', 'club, apartment, den, lobby, subway and roof shells with furniture'),
            ('cyber_dressing', ('cydress.',), 'Cyber Street Dressing', 'benches, bins, crates, carts, awnings, shutters and tanks'),
            ('cyber_sky', ('cysky.',), 'Cyber Sky', 'layered skyline cards, aircraft, halo and network cards, megatower'),
        ),
        'cast': ('fv_scribe', 'fv_warden'),
        'item_prefixes': ('cydress.',),
        'art_review': 'open',
        # Opt-in automatic premise matching (newgame.pick_style), appended AFTER the legacy rows so a tie keeps the
        # older pack. Words chosen to miss every legacy keyword set (no robot/android/space/station/night/storm).
        'auto_words': ('neon_city_night', frozenset({
            'cyber', 'cyberpunk', 'neon', 'city', 'cities', 'rain', 'rainy', 'server', 'hacker', 'hacking', 'megacity',
            'skyscraper', 'nightclub', 'club', 'subway', 'metro', 'hologram', 'holographic', 'synthwave', 'megacorp',
            'corporation', 'rooftop', 'downtown', 'alley'})),
    },
}

PACKS = {pid: dict(name=data[0], words=data[1], thumbnail=data[2], crop=data[3], scene=data[4],
                   collectible=data[5], cast=genre['cast'],
                   manifest='kits/library/' + lane + '-manifest.json',
                   sockets='kits/library/' + lane + '-sockets.json')
         for lane, genre in GENRES.items() for pid, data in genre['packs'].items()}
FAMILIES = tuple(family for genre in GENRES.values() for family in genre['families'])
ITEM_PREFIXES = tuple(prefix for genre in GENRES.values() for prefix in genre.get('item_prefixes', ()))
# (pack, words) rows for newgame.KEYWORDS, in GENRES order; only genres that opt in with 'auto_words'.
AUTO_KEYWORDS = tuple(genre['auto_words'] for genre in GENRES.values() if 'auto_words' in genre)
