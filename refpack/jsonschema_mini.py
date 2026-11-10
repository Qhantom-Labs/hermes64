"""Minimal stdlib JSON-Schema subset validator (draft-07 style) for refpack's own schemas.
Supports: type, enum, const, properties, required, additionalProperties(false), items, minItems,
maxItems, uniqueItems, minimum, maximum, minLength, maxLength, pattern, $ref (#/definitions/...).
Returns a list of 'path: message' strings (empty = valid)."""
import re

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf")),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance, schema, root=None, path="$", errors=None, max_errors=50):
    if errors is None:
        errors = []
    if root is None:
        root = schema
    if len(errors) >= max_errors:
        return errors
    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            errors.append("%s: unsupported $ref %r" % (path, ref))
            return errors
        return validate(instance, root["definitions"][ref.split("/")[-1]], root, path, errors, max_errors)
    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPES[x](instance) for x in types):
            errors.append("%s: expected %s, got %s" % (path, "/".join(types), type(instance).__name__))
            return errors
    if "const" in schema and instance != schema["const"]:
        errors.append("%s: must be %r" % (path, schema["const"]))
    if "enum" in schema and instance not in schema["enum"]:
        shown = schema["enum"] if len(schema["enum"]) <= 12 else schema["enum"][:12] + ["..."]
        errors.append("%s: %r is not one of %s" % (path, instance, shown))
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append("%s: shorter than %d" % (path, schema["minLength"]))
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append("%s: longer than %d characters" % (path, schema["maxLength"]))
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append("%s: does not match %s" % (path, schema["pattern"]))
    if _TYPES["number"](instance):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append("%s: %r < minimum %r" % (path, instance, schema["minimum"]))
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append("%s: %r > maximum %r" % (path, instance, schema["maximum"]))
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append("%s: needs at least %d items" % (path, schema["minItems"]))
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append("%s: at most %d items allowed (got %d)" % (path, schema["maxItems"], len(instance)))
        if schema.get("uniqueItems"):
            seen = []
            for v in instance:
                if v in seen:
                    errors.append("%s: duplicate item %r" % (path, v))
                    break
                seen.append(v)
        if "items" in schema:
            for i, v in enumerate(instance):
                validate(v, schema["items"], root, "%s[%d]" % (path, i), errors, max_errors)
    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for k in schema.get("required", []):
            if k not in instance:
                errors.append("%s: missing required key %r" % (path, k))
        if schema.get("additionalProperties") is False:
            for k in sorted(instance):
                if k not in props:
                    errors.append("%s: unknown key %r" % (path, k))
        for k, sub in props.items():
            if k in instance:
                validate(instance[k], sub, root, "%s.%s" % (path, k), errors, max_errors)
    return errors
