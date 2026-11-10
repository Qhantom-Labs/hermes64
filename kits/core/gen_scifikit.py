"""SCIFIKIT generator families (loaded by kits/core/pipeline.load_generators with one import line).

  stn.     station architecture               kits/core/gen_scifikit_station.py
  tech.    tech props                         kits/core/gen_scifikit_props.py
  ship.    ships / vehicles                   kits/core/gen_scifikit_ships.py
  alien.   alien flora / rock / crystal       kits/core/gen_scifikit_alien.py
  planet.  planet-surface terrain             kits/core/gen_scifikit_terrain.py
  skyx.    star-field / planet sky backdrops  kits/core/gen_scifikit_sky.py
"""
import importlib

FAMILIES = ("station", "props", "ships", "alien", "terrain", "sky")

for _fam in FAMILIES:
    importlib.import_module(".gen_scifikit_" + _fam, __package__)
