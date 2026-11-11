"""Base locomotion format: every two-legged character gets a planted-foot run and walk (docs/LOCOMOTION.md).

    from adventure_maker import locomotion
    out, report = locomotion.bake(glb_bytes)          # refuses with locomotion.LocomotionError in plain words
    report = locomotion.check(glb_bytes)              # the same metrics on the clips a file already has

base_v1.json next to this file is the format: the bones, the body measurements, the two cycles, the limits, the fit
dials, the speed blend and the output block.
"""
from .core import (BLOCK, CLIPS, FORMAT, LocomotionError, bake, check, cycle, load_spec, read_body,  # noqa: F401
                   attach, block_of, rig_contract, waive_flight)
