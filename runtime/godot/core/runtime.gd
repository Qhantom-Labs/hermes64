extends RefCounted
## Pure contract transition system. No Nodes, input, clocks, filesystem or rendering.
## The compiler owns full source validation; configure accepts compiled dictionaries.
var game: Dictionary = {}
var state: Dictionary = {}
var rooms: Dictionary = {}
var characters: Dictionary = {}
var dialogues: Dictionary = {}
var nodes: Dictionary = {}
var local: Dictionary = {}
var collections: Dictionary = {}
var tide_indices: Dictionary = {}
var modules

func configure(data: Dictionary) -> Dictionary:
	if data.get("contract_version") not in ["1.0.0", "1.1.0", "1.2.0"]:
		return {"ok": false, "reason": "unsupported contract version"}
	for key in ["start", "rooms", "characters", "items", "flags", "interactions", "dialogues", "tide", "quests", "endings", "spec_hash", "game_hash"]:
		if not data.has(key):
			return {"ok": false, "reason": "missing game field: " + key}
	if data.contract_version in ["1.1.0", "1.2.0"] and (not data.has("collectibles") or not data.has("collectible_groups") or not data.start.has("collected")):
		return {"ok": false, "reason": "missing collection fields"}
	modules = null
	if data.contract_version == "1.2.0":
		modules = preload("res://core/module_runtime.gd").new()
		var checked: Dictionary = modules.configure(data)
		if not checked.ok: return checked
	game = data.duplicate(true)
	rooms = index_by_id(game.rooms)
	characters = index_by_id(game.characters)
	dialogues = index_by_id(game.dialogues)
	collections = index_by_id(game.get("collectibles", []))
	nodes = {}
	local = {}
	tide_indices = {}
	for did in dialogues:
		nodes[did] = index_by_id(dialogues[did].nodes)
	for rid in rooms:
		local[rid] = []
	for interaction in game.interactions:
		local[interaction.room].append(interaction)
	for i in game.tide.states.size():
		tide_indices[game.tide.states[i].id] = i
	state = game.start.duplicate(true)
	if not valid_dialogue(state):
		return {"ok": false, "reason": "initial active dialogue conditions do not hold"}
	return {"ok": true}

static func index_by_id(values: Array) -> Dictionary:
	var out := {}
	for value in values:
		out[value.id] = value
	return out

func matches(conditions: Array, st: Dictionary) -> bool:
	for c in conditions:
		var ok := false
		if c.has("flag"):
			ok = st.flags[c.flag] == c.equals
		elif c.has("item"):
			ok = st.inventory.has(c.item) == c.present
		elif c.has("location"):
			ok = st.location == c.location
		elif c.has("tide"):
			ok = st.tide.state == c.tide
		elif c.has("role"):
			ok = characters[c.role].role == c.equals
		elif c.has("dialogue"):
			ok = st.dialogue[c.dialogue] == c.node
		elif c.has("ability"):
			ok = st.get("modules", {}).get("abilities", []).has(c.ability)
		elif c.has("challenge"):
			ok = st.get("modules", {}).get("completed", []).has(c.challenge)
		elif c.has("collected"):
			ok = st.get("collected", []).has(c.collected)
		elif c.has("group"):
			var count := 0
			for cid in st.get("collected", []):
				if collections[cid].group == c.group:
					count += 1
			ok = count >= c.at_least
		if not ok:
			return false
	return true

func endings(st: Dictionary) -> Array:
	if modules != null and (st.modules.active != "" or st.modules.failed != ""): return []
	var out := []
	for ending in game.endings:
		if matches(ending.conditions, st):
			out.append(ending.id)
	return out

func valid_dialogue(st: Dictionary) -> bool:
	var active := 0
	for did in st.dialogue:
		var nid: String = st.dialogue[did]
		if nid != "":
			active += 1
			if not nodes.has(did) or not nodes[did].has(nid) or not matches(nodes[did][nid].conditions, st):
				return false
	return active <= 1

func apply_effects(st: Dictionary, effects: Array, cursor: Array = []):
	var out := st.duplicate(true)
	for effect in effects:
		if effect.has("flag"):
			out.flags[effect.flag] = effect.value
		elif effect.has("give"):
			if not out.inventory.has(effect.give):
				out.inventory.append(effect.give)
		elif effect.has("take"):
			if not out.inventory.has(effect.take):
				return null
			out.inventory.erase(effect.take)
		elif effect.has("dialogue"):
			out.dialogue[effect.dialogue] = effect.node
		elif effect.has("location"):
			out.location = effect.location
		elif effect.has("tide"):
			out.tide = {"state": effect.tide, "tick": 0}
		elif effect.has("unlock") and modules != null:
			for dep in modules.abilities[effect.unlock].requires:
				if not out.modules.abilities.has(dep): return null
			if not out.modules.abilities.has(effect.unlock): out.modules.abilities.append(effect.unlock)
			out.modules.abilities.sort()
	if not cursor.is_empty():
		out.dialogue[cursor[0]] = cursor[1]
	out.inventory.sort()
	return out if valid_dialogue(out) else null

