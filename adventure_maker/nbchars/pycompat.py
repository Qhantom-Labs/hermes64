"""Python-version float compatibility for the vendored generator.

The published oracle GLBs were generated inside Blender 5.2.1, which runs CPython 3.13. Two builtins the generator
uses changed their float results between CPython releases:
  * sum() of floats uses Neumaier compensated summation since 3.12 (3.9-3.11 add naively; 3.14 also compensates
    int items);
  * math.hypot() uses the lossless-scaling vector_norm algorithm (3.9 calls libm hypot).
On an older interpreter the generator's floats then differ in the last bits (quaternion normalisation in core/pose.py,
ring centres in core/enemies.py, prop placement in core/attach.py ...). These functions reproduce the 3.13 results
bit for bit on any CPython >= 3.8, and gen.py installs them into the generator's module namespaces when needed, so
the Blender-free exporter produces the same floats on every supported interpreter.
"""
import math
import sys
import types
from fractions import Fraction

REFERENCE = (3, 13)
# 3.13 itself needs nothing; every other interpreter gets the 3.13 functions (3.14 changed sum() again: ints inside a
# float sum now join the compensated path). Both were verified against Blender's bundled CPython 3.13.13 binary.
NEED_SUM = sys.version_info[:2] != REFERENCE
NEED_HYPOT = sys.version_info[:2] != REFERENCE
_bsum = sum
_LONG_MIN, _LONG_MAX = -(1 << 63), (1 << 63) - 1


def sum313(iterable, /, start=0):
    """builtins.sum with CPython 3.13 semantics (fast int path, Neumaier float path, generic fallback)."""
    it = iter(iterable)
    result = start
    if type(result) is int:
        for item in it:
            if type(item) is int or type(item) is bool:
                result = result + item
                continue
            result = result + item
            break
        else:
            return result
    if type(result) is float:
        f, c = result, 0.0
        for item in it:
            if type(item) is float:
                x = item
                t = f + x
                if abs(f) >= abs(x):
                    c += (f - t) + x
                else:
                    c += (x - t) + f
                f = t
                continue
            if isinstance(item, int) and _LONG_MIN <= item <= _LONG_MAX:
                f += float(item)
                continue
            if c and math.isfinite(c):
                f += c
            result = f + item
            break
        else:
            if c and math.isfinite(c):
                f += c
            return f
    for item in it:
        result = result + item
    return result


def _dl_mul(x, y):
    z = x * y
    return z, float(Fraction(x) * Fraction(y) - Fraction(z))


def _dl_fast_sum(a, b):
    x = a + b
    return x, (a - x) + b


def _vector_norm(vec, mx):
    if math.isinf(mx):
        return mx
    if any(math.isnan(v) for v in vec):
        return math.nan
    if mx == 0.0 or len(vec) <= 1:
        return mx
    _, max_e = math.frexp(mx)
    if max_e < -1023:
        return 2.2250738585072014e-308 * _vector_norm([v / 2.2250738585072014e-308 for v in vec], mx / 2.2250738585072014e-308)
    scale = math.ldexp(1.0, -max_e)
    csum, frac1, frac2 = 1.0, 0.0, 0.0
    for x in vec:
        x *= scale
        hi, lo = _dl_mul(x, x)
        s_hi, s_lo = _dl_fast_sum(csum, hi)
        csum = s_hi
        frac1 += lo
        frac2 += s_lo
    h = math.sqrt(csum - 1.0 + (frac1 + frac2))
    hi, lo = _dl_mul(-h, h)
    s_hi, s_lo = _dl_fast_sum(csum - 1.0, hi)
    csum = s_hi
    frac1 += lo
    frac2 += s_lo
    x = csum + (frac1 + frac2)
    h += x / (2.0 * h)
    return h / scale


def hypot313(*coords):
    vec = [abs(float(c)) for c in coords]
    if not vec:
        return 0.0
    return _vector_norm(vec, max(vec))


def math_proxy():
    m = types.ModuleType('math')
    m.__dict__.update({k: getattr(math, k) for k in dir(math) if not k.startswith('__')})
    setattr(m, 'hypot', hypot313)
    return m


def install(module):
    """Make one generator module compute like CPython 3.13 (call before exec for sum, after exec for math)."""
    if NEED_SUM:
        module.__dict__['sum'] = sum313


def install_after(module):
    if NEED_HYPOT and module.__dict__.get('math') is math:
        module.__dict__['math'] = math_proxy()


def describe():
    return {'python': '%d.%d.%d' % sys.version_info[:3], 'sum_compat': NEED_SUM, 'hypot_compat': NEED_HYPOT,
            'reference': 'CPython 3.13 (Blender 5.2.1 bundled interpreter)'}
