extends SceneTree
const Host = preload("res://modules/host.gd")
var checks := 0
var failures := []
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)
func _initialize() -> void:
	var game: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://module-vectors.json"))[0].game
	game.gameplay.api_version = "1.2.0"
	for m in game.gameplay.modules: m.version = "1.2.0"
	var runtime = preload("res://core/runtime.gd").new()
	expect(runtime.configure(game).ok, "production runtime admits registered gameplay 1.2.0")
	var h = Host.new()
	expect(h.get("run") != null, "host exposes run authority")
	if h.get("run") != null:
		var r = h.run
		r.configure({"death_penalty_ticks":600})
		r.advance(false); expect(r.ticks == 0, "idle before first control is outside clock")
		r.advance(true); expect(r.ticks == 1, "first control starts integer clock")
		r.died(); expect(r.deaths == 1 and r.ticks == 601, "death adds exactly 600")
		for t in 60: r.advance(false)
		expect(r.ticks == 661, "retry countdown stays on clock")
		var data: Dictionary = r.snapshot(); r.advance(false); r.restore(data)
		expect(r.snapshot() == data, "run snapshot round trip")
		r.finish(); r.advance(true)
		expect(r.finished_tick == 661 and r.ticks == 661, "finish freezes exact final tick")
		r.configure({}); r.advance(true, true); expect(r.ticks == 0, "cutscene pause does not start clock")
		r.checkpoint(); expect(r.checkpoint_flash == 90, "checkpoint has three-blink 90 tick cue")
	h.free()
	var report := {"checks":checks,"failures":failures}
	var args := OS.get_cmdline_user_args(); var i := args.find("--report")
	if i >= 0: var f = FileAccess.open(args[i+1], FileAccess.WRITE); f.store_string(JSON.stringify(report,"  "))
	print("COMBAT2_RUN ", JSON.stringify(report)); quit(0 if failures.is_empty() else 1)
