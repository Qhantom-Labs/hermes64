# Exact symbolic collectible analysis — 1.1.0

## Concrete model and admissibility

A state is `(q,C)` with finite non-collectible core `q` and set `C` of declared collectible identities. The core includes location, finite inventory, Boolean mutable flags, at most one dialogue cursor, and finite cyclic timer phase/tick. Asset/story text has no executable semantics. Only declared deterministic actions exist. Collectibles are never removed in play; one collect action adds one previously absent identity and optionally opens a dialogue. Other actions preserve C. All guards are conjunctions of core predicates, positive identity membership, and group-cardinality lower bounds. Ordered ordinary effects act only on the core. Follower flags/counters are derived from C. This exact contract is validated before analysis; no unsupported semantics are approximated.

For each core, a transition template is `(q,a,g,u,q')`: `g(C)` is the exact Boolean guard including destination-node guards and terminal exclusion; `u` is identity or add-one-bit. Missing ordinary item prerequisites disable a whole template. The direct engine and symbolic solver share these templates/effect semantics, but concrete BFS enumerates states independently of the symbolic representation. Differential tests therefore additionally compare templates with direct expected transition fixtures and test BDD operations against truth tables.

## Representation

Each collectible is a Boolean variable ordered by sorted ID. A reduced ordered BDD represents a set of assignments, NOT a maximal collectible union. Nodes are hash-consed; identical low/high branches reduce. Identity predicates and cardinality thresholds build exact formulas. Set union/intersection/complement and restriction are Boolean operations. No count quotient, maximal-set domination or optimistic auto-pickup occurs. Alternative reachable sets stay alternatives; mutually exclusive sphere branches cannot be merged into a fictional combined inventory.

## Forward fixed point / shortest witnesses

Initially R(q0) is the one exact initial assignment and other cores are empty. In breadth-first symbolic layers apply:

- ordinary edge: `image(X)=X ∩ g` at q';
- collect bit i: guard additionally requires `not i`; `image(X) = (exists i: X ∩ g) ∩ i` at q'. Since the input guard forces i=false, existential abstraction equals restricting i=false before conjoining i=true.

Each new frontier subtracts assignments already visited at its target core. Matching endings are partitioned by exact guards: one match is a valid terminal; multiple matches are an ambiguous terminal error. All matching terminals are excluded from outgoing transitions. Iterate until no new assignment appears. By induction on path length, layer k is exactly the set of concrete states first reached at depth k: the base is exact; each edge image is exact; union enumerates alternatives; subtraction removes only earlier states. Hence the final fixed point is exactly the reachable state set. Its BDD satisfying-assignment count sums to the exact concrete state count. Resource exhaustion reports INCONCLUSIVE.

For a target concrete assignment selected from a reachable BDD, backtrack through the previous frontier and an edge whose preimage contains it. An ordinary edge preserves the assignment; a collection predecessor clears only its added bit. Every selected predecessor is checked in the preceding frontier. This constructs a concrete shortest action witness, not a union of incompatible paths. Replaying it in the direct engine is a required evidence check.

## Backward obligations

Within the forward reachable graph, compute W as the least fixed point seeded with valid terminal assignments and closed under exact edge preimages. Ordinary preimage is `W(q') ∩ g`; collection preimage is `W(q')[i:=true] ∩ not i ∩ g`. Intersect every result with R(q). Source terminal exclusion remains in g. Induction on distance to a terminal proves W exactly contains states with a finite route to an ending. Nonterminal `R \ W` are exactly softlocks, even if they contain cycles or infinite WAIT policies. A state is a dead end iff no enabled transition changes its core or collectible assignment.

For each identity i, repeat the backward fixed point seeded with all reachable states already containing i. Nonterminal reachable states lacking i and absent from this fixed point are exactly states from which i is permanently unobtainable before termination. This catches one-way gates/storm changes even when i is obtainable on another branch. Ending states deliberately terminate and are not accused of making optional collections missable. Per-collectible existence and group/threshold attainability are intersections with their exact predicates. No reversibility/fairness assumptions are used; clocks advance only by explicit WAIT.

## Scope of the proof

These arguments establish equivalence to the finite concrete transition system for every valid 1.1.0 spec **when all fixed points finish**. They do not prove correctness of an implementation by themselves: truth-table tests, many deterministic generated-game comparisons with concrete BFS (including rejected games), witness replay, explicit irreversible-gate/terminal/threshold controls and preserved 1.0.0 regressions are mandatory. Counts/results from those runs belong in RESULT.md, not in this pre-implementation document.

BDD compression is data-dependent; exponential worst cases remain possible. The solver has separate core/BDD budgets and returns INCONCLUSIVE on exhaustion. It never claims a general polynomial-time algorithm, credits an optional pickup, raises the brute-force state cap to accommodate Thaw, or transfers this proof to untested Godot behavior.
