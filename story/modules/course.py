"""Necessary distance/speed bound, NOT a steering or human feasibility proof."""
import math
from .registry import index


def minimum_ticks(game, track):
    points = [(track['start_position_m'], 0)] + [(p['position_m'], p['radius_m']) for p in track['checkpoints']]
    distance = sum(max(0.0, math.dist(a, b) - ra - rb) for (a, ra), (b, rb) in zip(points, points[1:]))
    config = index(game)['course']['config']
    # Closed spheres in 3D: triangle inequality gives a necessary lower bound.
    # Subtract tiny rounding tolerance; never round a feasible boundary up accidentally.
    return max(0, math.ceil(distance / config['max_speed_mps'] * config['simulation_hz'] - 1e-9))
