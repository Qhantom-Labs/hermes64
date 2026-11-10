extends RefCounted
## State-only wire codec and exact membership proof. No scene or filesystem dependency.
## Greedy best-first changes exploration ORDER only; success requires an actual path.
## Only sound pruning: collected identities outside the target can never be removed.
var timestamps: Dictionary = {}
var has_timestamps := false

func pack(runtime) -> Dictionary:
	if runtime.game.contract_version == "1.2.0":
		return load("res://modules/save_codec.gd").new().pack(runtime, timestamps if has_timestamps else null)
	var out: Dictionary = runtime.state.duplicate(true)
	out.inventory.sort()
	if out.has("collected"):
		out.collected.sort()
	for key in ["contract_version", "spec_hash", "game_hash"]:
		out[key] = runtime.game[key]
	if has_timestamps:
		out.timestamps = timestamps.duplicate(true)
	return out

func reject(reason: String, status := "rejected") -> Dictionary:
	return {"ok": false, "status": status, "reason": reason}

func exact_keys(data: Dictionary, keys: Array) -> bool:
	var a := data.keys()
	var b := keys.duplicate()
	a.sort()
	b.sort()
	return a == b

func unique_sorted_ids(value, domain: Dictionary) -> bool:
	if not value is Array:
		return false
	var prior := ""
	for entry in value:
		if not entry is String or not domain.has(entry) or (prior != "" and entry <= prior):
			return false
		prior = entry
	return true

func state_fields(game: Dictionary) -> Array:
	var out := ["location", "inventory", "flags", "dialogue", "tide"]
	if game.contract_version == "1.1.0":
		out.append("collected")
	return out

func validate_shape(runtime, save: Dictionary) -> Dictionary:
	var fields := state_fields(runtime.game)
	var keys := fields + ["contract_version", "spec_hash", "game_hash"]
	if save.has("timestamps"):
		keys.append("timestamps")
		if not save.timestamps is Dictionary:
			return reject("timestamps must be an object")
	if not exact_keys(save, keys):
		return reject("save keys differ from versioned state-only contract")
	for key in ["contract_version", "spec_hash", "game_hash"]:
		if save[key] != runtime.game[key]:
			return reject("save %s does not match exact game; migrate explicitly with STORY source game" % key)
	if not save.location is String or not runtime.rooms.has(save.location):
		return reject("unknown location")
	if not unique_sorted_ids(save.inventory, runtime.index_by_id(runtime.game.items)):
		return reject("inventory must contain sorted unique known IDs")
	if save.has("collected") and not unique_sorted_ids(save.collected, runtime.collections):
		return reject("collected must contain sorted unique known identities")
	if not save.flags is Dictionary or not exact_keys(save.flags, runtime.game.start.flags.keys()):
		return reject("flag keys mismatch")
	for value in save.flags.values():
		if typeof(value) != TYPE_BOOL:
			return reject("flags require booleans")
	if not save.dialogue is Dictionary or not exact_keys(save.dialogue, runtime.dialogues.keys()):
		return reject("dialogue keys mismatch")
	var active := 0
	for did in save.dialogue:
		var nid = save.dialogue[did]
		if not nid is String:
			return reject("dialogue cursor must be string")
		if nid != "":
			active += 1
			if not runtime.nodes[did].has(nid):
				return reject("unknown dialogue node")
	if active > 1:
		return reject("multiple active dialogues")
	if not save.tide is Dictionary or not exact_keys(save.tide, ["state", "tick"]):
		return reject("invalid tide shape")
	if not save.tide.state is String or not runtime.tide_indices.has(save.tide.state):
		return reject("unknown tide state")
	if typeof(save.tide.tick) != TYPE_INT or save.tide.tick < 0 or save.tide.tick >= runtime.game.tide.states[runtime.tide_indices[save.tide.state]].duration:
		return reject("invalid tide tick")
	var state := {}
	for key in fields:
		state[key] = save[key]
	# Node guards are not structural: WAIT can move away from a guarded tide.
	if runtime.endings(state).size() > 1:
		return reject("ambiguous terminal save state")
	return {"ok": true, "state": state.duplicate(true)}

func score(st: Dictionary, target: Dictionary) -> int:
	var result := 0
	for cid in target.get("collected", []):
		if not st.collected.has(cid):
			result += 8
	for fid in target.flags:
		if st.flags[fid] != target.flags[fid]:
			result += 4
	for item in target.inventory:
		if not st.inventory.has(item):
			result += 3
	for item in st.inventory:
		if not target.inventory.has(item):
			result += 3
	for did in target.dialogue:
		if st.dialogue[did] != target.dialogue[did]:
			result += 1
	if st.location != target.location: result += 1
	if st.tide != target.tide: result += 1
	return result

func membership(runtime, target: Dictionary, max_states: int) -> Dictionary:
	if max_states < 1:
		return reject("membership cap must be positive")
	var initial: Dictionary = runtime.game.start.duplicate(true)
	var key := JSON.stringify(initial, "", true)
	var states := [initial]
	var visited := {key: 0}
	var parents := [[-1, ""]]
	var buckets := {score(initial, target): [0]}
	while not buckets.is_empty():
		var priorities := buckets.keys()
		priorities.sort()
		var priority: int = priorities[0]
		var index: int = buckets[priority].pop_front()
		if buckets[priority].is_empty():
			buckets.erase(priority)
		var st: Dictionary = states[index]
		if st == target:
			var witness := []
			while parents[index][0] != -1:
				witness.push_front(parents[index][1])
				index = parents[index][0]
			return {"ok": true, "status": "reachable", "explored": visited.size(), "witness": witness}
		for action in runtime.actions(st):
			var next: Dictionary = action.state
			var outside := false
			for cid in next.get("collected", []):
				if not target.collected.has(cid):
					outside = true
			if outside: continue
			key = JSON.stringify(next, "", true)
			if visited.has(key): continue
			if visited.size() >= max_states:
				return reject("state cap reached; exact save membership proof incomplete", "inconclusive")
			visited[key] = states.size()
			var next_score := score(next, target)
			if not buckets.has(next_score): buckets[next_score] = []
			buckets[next_score].append(states.size())
			parents.append([index, action.id])
			states.append(next)
	return reject("unreachable save state")

func load_into(runtime, save: Dictionary, max_states := 20000) -> Dictionary:
	if runtime.game.contract_version == "1.2.0":
		var result: Dictionary = load("res://modules/save_codec.gd").new().load_into(runtime, save, max_states)
		if result.ok:
			has_timestamps = save.has("timestamps")
			timestamps = save.get("timestamps", {}).duplicate(true)
		return result
	var shape := validate_shape(runtime, save)
	if not shape.ok: return shape
	var proof := membership(runtime, shape.state, max_states)
	if not proof.ok: return proof
	runtime.state = shape.state.duplicate(true)
	has_timestamps = save.has("timestamps")
	timestamps = save.get("timestamps", {}).duplicate(true)
	return {"ok": true, "status": "as_is", "reason": "exact hashes and reachable state match", "explored": proof.explored, "witness": proof.witness}
