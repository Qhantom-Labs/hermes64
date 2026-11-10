"""Typed parameter schemas (JSON-Schema subset) with fail-closed validation.

Schema helpers build `{"type": "object", "properties": {...}, "additionalProperties": False}`.
Supported property types: number, integer, string (enum or x-palette-color), boolean,
array (of objects with their own properties, maxItems). No silent clamping, ever.
"""
import math


class ParamError(ValueError):
    pass


def num(default, lo, hi, desc=""):
    return {"type": "number", "default": default, "minimum": lo, "maximum": hi, "description": desc}


def integer(default, lo, hi, desc=""):
    return {"type": "integer", "default": default, "minimum": lo, "maximum": hi, "description": desc}


def enum(default, values, desc=""):
    assert default in values, (default, values)
    return {"type": "string", "default": default, "enum": list(values), "description": desc}


def boolean(default, desc=""):
    return {"type": "boolean", "default": bool(default), "description": desc}


def lod(spec):
    """Mark a tessellation-only param (x-lod: smoothness/density, not design; the visible-difference
    validator does not require it to change the look)."""
    out = dict(spec)
    out["x-lod"] = True
    return out


def runtime(spec):
    """Mark a param that only acts in the runtime (x-runtime: emitter behaviour, placement scale), so a
    static render cannot show it."""
    out = dict(spec)
    out["x-runtime"] = True
    return out


def color(default, desc=""):
    """A pack palette colour NAME (validated against the active pack at build time)."""
    return {"type": "string", "default": default, "x-palette-color": True, "description": desc}


def array(item_props, default, max_items, desc=""):
    return {"type": "array", "default": default, "maxItems": max_items, "description": desc,
            "items": {"type": "object", "properties": item_props, "additionalProperties": False}}


def obj(props):
    return {"type": "object", "properties": props, "additionalProperties": False}


def defaults(schema):
    out = {}
    for k, p in schema["properties"].items():
        d = p["default"]
        out[k] = [dict(x) for x in d] if isinstance(d, list) else d
    return out


def _check_value(path, p, v, palette_names):
    t = p["type"]
    if t == "number":
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ParamError("%s: expected number, got %r" % (path, v))
        if v < p["minimum"] or v > p["maximum"]:
            raise ParamError("%s: %r outside [%r, %r]" % (path, v, p["minimum"], p["maximum"]))
        return float(v)
    if t == "integer":
        if isinstance(v, bool) or not isinstance(v, int):
            raise ParamError("%s: expected integer, got %r" % (path, v))
        if v < p["minimum"] or v > p["maximum"]:
            raise ParamError("%s: %r outside [%r, %r]" % (path, v, p["minimum"], p["maximum"]))
        return int(v)
    if t == "boolean":
        if not isinstance(v, bool):
            raise ParamError("%s: expected boolean, got %r" % (path, v))
        return v
    if t == "string":
        if not isinstance(v, str):
            raise ParamError("%s: expected string, got %r" % (path, v))
        if "enum" in p and v not in p["enum"]:
            raise ParamError("%s: %r not in %r" % (path, v, p["enum"]))
        if p.get("x-palette-color"):
            if palette_names is not None and v not in palette_names:
                raise ParamError("%s: unknown palette colour %r for this pack" % (path, v))
        return v
    if t == "array":
        if not isinstance(v, list):
            raise ParamError("%s: expected array, got %r" % (path, v))
        if len(v) > p["maxItems"]:
            raise ParamError("%s: %d items > maxItems %d" % (path, len(v), p["maxItems"]))
        out = []
        for i, item in enumerate(v):
            out.append(validate_object("%s[%d]" % (path, i), p["items"], item, palette_names, fill=True))
        return out
    raise ParamError("%s: unsupported schema type %r" % (path, t))


def validate_object(path, schema, params, palette_names, fill=True):
    if not isinstance(params, dict):
        raise ParamError("%s: expected object, got %r" % (path, type(params).__name__))
    props = schema["properties"]
    for k in params:
        if k not in props:
            raise ParamError("%s: unknown param %r (allowed: %s)" % (path, k, ", ".join(sorted(props))))
    out = {}
    for k, p in props.items():
        if k in params:
            out[k] = _check_value(path + "." + k, p, params[k], palette_names)
        elif fill:
            d = p["default"]
            out[k] = _check_value(path + "." + k, p, [dict(x) for x in d] if isinstance(d, list) else d,
                                  palette_names)
    return out


def resolve(schema, layers, palette_names):
    """Merge param layers (dicts, later wins) after validating EACH layer, then fill defaults."""
    merged = {}
    for name, layer in layers:
        if layer is None:
            continue
        validate_object(name, schema, layer, palette_names, fill=False)
        merged.update(layer)
    return validate_object("params", schema, merged, palette_names, fill=True)
