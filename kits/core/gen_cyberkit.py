"""CYBERKIT: neon-city kit families for the shared Hermes64 core (registered by one import line in pipeline.py).

Families (docs/CYBERKIT.md): cytower. (towers, facades, crowns, gardens), cystreet. (roads, crossings, alleys,
stairs, elevated decks and rails), cysign. (neon frames, blades, billboards, holo cards, shopfronts), cytech. (vending,
terminals, racks, drones, hover cars, conduits, street lights, puddles), cyroom. (interior shells and furniture,
rooftop decks), cydress. (nature-free set dressing), cysky. (skyline cards, holo lines, aircraft, megatower).
The painted field generators (kits/core/texgen_cyber.py) register into texgen.FIELD_GENS here, before any cyber
pack texture is made (every build path loads the generators first).
"""
from . import texgen_cyber  # noqa: F401  (registers the cy_* painters)
from . import gen_cyberkit_tower  # noqa: F401
from . import gen_cyberkit_street  # noqa: F401
from . import gen_cyberkit_sign  # noqa: F401
from . import gen_cyberkit_tech  # noqa: F401
from . import gen_cyberkit_room  # noqa: F401
from . import gen_cyberkit_dress  # noqa: F401
from . import gen_cyberkit_sky  # noqa: F401

FAMILIES = ("cytower.", "cystreet.", "cysign.", "cytech.", "cyroom.", "cydress.", "cysky.")
