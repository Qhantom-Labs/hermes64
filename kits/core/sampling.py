"""Seeded random parameter sampling from a generator schema (sweeps and gates)."""
from .rng import rng


def sample_value(r, p, palette_names):
    t = p["type"]
    if t == "number":
        return round(r.uniform(p["minimum"], p["maximum"]), 4)
    if t == "integer":
        return r.randint(p["minimum"], p["maximum"])
    if t == "boolean":
        return r.random() < 0.5
    if t == "string":
        if "enum" in p:
            return r.choice(p["enum"])
        if p.get("x-palette-color"):
            return r.choice(sorted(palette_names))
        return p["default"]
    if t == "array":
        n = r.randint(0, p["maxItems"])
        return [{k: sample_value(r, q, palette_names) for k, q in p["items"]["properties"].items()} for _ in range(n)]
    raise ValueError(t)


def sample_params(spec, palette_names, seed, i, fixed=None, tries=40):
    """Returns (params, attempts). Respects spec.rules by resampling; fixed overrides keys."""
    for a in range(tries):
        r = rng("sweep", spec.id, seed, i, a)
        P = {k: sample_value(r, p, palette_names) for k, p in spec.schema["properties"].items()}
        if fixed:
            P.update(fixed)
        if spec.sweep_fixed:
            for k, v in spec.sweep_fixed.items():
                P[k] = v(P, r) if callable(v) else v
        if spec.rules is None or not spec.rules(P):
            return P, a + 1
    raise RuntimeError("could not sample valid params for %s" % spec.id)
