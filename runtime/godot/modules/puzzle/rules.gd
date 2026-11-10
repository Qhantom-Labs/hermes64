extends RefCounted
## Exact port of story/puzzle/rules.py (Grid): same tokens, same settle order, same 63-bit state key.
## Parity is bound by tools/puzzle_vectors.py + tests/puzzle_rules.gd. Pure data in, data out; no clock.
const DIRS := {"n": Vector2i(0, -1), "e": Vector2i(1, 0), "s": Vector2i(0, 1), "w": Vector2i(-1, 0)}
const ORDER := ["n", "e", "s", "w"]
const OPPOSITE := {"n": "s", "s": "n", "e": "w", "w": "e"}
const ACTABLE := ["switch", "torch", "lock", "key", "orb"]
const SOLID := ["switch", "torch", "orb", "shutter", "key"]

var id := ""
var room := ""
var cols := 0
var rows := 0
var layout: Array = []
var persistent := false
var resettable := true
var hint: Array = []
var goal: Dictionary = {}
var opens := {}
var el := {}
var ids: Array = []
var blocks: Array = []
var timed: Array = []
var step_ticks := 18
var open_steps := {}
var cell_of := {}
var bridge_at := {}
var bits: Array = []
var bit := {}
var ordered: Array = []
var ordered_mask := 0
var latchable := {}
var exits := {}
var exit_cells := {}
var start := Vector2i.ZERO
var relevant_items := {}

static func door_cell(door: Dictionary, room_data: Dictionary) -> Vector2i:
	var w := int(room_data.grid_size[0])
	var d := int(room_data.grid_size[1])
	var p := int(door.position)
	match str(door.wall):
		"north": return Vector2i(p, 0)
		"south": return Vector2i(p, d - 1)
		"west": return Vector2i(0, p)
	return Vector2i(w - 1, p)

static func cell(a) -> Vector2i:
	return Vector2i(int(a[0]), int(a[1]))

func configure(room_data: Dictionary, puzzle: Dictionary, config: Dictionary) -> void:
	id = str(puzzle.id)
	room = str(room_data.id)
	cols = int(room_data.grid_size[0])
	rows = int(room_data.grid_size[1])
	layout = puzzle.layout
	persistent = puzzle.persistence == "persistent"
	resettable = puzzle.reset == "hold"
	hint = puzzle.hint
	goal = puzzle.goal
	for o in goal.opens: opens[str(o)] = true
	for e in puzzle.elements: el[str(e.id)] = e
	ids = el.keys()
	ids.sort()
	step_ticks = int(config.step_ticks)
	for i in ids:
		var e: Dictionary = el[i]
		match str(e.kind):
			"block": blocks.append(i)
			"timed_gate":
				timed.append(i)
				open_steps[i] = int(e.open_ticks) / step_ticks
		if e.kind == "bridge":
			for c in e.cells: bridge_at[cell(c)] = i
		elif e.kind != "block":
			cell_of[cell(e.cell)] = i
	for i in ids:
		var e: Dictionary = el[i]
		var k := str(e.kind)
		if k in ["switch", "torch", "orb"] or (k == "plate" and e.mode == "latch"): bits.append([i, "on"])
		elif k in ["door", "bridge"]: bits.append([i, "open"])
		elif k == "timed_gate":
			bits.append([i, "open"]); bits.append([i, "prev"])
	for n in bits.size(): bit[bits[n][0] + ":" + bits[n][1]] = 1 << n
	for i in ids:
		if el[i].kind == "torch" and int(el[i].order) > 0:
			ordered.append(i)
			ordered_mask |= bit[i + ":on"]
		if persistent and el[i].kind in ["switch", "plate"] and el[i].mode == "latch": latchable[i] = true
	var dids: Array = []
	for door in room_data.doors:
		exits[str(door.id)] = door_cell(door, room_data)
		dids.append(str(door.id))
	dids.sort()
	for did in dids:
		var c: Vector2i = exits[did]
		if not exit_cells.has(c): exit_cells[c] = []
		exit_cells[c].append(did)
	start = cell(puzzle.start)
	for i in ids:
		if el[i].kind == "lock":
			for item in el[i].accepts: relevant_items[str(item)] = true

