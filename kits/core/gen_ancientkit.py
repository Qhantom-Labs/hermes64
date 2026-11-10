"""ANCIENTKIT entry point: importing this module registers the four ANCIENTKIT kit families and the anc_* texture
fields. kits/core/pipeline.load_generators imports it (the lane's single added line in a shared file).

  ruin.*   ruin architecture   (gen_ancientkit_ruin.py)
  relic.*  carving props       (gen_ancientkit_relic.py)
  wild.*   nature              (gen_ancientkit_wild.py)
  land.*   terrain + sky       (gen_ancientkit_land.py)
"""
from . import gen_ancientkit_tex  # noqa: F401
from . import gen_ancientkit_ruin, gen_ancientkit_relic, gen_ancientkit_wild, gen_ancientkit_land  # noqa: F401

FAMILIES = ("ruin.", "relic.", "wild.", "land.")
