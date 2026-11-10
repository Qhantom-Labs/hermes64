extends RefCounted
## Strict v2 checkpoint codec. Membership is abstract, not authenticated play history.
const Legacy = preload("res://core/save_codec.gd")
func reject(reason: String) -> Dictionary:
	return {"ok": false, "status": "rejected", "reason": reason}
func safe(runtime, st: Dictionary) -> bool:
	if not st.get("modules") is Dictionary: return false
	var ms: Dictionary = st.modules
	return ms.get("active", "?") == "" and ms.get("failed", "?") == "" and runtime.modules.checkpoints.has(ms.get("checkpoint", "")) and runtime.modules.checkpoints[ms.checkpoint].room == st.get("location")
func contract_hash(runtime) -> String:
	return JSON.stringify(runtime.game.module_contract, "", true).sha256_text()
func pack(runtime, timestamps = null) -> Dictionary:
	if not safe(runtime, runtime.state): return reject("active/failed or uncommitted checkpoint")
	var out := {"save_version": "2.0.0", "contract_version": "1.2.0", "spec_hash": runtime.game.spec_hash, "game_hash": runtime.game.game_hash, "module_contract_hash": contract_hash(runtime), "state": runtime.state.duplicate(true)}
	if timestamps != null: out.timestamps = timestamps.duplicate(true)
	return out
func load_into(runtime, save: Dictionary, cap: int) -> Dictionary:
	var codec = Legacy.new()
	var keys := ["save_version", "contract_version", "spec_hash", "game_hash", "module_contract_hash", "state"]
	if save.has("timestamps"):
		keys.append("timestamps")
		if not save.timestamps is Dictionary: return reject("invalid timestamps")
	if not codec.exact_keys(save, keys): return reject("unexpected checkpoint fields")
	if save.save_version != "2.0.0" or save.contract_version != "1.2.0": return reject("unsupported checkpoint version")
	if save.spec_hash != runtime.game.spec_hash or save.game_hash != runtime.game.game_hash or save.module_contract_hash != contract_hash(runtime): return reject("checkpoint provenance mismatch")
	if not save.state is Dictionary or not safe(runtime, save.state): return reject("unsafe checkpoint")
	if not codec.exact_keys(save.state, runtime.game.start.keys()): return reject("transient/unknown state fields")
	if not codec.exact_keys(save.state.modules, runtime.game.start.modules.keys()): return reject("unknown module state fields")
	for field in ["abilities", "completed", "discovered"]:
		var domain: Dictionary = {"abilities": runtime.modules.abilities, "completed": runtime.modules.challenges, "discovered": runtime.modules.regions}[field]
		if not codec.unique_sorted_ids(save.state.modules[field], domain): return reject("unknown/unsorted module IDs")
	# Exact dictionary equality with reached states also rejects invalid core types/keys.
	if cap < 1 or cap > 100000: return reject("invalid membership cap")
	# STORY 1.3 puzzle builds: the lowered actions cannot set reserved puzzle flags, so membership comes from the
	# build's proved safe-checkpoint set (puzzle.json "reachable", installed by modules/puzzle/controller.gd).
	if runtime.has_meta("puzzle_reachable"):
		for st in runtime.get_meta("puzzle_reachable"):
			if st == save.state:
				runtime.state = save.state.duplicate(true)
				return {"ok": true, "status": "as_is", "explored": 0, "witness": [], "reason": "proved STORY 1.3 safe-checkpoint set; no physical-history claim"}
		return reject("unreachable puzzle checkpoint")
	var initial: Dictionary = runtime.game.start.duplicate(true)
	var queue := [initial]
	var visited := {JSON.stringify(initial, "", true): true}
	var index := 0
	var edges := 0
	while index < queue.size():
		var st: Dictionary = queue[index]
		index += 1
		if st == save.state:
			runtime.state = st.duplicate(true)
			return {"ok": true, "status": "as_is", "explored": index, "witness": [], "reason": "abstract checkpoint membership; no physical-history claim"}
		for a in runtime.modules.analysis_actions(runtime, st):
			edges += 1
			if edges > 1000000: return reject("membership edge cap")
			var key := JSON.stringify(a.state, "", true)
			if visited.has(key): continue
			if visited.size() >= cap: return reject("membership state cap")
			visited[key] = true
			queue.append(a.state)
	return reject("unreachable checkpoint")
