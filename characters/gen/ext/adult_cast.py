"""Cast recipes of the n64_adult family (lane CHARS3). Originals: identity by silhouette, outfit, prop and a fictional
mark; no real person's likeness and no real company name or logo. The emblem default is a plain four-point star of
our own drawing, flagged placeholder_until_permission (docs/CHARS3-RESULT.md)."""

TEKNIUM = {
    'id': 'teknium', 'preset': 'n64_adult', 'band': 'hero', 'torso': 'bomber', 'hair': 'spikes', 'emblem': 'back',
    'emblem_kind': 'star4', 'pouches': 'right', 'legs': 'cargo', 'gloves': 'fingerless', 'chevron': True, 'tail': True,
    'sleeve': 'puff34', 'shoulder': .114, 'chest': .134, 'stance': 1.22, 'boot_r': 1.16, 'fist_w': 1.22, 'hand': .124, 'boot_h': .174,
    'colors': {'skin': '#e2ae86', 'hair': '#3cb45a', 'hair_tip': '#3a8fd8', 'brow': '#1c4034', 'eye': '#2f7fd0',
               'jacket': '#27754a', 'panel': '#e6ecdc', 'trim': '#173528', 'trouser': '#41466a', 'boot': '#454258',
               'sole': '#a6a6b8', 'glove': '#2a2630', 'belt': '#2b2a38', 'buckle': '#e0c765', 'pouch': '#9a6a3c',
               'emblem': '#ffffff'},
    'face': {'brow': 'stern', 'fringe': 'spiky', 'mouth': 'flat', 'eye_w': 14, 'eye_h': 10, 'eye_gap': 5},
    'props': ['visor'],
}

# the rig's reference body: hero-band defaults, plain training suit, no props (rigs/human16_v3/mannequin.glb)
MANNEQUIN = {
    'id': 'mannequin', 'preset': 'n64_adult', 'band': 'hero', 'height': 1.74, 'torso': 'shirt', 'hair': 'short', 'emblem': 'none',
    'pouches': False, 'legs': 'cargo', 'gloves': 'none', 'chevron': False, 'hand': .084,
    'colors': {'skin': '#d8b090', 'hair': '#5a5a66', 'brow': '#3a3a44', 'eye': '#3a4a5c', 'jacket': '#8a93a8', 'panel': '#c4cad6',
               'trim': '#5c6478', 'trouser': '#646c84', 'boot': '#4a4e60', 'sole': '#9a9aa8', 'glove': '#d8b090', 'belt': '#5c6478',
               'buckle': '#c4cad6', 'pouch': '#5c6478', 'emblem': '#f4f0dc'},
    'face': {'brow': 'flat', 'eye': 'calm', 'mouth': 'flat'}, 'props': [],
}

CAST = {'teknium': TEKNIUM, 'mannequin': MANNEQUIN}


def recipe(cid):
    import copy
    return copy.deepcopy(CAST[cid])
