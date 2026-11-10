extends SceneTree
const Runtime = preload("res://core/runtime.gd")
const Wire = preload("res://core/wire.gd")
const SaveCodec = preload("res://core/save_codec.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func manual_save(r) -> Dictionary:
	var save: Dictionary = r.state.duplicate(true)
	for key in ["contract_version", "spec_hash", "game_hash"]:
		save[key] = r.game[key]
	return save
func _initialize() -> void:
	var source := ProjectSettings.globalize_path("res://../evidence/last-light-1/game.json")
	var game: Dictionary = Wire.read_json(source)
	var r = Runtime.new()
	r.configure(game)
	var codec = SaveCodec.new()
	expect(codec.pack(r) == manual_save(r), "state-only save exact 1.0.0 keys and hashes")
	var initial = manual_save(r)
	r.step("move:fog_street:boathouse_path")
	r.step("interact:take_oil")
	r.step("wait")
	var midgame = manual_save(r)
	r.configure(game)
	var loaded = codec.load_into(r, midgame)
	expect(loaded.ok and r.state.inventory == ["oil"] and r.state.location == "boathouse" and r.state.tide.tick == 1, "load verifies reachable midgame state")
	var save: Dictionary = codec.pack(r)
	var path := ProjectSettings.globalize_path("res://../evidence/roundtrip.json")
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string(JSON.stringify(save))
	f.close()
	var r2 = Runtime.new()
	r2.configure(game)
	expect(codec.load_into(r2, Wire.read_json(path)).ok and r2.state == r.state and save == codec.pack(r2), "disk save/load round trip into fresh runtime")
	for label in ["hash", "unknown", "duplicate", "tick", "type", "extra", "unreachable"]:
		var bad: Dictionary = initial.duplicate(true)
		match label:
			"hash": bad.game_hash = "c".repeat(64)
			"unknown": bad.inventory = ["nothing"]
			"duplicate": bad.inventory = ["oil", "oil"]
			"tick": bad.tide.tick = 99
			"type": bad.flags.clue = 1
			"extra": bad.position = [1, 2, 3]
			"unreachable": bad.flags.figure_seen = true
		var before: Dictionary = r.state.duplicate(true)
		var refusal = codec.load_into(r, bad)
		expect(not refusal.ok and r.state == before, "CONTROL reject " + label + " without changing session")
	var cap = codec.load_into(r, midgame, 1)
	expect(not cap.ok and cap.get("status") == "inconclusive", "membership resource limit is inconclusive")
	var data: Dictionary = Wire.read_json(ProjectSettings.globalize_path("res://../evidence/last-light-1/replays.json"))
	var end = initial.duplicate(true)
	end.merge(data.traces[0].final, true)
	expect(codec.load_into(r, end).ok and r.endings(r.state) == ["leave_dark"], "terminal state save accepted by membership")
	var wrong = midgame.duplicate(true)
	wrong.contract_version = "1.1.0"
	wrong.collected = []
	expect(not codec.load_into(r, wrong).ok, "CONTROL no silent version upgrade")
	print("SAVE SUMMARY passed=%d failed=%d" % [passed, failed])
	quit(0 if failed == 0 else 1)
