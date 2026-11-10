extends RefCounted
## Finite STORY 1.2 reducer. Continuous attempts belong only to the trusted host.
var catalogue := {}
var abilities := {}
var challenges := {}
var checkpoints := {}
var regions := {}
func configure(game: Dictionary) -> Dictionary:
	if not game.has("module_contract") or not game.has("gameplay") or not game.start.has("modules"):
		return {"ok": false, "reason": "missing module contract"}
	# API 1.1.0 (robot/boss templates) is additive; every module carries the manifest's version.
	var api = game.gameplay.get("api_version")
	if api not in ["1.0.0", "1.1.0", "1.2.0"]: return {"ok": false, "reason": "unsupported module API"}
	for m in game.gameplay.modules:
		if m.id not in ["abilities", "challenge", "combat", "course", "regions"] or m.version != api or catalogue.has(m.id):
			return {"ok": false, "reason": "unsupported/duplicate module"}
		catalogue[m.id] = m
	if not catalogue.has("abilities") or not catalogue.has("challenge"): return {"ok": false, "reason": "missing host dependency"}
	abilities = entities("abilities", "abilities")
	challenges = entities("challenge", "challenges")
	checkpoints = entities("challenge", "checkpoints")
	regions = entities("regions", "regions")
	return {"ok": true}
func entities(mid: String, collection: String) -> Dictionary:
	var out := {}
	for e in catalogue.get(mid, {}).get("entities", {}).get(collection, []): out[e.id] = e
	return out
func discover(st: Dictionary) -> Dictionary:
	var out := st.duplicate(true)
	for id in regions:
		if regions[id].room == out.location and not out.modules.discovered.has(id): out.modules.discovered.append(id)
	out.modules.discovered.sort()
	return out
func outcome(st: Dictionary, success: bool) -> Dictionary:
	if st.modules.active == "" or not challenges.has(st.modules.active): return st.duplicate(true)
	var out := st.duplicate(true)
	var c: Dictionary = challenges[st.modules.active]
	out.modules.active = ""
	if success:
		if out.modules.completed.has(c.id): return st.duplicate(true)
		out.modules.completed.append(c.id)
		out.modules.completed.sort()
		for id in c.rewards.items:
			if not out.inventory.has(id): out.inventory.append(id)
		for id in c.rewards.abilities:
			if not out.modules.abilities.has(id): out.modules.abilities.append(id)
		out.inventory.sort()
		out.modules.abilities.sort()
	else:
		out.location = checkpoints[c.checkpoint].room
		out.modules.failed = c.id
		out.modules.checkpoint = c.checkpoint
	return discover(out)
func actions(runtime, st: Dictionary, base: Array, abstract := false) -> Array:
	if not runtime.endings(st).is_empty(): return []
	var out := []
	var ms: Dictionary = st.modules
	if ms.active != "":
		out.append(runtime.action_record("challenge:abort:" + ms.active, "Abort " + ms.active, outcome(st, false), "", "abort"))
		if abstract:
			out.append(runtime.action_record("assume:complete:" + ms.active, "Analysis only", outcome(st, true)))
			out.append(runtime.action_record("assume:fail:" + ms.active, "Analysis only", outcome(st, false)))
	elif ms.failed != "":
		var next := st.duplicate(true)
		next.modules.failed = ""
		out.append(runtime.action_record("challenge:retry:" + ms.failed, "Retry", next, "", "retry"))
	else:
		for a in base:
			var b: Dictionary = a.duplicate(true)
			b.state = discover(b.state)
			out.append(b)
		if st.dialogue.values().all(func(x): return x == ""):
			for id in challenges:
				var c: Dictionary = challenges[id]
				if ms.completed.has(id) or st.location != c.room or not runtime.matches(c.conditions, st): continue
				var next := st.duplicate(true)
				next.modules.active = id
				next.modules.checkpoint = c.checkpoint
				out.append(runtime.action_record("challenge:start:" + id, "Start " + id, next, "", "challenge"))
			for id in checkpoints:
				if checkpoints[id].room != st.location: continue
				var next := st.duplicate(true)
				next.modules.checkpoint = id
				out.append(runtime.action_record("checkpoint:" + id, "Checkpoint", next, "", "checkpoint"))
	out.sort_custom(func(a, b): return a.id < b.id)
	return out
func analysis_actions(runtime, st: Dictionary) -> Array:
	return actions(runtime, st, runtime.core_actions(st), true)
