extends SceneTree
const Runtime = preload("res://core/runtime.gd")
const Codec = preload("res://core/save_codec.gd")
const Wire = preload("res://core/wire.gd")
var checks := 0
var failures := []
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures.append(message)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	for vector in Wire.read_json("res://module-vectors.json"):
		var r = Runtime.new()
		var configured: Dictionary = r.configure(vector.game)
		expect(configured.ok, vector.kind + " STORY 1.2 configuration admitted")
		if not configured.ok: continue
		for row in vector.rows:
			var actual: Array = r.modules.analysis_actions(r, row.state)
			var pairs := []
			for a in actual: pairs.append({"id": a.id, "state": a.state})
			if pairs != row.actions and failures.size() < 3: print("PARITY expected=", JSON.stringify(row.actions), " actual=", JSON.stringify(pairs))
			expect(pairs == row.actions, vector.kind + " complete abstract transition parity " + JSON.stringify(row.state))
			expect(r.endings(row.state) == row.endings, vector.kind + " terminal parity")
			for a in r.actions(row.state): expect(not a.id.begins_with("assume:"), "no assumptions exposed")
		var codec = Codec.new()
		expect(codec.load_into(r, vector.save).ok, "Python checkpoint loads")
		expect(codec.pack(r) == vector.save, "checkpoint wire roundtrip")
		var old: Dictionary = r.state.duplicate(true)
		var bad: Dictionary = vector.save.duplicate(true)
		bad.game_hash = "stale"
		expect(not codec.load_into(r, bad).ok and r.state == old, "stale load atomic")
		bad = vector.save.duplicate(true)
		bad.state.modules.completed = ["unknown"]
		expect(not codec.load_into(r, bad).ok and r.state == old, "unknown completion rejected")
		bad = vector.save.duplicate(true)
		bad.state["velocity"] = [1, 2, 3]
		expect(not codec.load_into(r, bad).ok, "transient save fields rejected")
		for row in vector.rows:
			if row.state.modules.active != "" or row.state.modules.failed != "":
				r.state = row.state.duplicate(true)
				expect(codec.pack(r).get("ok") == false, "active/failed saves rejected")
				break
		expect(not r.step("assume:complete:gate_trial").ok, "no live completion injection")
	print("MODULE_PARITY checks=%d failures=%d" % [checks, failures.size()])
	for f in failures.slice(0, 12): print("FAIL ", f)
	quit(0 if failures.is_empty() else 1)
