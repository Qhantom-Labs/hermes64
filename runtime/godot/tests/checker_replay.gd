extends SceneTree
const Runtime = preload("res://core/runtime.gd")
const Wire = preload("res://core/wire.gd")
var game: Dictionary
var count := 0
var steps := 0
var failed := 0
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		print("Usage: checker_replay.gd -- /absolute/game.json /absolute/check.json")
		quit(2)
		return
	var parsed = Wire.read_json(args[0])
	var report = Wire.read_json(args[1])
	if not parsed is Dictionary or not report is Dictionary or report.get("game_hash", "") != parsed.game_hash:
		print("CHECKER REPLAY ERROR: missing input or report/game provenance mismatch")
		quit(2)
		return
	game = parsed
	visit(report, "")
	print("RAW CHECKER SUMMARY witnesses=%d steps=%d failures=%d" % [count, steps, failed])
	quit(0 if failed == 0 and count > 0 else 1)
func visit(value, path: String) -> void:
	if value is Dictionary:
		if value.has("witness") and value.witness is Array:
			count += 1
			if not replay_claim(value, path): failed += 1
		for key in value:
			if key != "witness": visit(value[key], path + "/" + str(key))
	elif value is Array:
		for i in value.size(): visit(value[i], path + "/" + str(i))
func replay_claim(claim: Dictionary, path: String) -> bool:
	var runtime = Runtime.new()
	if not runtime.configure(game).ok: return false
	for witness in claim.witness:
		var found := false
		for action in runtime.actions(runtime.state):
			if action.id == witness.action:
				found = action.label == witness.label
		if not found:
			print("FAIL unavailable action/label ", path, " ", witness.action)
			return false
		var result: Dictionary = runtime.step(witness.action)
		steps += 1
		if not result.ok or runtime.state.location != witness.location or runtime.state.tide != witness.tide:
			print("FAIL checker projection/effects ", path, " ", witness.action)
			return false
	if claim.has("final_state") and runtime.state != claim.final_state:
		print("FAIL full final state ", path)
		return false
	if path.begins_with("/endings/"):
		var ending := path.trim_prefix("/endings/")
		if runtime.endings(runtime.state) != [ending]:
			print("FAIL ending claim ", path)
			return false
	if path.begins_with("/collectibles/"):
		if not runtime.state.collected.has(path.trim_prefix("/collectibles/")):
			print("FAIL collection claim ", path)
			return false
	print("RAW REPLAY ", path, " actions=", claim.witness.size(), " terminal=", runtime.endings(runtime.state))
	return true
