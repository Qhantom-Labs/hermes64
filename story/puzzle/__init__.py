"""STORY 1.3.0: additive puzzle family, compiled by lowering onto the untouched STORY 1.2 machinery.

This package deliberately lives outside ``story/*.py`` and ``story/modules/*.py``: those files are pinned by
the 1.2 module ``implementation_hash`` and the starter style lock, so every existing 1.2 game keeps its
exact bytes. A 1.3 source lowers to a real 1.2 source in which every permanent puzzle fact is a reserved
flag that only the puzzle module sets:

- ``puzzle__s__<puzzle>``  solved
- ``puzzle__t__<key>``     key taken
- ``puzzle__o__<lock>``    lock opened
- ``puzzle__l__<element>`` latch switch/plate latched (persistent puzzles only)

so the existing 1.2 saves, checkpoints and hold-R restore carry puzzle facts unchanged. The compiled 1.3 game
is that compiled 1.2 game plus an additive ``puzzle`` sidecar. Nothing here loads or executes authored code.
"""
VERSION = '1.3.0'
PUZZLE_API = '1.0.0'
PREFIX = 'puzzle__'
KINDS = {'solved': 's', 'taken': 't', 'opened': 'o', 'latched': 'l'}


def is13(value):
    return isinstance(value, dict) and value.get('contract_version') == VERSION


def fact_flag(field, eid):
    return PREFIX + KINDS[field] + '__' + eid


def flag(pid):
    return fact_flag('solved', pid)


def parse_flag(name):
    """('solved'|'taken'|'opened'|'latched', id) for a reserved flag name, else None."""
    if not isinstance(name, str) or not name.startswith(PREFIX) or len(name) < len(PREFIX) + 4 or name[len(PREFIX) + 1:len(PREFIX) + 3] != '__':
        return None
    letter = name[len(PREFIX)]
    for field, value in KINDS.items():
        if value == letter:
            return field, name[len(PREFIX) + 3:]
    return None