## ctx: {taken:{}, opened:{}, latched:{}, solved:bool, inventory:{}} (dictionaries used as sets)
func ctx(solved: Array, taken: Array, opened: Array, latched: Array, inventory: Array) -> Dictionary:
	var out := {"taken": {}, "opened": {}, "latched": {}, "solved": solved.has(id), "inventory": {}}
	for x in taken:
		if el.has(x): out.taken[x] = true
	for x in opened:
		if el.has(x): out.opened[x] = true
	for x in latched:
		if latchable.has(x): out.latched[x] = true
	for x in inventory:
		if relevant_items.has(x): out.inventory[x] = true
	return out

func after(c: Dictionary, events: Array) -> Dictionary:
	var out := {"taken": c.taken.duplicate(), "opened": c.opened.duplicate(), "latched": c.latched.duplicate(), "solved": c.solved, "inventory": c.inventory.duplicate()}
	for ev in events:
		match str(ev[0]):
			"take":
				out.taken[ev[1]] = true
				var item := str(el[ev[1]].item)
				if relevant_items.has(item): out.inventory[item] = true
			"unlock":
				out.opened[ev[1]] = true
				out.inventory.erase(ev[2])
			"latch": out.latched[ev[1]] = true
			"solve": out.solved = true
	return out

func make(p: Vector2i, b: Array, on: int, tm: Array) -> Dictionary:
	return {"p": p, "blocks": b, "on": on, "tm": tm}

func index(c: Vector2i) -> int:
	return c.y * cols + c.x

func key(st: Dictionary) -> int:
	var k := index(st.p)
	for n in st.blocks.size(): k |= index(st.blocks[n]) << (8 * (n + 1))
	for n in st.tm.size(): k |= int(st.tm[n]) << (32 + 4 * n)
	return k | (int(st.on) << 40)

func inside(c: Vector2i) -> bool:
	return c.x >= 0 and c.y >= 0 and c.x < cols and c.y < rows

func terrain(c: Vector2i) -> String:
	return str(layout[c.y])[c.x]

func has(st: Dictionary, eid: String, role := "on") -> bool:
	return (int(st.on) & int(bit[eid + ":" + role])) != 0

func weight_at(st: Dictionary, c: Vector2i) -> int:
	if st.p == c: return 1
	return 2 if st.blocks.has(c) else 0

func source(st: Dictionary, c: Dictionary, sid: String) -> bool:
	var e: Dictionary = el[sid]
	if e.kind == "lock": return c.opened.has(sid)
	if e.kind == "plate":
		if e.mode == "latch" and (has(st, sid) or c.latched.has(sid)): return true
		return weight_at(st, cell(e.cell)) >= int(e.weight)
	return c.latched.has(sid) or has(st, sid)

func link(st: Dictionary, c: Dictionary, value: Dictionary) -> bool:
	var count := 0
	for sid in value.of:
		if source(st, c, str(sid)): count += 1
	return (count >= int(value.at_least)) != bool(value.invert)

func floor_like(st: Dictionary, c: Vector2i) -> bool:
	if not inside(c): return false
	var t := terrain(c)
	if t == "#": return false
	if t == "_":
		return bridge_at.has(c) and has(st, bridge_at[c], "open")
	return true

func solid(st: Dictionary, c: Dictionary, at: Vector2i) -> bool:
	if not cell_of.has(at): return false
	var eid: String = cell_of[at]
	var k := str(el[eid].kind)
	if k in SOLID: return true
	if k == "lock": return not c.opened.has(eid)
	if k in ["door", "timed_gate"]: return not has(st, eid, "open")
	return false

