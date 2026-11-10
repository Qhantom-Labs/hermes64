extends "res://tests/checker_replay.gd"
## Normalized plugin seam: checker proof -> same gameplay core + real disk save/load.
const SaveCodec = preload("res://core/save_codec.gd")
var destination := ""
var ending_results := {}
var save_results := []
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var options := {}
	for i in range(0, args.size() - 1, 2): options[args[i].trim_prefix("--")] = args[i+1]
	if not options.has_all(["game", "proof", "report"]):
		quit(2)
		return
	destination = options.report
	var parsed = Wire.read_json(options.game)
	var proof = Wire.read_json(options.proof)
	if not parsed is Dictionary or not proof is Dictionary or proof.get("status") != "proved" or proof.get("game_hash", "") != parsed.get("game_hash", "missing"):
		quit(2)
		return
	game = parsed
	visit(proof, "")
	var ok: bool = failed == 0 and count > 0 and ending_results.size() == game.endings.size()
	var imported := {"status":"not_requested"}
	if options.has("save"):
		var restored_runtime = Runtime.new()
		restored_runtime.configure(game)
		imported = SaveCodec.new().load_into(restored_runtime,Wire.read_json(options.save))
		ok = ok and imported.get("ok",false)
	var result := {"imported_save":imported,"status": "passed" if ok else "failed", "game_hash": game.game_hash, "endings": ending_results, "save_round_trip": ok and not save_results.is_empty(), "saves": save_results, "witnesses": count, "steps": steps, "failures": failed}
	var f := FileAccess.open(destination, FileAccess.WRITE)
	if f == null:
		quit(2)
		return
	f.store_string(JSON.stringify(result, "\t", true))
	f.close()
	print("PLUGIN REPLAY witnesses=%d steps=%d failures=%d saves=%d" % [count, steps, failed, save_results.size()])
	quit(0 if ok else 1)
func replay_claim(claim: Dictionary, path: String) -> bool:
	var ok: bool = super.replay_claim(claim, path)
	var runtime = Runtime.new()
	runtime.configure(game)
	for step in claim.witness:
		if not runtime.step(step.action).ok: ok = false
	var codec = SaveCodec.new()
	var file_path := destination.get_base_dir().path_join("save-" + str(save_results.size()) + ".json")
	var f := FileAccess.open(file_path, FileAccess.WRITE)
	if f == null: return false
	f.store_string(JSON.stringify(codec.pack(runtime), "\t", true))
	f.close()
	var fresh = Runtime.new()
	fresh.configure(game)
	var restored: Dictionary = codec.load_into(fresh, Wire.read_json(file_path))
	var equal: bool = restored.ok and fresh.state == runtime.state
	ok = ok and equal
	save_results.append({"claim": path, "path": file_path.get_file(), "ok": equal})
	if path.begins_with("/endings/"):
		ending_results[path.trim_prefix("/endings/")] = {"status": "passed" if ok else "failed", "steps": claim.witness.size()}
	return ok
