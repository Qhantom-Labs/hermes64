"""Reduced ordered BDDs for exact sets of collectible identities; no third-party code."""


class BudgetExceeded(RuntimeError):
    pass


class BDD:
    def __init__(self, variables, max_nodes=200000):
        if type(variables) is not int or variables < 0 or type(max_nodes) is not int or max_nodes < 2:
            raise ValueError('invalid BDD variable/node budget')
        self.variables, self.max_nodes = variables, max_nodes
        self.nodes = [(variables, 0, 0), (variables, 1, 1)]
        self.unique = {}
        self.apply_cache, self.not_cache = {}, {0: 1, 1: 0}
        self.restrict_cache, self.count_cache, self.threshold_cache = {}, {}, {}

    def node(self, i, low, high):
        if low == high:
            return low
        key = (i, low, high)
        if key not in self.unique:
            if len(self.nodes) >= self.max_nodes:
                raise BudgetExceeded('BDD node cap reached')
            self.unique[key] = len(self.nodes)
            self.nodes.append(key)
        return self.unique[key]

    def var(self, i):
        if not 0 <= i < self.variables:
            raise ValueError('BDD variable out of range')
        return self.node(i, 0, 1)

    def _apply(self, op, a, b):
        if a > b:
            a, b = b, a
        if op == 'and':
            if a == 0: return 0
            if a == 1: return b
        else:
            if a == 0: return b
            if a == 1: return 1
        if a == b: return a
        key = (op, a, b)
        if key in self.apply_cache:
            return self.apply_cache[key]
        ia, la, ha = self.nodes[a]
        ib, lb, hb = self.nodes[b]
        i = min(ia, ib)
        if ia != i: la = ha = a
        if ib != i: lb = hb = b
        out = self.node(i, self._apply(op, la, lb), self._apply(op, ha, hb))
        self.apply_cache[key] = out
        return out

    def intersect(self, a, b): return self._apply('and', a, b)
    def union(self, a, b): return self._apply('or', a, b)

    def negate(self, a):
        if a not in self.not_cache:
            i, lo, hi = self.nodes[a]
            out = self.node(i, self.negate(lo), self.negate(hi))
            self.not_cache[a] = out
            self.not_cache[out] = a
        return self.not_cache[a]

    def difference(self, a, b):
        return self.intersect(a, self.negate(b))

    def restrict(self, a, i, value):
        key = (a, i, bool(value))
        if key in self.restrict_cache:
            return self.restrict_cache[key]
        j, lo, hi = self.nodes[a]
        if a < 2 or j > i:
            out = a
        elif j == i:
            out = hi if value else lo
        else:
            out = self.node(j, self.restrict(lo, i, value), self.restrict(hi, i, value))
        self.restrict_cache[key] = out
        return out

    def evaluate(self, a, bits):
        while a >= 2:
            i, lo, hi = self.nodes[a]
            a = hi if bits & (1 << i) else lo
        return bool(a)

    def assignment(self, bits):
        out = 1
        for i in reversed(range(self.variables)):
            out = self.node(i, 0, out) if bits & (1 << i) else self.node(i, out, 0)
        return out

    def count(self, a, level=0):
        key = (a, level)
        if key not in self.count_cache:
            if a < 2:
                out = (1 << (self.variables - level)) if a else 0
            else:
                i, lo, hi = self.nodes[a]
                out = (1 << (i - level)) * (self.count(lo, i + 1) + self.count(hi, i + 1))
            self.count_cache[key] = out
        return self.count_cache[key]

    def pick(self, a):
        if not a:
            return None
        bits = 0
        while a >= 2:
            i, lo, hi = self.nodes[a]
            if lo:
                a = lo
            else:
                bits |= 1 << i
                a = hi
        return bits

    def threshold(self, indices, minimum):
        indices = tuple(sorted(indices))
        key = (indices, minimum)
        if key not in self.threshold_cache:
            if minimum <= 0:
                out = 1
            elif minimum > len(indices):
                out = 0
            else:
                out = self.node(indices[0], self.threshold(indices[1:], minimum), self.threshold(indices[1:], minimum - 1))
            self.threshold_cache[key] = out
        return self.threshold_cache[key]

    def add_image(self, a, i):
        return self.intersect(self.restrict(a, i, False), self.var(i))

    def add_preimage(self, a, i):
        return self.intersect(self.restrict(a, i, True), self.negate(self.var(i)))
