extends SceneTree
const Runtime = preload("res://core/runtime.gd")
var passed := 0
var failed := 0

func expect(ok: bool, label: String) -> void:
	if ok:
		passed += 1
		print("PASS ", label)
	else:
		failed += 1
		print("FAIL ", label)

func fixture() -> Dictionary:
	return {
		"contract_version": "1.1.0", "id": "unit", "title": "Unit", "metadata": {},
		"spec_hash": "a".repeat(64), "game_hash": "b".repeat(64),
		"start": {"location": "a", "inventory": [], "flags": {"gate": false, "end": false},
			"dialogue": {"d": "", "e": ""}, "tide": {"state": "calm", "tick": 0}, "collected": []},
		"rooms": [{"id": "a", "doors": [{"id": "east", "to_room": "b", "label": "Go", "conditions": [{"flag": "gate", "equals": true}]}]}, {"id": "b", "doors": []}],
		"characters": [{"id": "host", "role": "friend"}], "items": [{"id": "key"}],
		"flags": [{"id": "gate", "initial": false}, {"id": "end", "initial": false}],
		"interactions": [
			{"id": "get", "room": "a", "kind": "take", "label": "Get", "text": "A key.", "conditions": [], "effects": [{"give": "key"}]},
			{"id": "unlock", "room": "a", "kind": "use", "label": "Unlock", "text": "Open.", "conditions": [], "effects": [{"flag": "gate", "value": true}, {"take": "key"}]},
			{"id": "talk", "room": "a", "kind": "talk", "label": "Talk", "text": "Hello", "conditions": [], "effects": [{"dialogue": "d", "node": "hello"}]},
			{"id": "finish", "room": "b", "kind": "use", "label": "End", "text": "Done.", "conditions": [{"group": "cats", "at_least": 1}], "effects": [{"flag": "end", "value": true}]}
		],
		"dialogues": [{"id": "d", "start_node": "hello", "nodes": [
			{"id": "hello", "text": "Hello", "conditions": [], "choices": [
				{"id": "bad", "text": "Bad", "conditions": [], "effects": [{"flag": "gate", "value": true}], "next": "locked"},
				{"id": "bye", "text": "Bye", "conditions": [], "effects": [{"dialogue": "d", "node": "hello"}], "next": ""}]},
			{"id": "locked", "text": "Locked", "conditions": [{"item": "key", "present": true}], "choices": []}]},
			{"id": "e", "start_node": "cat", "nodes": [{"id": "cat", "text": "Purr", "conditions": [{"collected": "cat"}], "choices": []}]}],
		"tide": {"states": [{"id": "calm", "label": "Calm", "duration": 2}, {"id": "storm", "label": "Storm", "duration": 1}], "wait_label": "Wait", "wait_text": "Time passes."},
		"collectible_groups": [{"id": "cats", "required": 1}],
		"collectibles": [{"id": "cat", "group": "cats", "room": "a", "label": "Pet", "text": "Found", "dialogue": "e", "follower_flag": "cat_follows", "conditions": []}],
		"quests": [{"id": "friends", "conditions": [{"group": "cats", "at_least": 1}]}],
		"endings": [{"id": "done", "conditions": [{"flag": "end", "equals": true}], "text": "Done"}]
	}

func fresh():
	var r = Runtime.new()
	r.configure(fixture())
	return r