func walkable(st: Dictionary, c: Dictionary, at: Vector2i) -> bool:
	return floor_like(st, at) and not solid(st, c, at) and not st.blocks.has(at)

func block_free(st: Dictionary, c: Dictionary, at: Vector2i, player_leaves := false) -> bool:
	return floor_like(st, at) and not solid(st, c, at) and not st.blocks.has(at) and (player_leaves or at != st.p)

func occupied(st: Dictionary, at: Vector2i) -> bool:
	return st.p == at or st.blocks.has(at)

static func adjacent(a: Vector2i, b: Vector2i) -> bool:
	return absi(a.x - b.x) + absi(a.y - b.y) == 1

func strike_clear(st: Dictionary, c: Dictionary, a: Vector2i, b: Vector2i) -> bool:
	var step := Vector2i(signi(b.x - a.x), signi(b.y - a.y))
	var at := a + step
	while at != b:
		if terrain(at) == "#" or st.blocks.has(at) or solid(st, c, at): return false
		at += step
	return true

## One micro action, no time passing. Returns [state, events] or null.
func apply(st: Dictionary, c: Dictionary, token: String) -> Variant:
	var p: Vector2i = st.p
	if token.begins_with("move."):
		var d := token.substr(5)
		var dv: Vector2i = DIRS[d]
		var t := p + dv
		if not inside(t): return null
		if cell_of.has(t) and el[cell_of[t]].kind == "shutter":
			var eid: String = cell_of[t]
			var sd := str(el[eid].dir)
			if d != sd and not (c.solved and opens.has(eid) and d == OPPOSITE[sd]): return null
			var t2 := t + dv
			if not walkable(st, c, t2): return null
			return [make(t2, st.blocks, st.on, st.tm), []]
		if st.blocks.has(t):
			var n: int = st.blocks.find(t)
			var t2 := t + dv
			if not block_free(st, c, t2): return null
			var nb: Array = st.blocks.duplicate()
			nb[n] = t2
			return [make(t, nb, st.on, st.tm), []]
		if not walkable(st, c, t): return null
		return [make(t, st.blocks, st.on, st.tm), []]
	if token.begins_with("pull."):
		var dv: Vector2i = DIRS[token.substr(5)]
		var t := p + dv
		var b := p - dv
		if not st.blocks.has(b) or not bool(el[blocks[st.blocks.find(b)]].pull): return null
		if not walkable(st, c, t) or not block_free(st, c, p, true): return null
		var nb: Array = st.blocks.duplicate()
		nb[st.blocks.find(b)] = p
		return [make(t, nb, st.on, st.tm), []]
	if token.begins_with("act."):
		return act(st, c, token.substr(4))
	if token == "wait":
		for t in st.tm:
			if int(t) > 0: return [st, []]
		return null
	return null

func act(st: Dictionary, c: Dictionary, eid: String) -> Variant:
	if not el.has(eid): return null
	var e: Dictionary = el[eid]
	var k := str(e.kind)
	if not k in ACTABLE: return null
	var p: Vector2i = st.p
	var at := cell(e.cell)
	var on: int = st.on
	match k:
		"switch":
			if not adjacent(p, at): return null
			var b: int = bit[eid + ":on"]
			if e.mode == "latch":
				if (on & b) != 0 or c.latched.has(eid): return null
				return [make(p, st.blocks, on | b, st.tm), [["latch", eid]] if latchable.has(eid) else []]
			return [make(p, st.blocks, on ^ b, st.tm), []]
		"torch":
			if not adjacent(p, at) or (on & int(bit[eid + ":on"])) != 0: return null
			if int(e.order) > 0:
				for o in ordered:
					if int(el[o].order) < int(e.order) and (on & int(bit[o + ":on"])) == 0:
						return [make(p, st.blocks, on & ~ordered_mask, st.tm), []]
			return [make(p, st.blocks, on | int(bit[eid + ":on"]), st.tm), []]
		"lock":
			if not adjacent(p, at) or c.opened.has(eid): return null
			var accepts: Array = e.accepts.duplicate()
			accepts.sort()
			for item in accepts:
				if c.inventory.has(item): return [st, [["unlock", eid, str(item)]]]
			return null
		"key":
			if c.taken.has(eid) or not adjacent(p, at): return null
			return [st, [["take", eid]]]
	# orb: along a row or column, within reach, first obstacle on the ray
	if not (p.x == at.x or p.y == at.y) or p == at: return null
	if absi(p.x - at.x) + absi(p.y - at.y) > int(e.reach) or not strike_clear(st, c, p, at): return null
	return [make(p, st.blocks, on ^ int(bit[eid + ":on"]), st.tm), []]