func action_record(id: String, label: String, out: Dictionary, text := "", kind := "") -> Dictionary:
	return {"id": id, "label": label, "state": out, "text": text, "kind": kind}

func actions(st: Dictionary) -> Array:
	if modules != null: return modules.actions(self, st, core_actions(st))
	return core_actions(st)

func core_actions(st: Dictionary) -> Array:
	if not endings(st).is_empty():
		return []
	var out := []
	var active := []
	for did in st.dialogue:
		if st.dialogue[did] != "":
			active.append([did, st.dialogue[did]])
	if not active.is_empty():
		var did: String = active[0][0]
		var nid: String = active[0][1]
		var node: Dictionary = nodes[did][nid]
		if matches(node.conditions, st):
			for choice in node.choices:
				if matches(choice.conditions, st):
					var next = apply_effects(st, choice.effects, [did, choice.next])
					if next != null:
						out.append(action_record("choose:%s:%s:%s" % [did, nid, choice.id], choice.text, next, choice.text, "choose"))
		var cancelled := st.duplicate(true)
		cancelled.dialogue[did] = ""
		out.append(action_record("cancel:" + did, "End conversation", cancelled, "", "cancel"))
	else:
		for door in rooms[st.location].doors:
			if matches(door.conditions, st):
				var next := st.duplicate(true)
				next.location = door.to_room
				out.append(action_record("move:%s:%s" % [st.location, door.id], door.label, next, "", "move"))
		for interaction in local[st.location]:
			if matches(interaction.conditions, st):
				var next = apply_effects(st, interaction.effects)
				if next != null:
					out.append(action_record("interact:" + interaction.id, interaction.label, next, interaction.text, interaction.kind))
		for cid in collections:
			var c: Dictionary = collections[cid]
			if c.room != st.location:
				continue
			var found: bool = st.collected.has(cid)
			if (found and c.dialogue == "") or (not found and not matches(c.conditions, st)):
				continue
			var next := st.duplicate(true)
			if not found:
				next.collected.append(cid)
				next.collected.sort()
			if c.dialogue != "":
				next.dialogue[c.dialogue] = dialogues[c.dialogue].start_node
			if valid_dialogue(next):
				var kind := "recall" if found else "collect"
				# Label is presentation only; exact oracle parity covers it separately.
				var label: String = "Recall " + c.get("name", cid) if found else c.label
				out.append(action_record(kind + ":" + cid, label, next, c.text, kind))
	var index: int = tide_indices[st.tide.state]
	var tick: int = int(st.tide.tick) + 1
	if tick >= game.tide.states[index].duration:
		index = (index + 1) % game.tide.states.size()
		tick = 0
	var waited := st.duplicate(true)
	waited.tide = {"state": game.tide.states[index].id, "tick": tick}
	# WAIT intentionally does not validate current node guards, matching the checker.
	out.append(action_record("wait", game.tide.wait_label, waited, game.tide.wait_text, "wait"))
	out.sort_custom(func(a, b): return a.id < b.id)
	return out

func step(action_id: String) -> Dictionary:
	for action in actions(state):
		if action.id == action_id:
			var before := state.duplicate(true)
			state = action.state.duplicate(true)
			return {"ok": true, "action": action_id, "before": before, "state": state.duplicate(true),
				"text": action.text, "endings": endings(state), "ambiguous": endings(state).size() > 1}
	return {"ok": false, "code": "unavailable", "reason": "action %s unavailable at %s" % [action_id, state.location], "endings": endings(state)}

func derived(st: Dictionary) -> Dictionary:
	var counts := {}
	var followers := {}
	var quests := []
	for group in game.get("collectible_groups", []):
		counts[group.id] = 0
	for cid in collections:
		var c: Dictionary = collections[cid]
		var found: bool = st.collected.has(cid)
		if found:
			counts[c.group] += 1
		if c.follower_flag != "":
			followers[c.follower_flag] = found
	for quest in game.quests:
		if matches(quest.conditions, st):
			quests.append(quest.id)
	return {"counts": counts, "follower_flags": followers, "quests": quests}