func _initialize() -> void:
	var r = fresh()
	expect(r.matches([], r.state), "empty conjunction true")
	expect(r.matches([{"flag": "gate", "equals": false}, {"item": "key", "present": false}, {"location": "a"}, {"tide": "calm"}, {"role": "host", "equals": "friend"}, {"dialogue": "d", "node": ""}], r.state), "all six base predicate forms")
	expect(not r.matches([{"location": "b"}], r.state), "CONTROL false predicate rejects")
	var before = r.state.duplicate(true)
	expect(not r.step("interact:unlock").ok and r.state == before, "CONTROL missing take is atomic rejection")
	expect(r.step("interact:get").ok and r.state.inventory == ["key"], "give puts item into inventory")
	r.step("interact:get")
	expect(r.state.inventory == ["key"], "give idempotent")
	expect(r.step("interact:unlock").ok and r.state.flags.gate and r.state.inventory.is_empty(), "ordered take and flag commit")
	expect(r.step("move:a:east").ok and r.state.location == "b", "guarded door changes room")
	expect(r.state.tide == before.tide, "CONTROL non-wait pauses timer")
	r = fresh()
	expect(r.step("interact:talk").ok and r.state.dialogue.d == "hello", "talk opens graph")
	expect(not r.step("interact:get").ok, "CONTROL dialogue blocks room interaction")
	before = r.state.duplicate(true)
	expect(not r.step("choose:d:hello:bad").ok and before == r.state, "CONTROL destination guard rolls effects back")
	expect(r.step("choose:d:hello:bye").ok and r.state.dialogue.d == "", "choice next overrides effect cursor")
	r.step("interact:talk")
	expect(r.step("cancel:d").ok and r.state.dialogue.d == "", "cancel clears cursor")
	r = fresh()
	r.step("wait")
	expect(r.state.tide == {"state": "calm", "tick": 1}, "wait increments tick")
	r.step("wait")
	expect(r.state.tide == {"state": "storm", "tick": 0}, "wait crosses duration")
	r.step("wait")
	expect(r.state.tide == {"state": "calm", "tick": 0}, "cyclic wait wraps")
	expect(r.step("collect:cat").ok and r.state.collected == ["cat"] and r.state.dialogue.e == "cat", "collect and vignette atomic against resulting membership")
	r.step("cancel:e")
	expect(not r.step("collect:cat").ok, "CONTROL duplicate collect denied")
	expect(r.step("recall:cat").ok and r.state.collected == ["cat"], "recall no duplicate credit")
	var view = r.derived(r.state)
	expect(view.counts.get("cats") == 1 and view.follower_flags.get("cat_follows") == true and not r.state.flags.has("cat_follows"), "derived counters and followers separate from flags")
	expect(view.quests == ["friends"], "quests derived from group predicates")
	r.step("cancel:e")
	r.step("interact:get")
	r.step("interact:unlock")
	r.step("move:a:east")
	expect(r.step("interact:finish").ok and r.endings(r.state) == ["done"], "ending evaluated after action")
	expect(r.actions(r.state).is_empty() and not r.step("wait").ok, "CONTROL terminal disables every action")
	var g = fixture()
	g.contract_version = "9.0.0"
	expect(not r.configure(g).ok, "unsupported version rejected")
	# Additional edge cases and regression controls; label behavior establishes new RED.
	g = fixture()
	g.collectibles[0]["name"] = "Purl"
	r.configure(g)
	r.step("collect:cat")
	r.step("cancel:e")
	var recall_label := ""
	for action in r.actions(r.state):
		if action.id == "recall:cat": recall_label = action.label
	expect(recall_label == "Recall Purl", "reference recall label includes authored name")
	g.collectibles[0].conditions = [{"flag": "gate", "equals": true}]
	r.configure(g)
	r.state.collected = ["cat"]
	expect(r.step("recall:cat").ok, "CONTROL recall ignores discovery guard")
	g = fixture()
	g.dialogues[1].nodes[0].conditions = [{"item": "key", "present": true}]
	r.configure(g)
	before = r.state.duplicate(true)
	expect(not r.step("collect:cat").ok and r.state == before, "CONTROL guarded vignette atomically refuses pickup")
	g = fixture()
	g.interactions[0].effects = [{"give": "key"}, {"take": "key"}, {"tide": "storm"}, {"location": "b"}]
	r.configure(g)
	expect(r.step("interact:get").ok and r.state.inventory.is_empty() and r.state.location == "b" and r.state.tide == {"state": "storm", "tick": 0}, "CONTROL ordered give/take, tide reset, location effects")
	g.interactions[0].effects = [{"take": "key"}, {"give": "key"}]
	r.configure(g)
	before = r.state.duplicate(true)
	expect(not r.step("interact:get").ok and r.state == before, "CONTROL cannot borrow a future give for take")
	g.interactions[0].effects = [{"dialogue": "d", "node": "hello"}, {"dialogue": "e", "node": "cat"}]
	g.dialogues[1].nodes[0].conditions = []
	r.configure(g)
	expect(not r.step("interact:get").ok, "CONTROL two active graphs refused")
	g = fixture()
	g.dialogues[0].nodes[0].conditions = [{"tide": "calm"}]
	r.configure(g)
	r.step("interact:talk")
	r.step("wait")
	r.step("wait")
	expect(r.state.tide.state == "storm" and r.state.dialogue.d == "hello", "CONTROL WAIT can invalidate active node guard")
	expect(not r.step("choose:d:hello:bye").ok and r.step("cancel:d").ok, "CONTROL stale guarded node disables choice but cancel remains")
	g = fixture()
	g.start.flags.end = true
	r.configure(g)
	expect(r.endings(r.state) == ["done"] and r.actions(r.state).is_empty(), "CONTROL initial terminal disables actions")
	g.endings.append({"id": "other", "conditions": [], "text": "Other"})
	r.configure(g)
	expect(r.endings(r.state).size() == 2 and not r.step("wait").ok, "CONTROL ambiguous terminals never silently select")
	g = fixture()
	g.contract_version = "1.0.0"
	g.erase("collectibles")
	g.erase("collectible_groups")
	g.start.erase("collected")
	g.interactions[3].conditions = []
	g.quests = []
	r.configure(g)
	expect(not r.state.has("collected") and r.step("wait").ok, "CONTROL 1.0.0 retains original state keys")
	print("UNIT SUMMARY passed=%d failed=%d" % [passed, failed])
	quit(0 if failed == 0 else 1)