## Time passes; latch plates, doors, bridges, gates update in sorted id order; goal is checked.
func settle(st: Dictionary, c: Dictionary, steps := 1) -> Array:
	var on: int = st.on
	var tm: Array = []
	for t in st.tm: tm.append(maxi(0, int(t) - steps))
	var events := []
	for i in ids:
		var e: Dictionary = el[i]
		if e.kind == "plate" and e.mode == "latch":
			if weight_at(st, cell(e.cell)) >= int(e.weight) and (on & int(bit[i + ":on"])) == 0 and not c.latched.has(i):
				on |= int(bit[i + ":on"])
				if latchable.has(i): events.append(["latch", i])
	var cur := make(st.p, st.blocks, on, tm.duplicate())
	for i in ids:
		var e: Dictionary = el[i]
		var k := str(e.kind)
		if not k in ["door", "bridge", "timed_gate"]: continue
		var forced: bool = c.solved and opens.has(i)
		var ob: int = bit[i + ":open"]
		var was := (on & ob) != 0
		var value := link(cur, c, e.when)
		var now := false
		if k == "door":
			now = value or forced or (was and occupied(cur, cell(e.cell)))
		elif k == "bridge":
			if e.mode == "latch": now = was or value or forced
			else:
				var held := false
				for bc in e.cells:
					if occupied(cur, cell(bc)): held = true
				now = value or forced or (was and held)
		else:
			var n := timed.find(i)
			var pb: int = bit[i + ":prev"]
			if value and (on & pb) == 0: tm[n] = open_steps[i]
			now = int(tm[n]) > 0 or forced or (was and occupied(cur, cell(e.cell)))
			on = (on | pb) if value else (on & ~pb)
		on = (on | ob) if now else (on & ~ob)
		cur = make(st.p, st.blocks, on, tm.duplicate())
	if not c.solved and link(cur, c, goal.when): events.append(["solve"])
	return [cur, events]

func advance(st: Dictionary, c: Dictionary, token: String) -> Variant:
	var res: Variant = apply(st, c, token)
	if res == null: return null
	var out: Array = res
	var settled := settle(out[0], c, 1)
	return [settled[0], out[1] + settled[1]]

func canonical(c: Dictionary, entry := "") -> Array:
	var p: Vector2i = start if entry == "" else exits[entry]
	var b: Array = []
	for i in blocks: b.append(cell(el[i].cell))
	var on := 0
	for i in c.latched: on |= int(bit[i + ":on"])
	var tm: Array = []
	for i in timed: tm.append(0)
	return settle(make(p, b, on, tm), c, 0)

func tokens(st: Dictionary) -> Array:
	var out := []
	for d in ORDER: out.append("move." + d)
	for d in ORDER: out.append("pull." + d)
	for i in ids:
		if el[i].kind in ACTABLE: out.append("act." + i)
	for t in st.tm:
		if int(t) > 0:
			out.append("wait")
			break
	return out

static func event_token(ev: Array) -> String:
	return ".".join(PackedStringArray(ev.map(func(x): return str(x))))
