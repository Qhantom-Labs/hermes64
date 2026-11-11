extends SceneTree
## Strict movie verification + disk checkpoint round-trip; never inject outcomes.
const View = preload("res://playtest/module_view.gd")
const Wire = preload("res://core/wire.gd")
const Codec = preload("res://core/save_codec.gd")
var view
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var config: Dictionary = Wire.read_json("res://author-replay-config.json")
	view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack":"res://theme.json", "bindings":"res://bindings.json"})
	var value := {"ok":false,"save_round_trip":false,"movie":{},"endings":[],"game_hash":""}
	if booted.ok:
		value.game_hash = view.runtime.game.game_hash
		view.actions.configure({"version":1})
		view.actions.set_source("bot")
		# The initial ready checkpoint is a legal save, never a mid-attempt resume.
		var codec = Codec.new()
		var saved: Dictionary = codec.pack(view.runtime)
		var f := FileAccess.open(config.save, FileAccess.WRITE)
		if f != null:
			f.store_string(JSON.stringify(saved)); f.close()
			var loaded: Dictionary = codec.load_into(view.runtime, Wire.read_json(config.save))
			value.save_round_trip = loaded.get("ok", false) and codec.pack(view.runtime) == saved
		var opened: Dictionary = view.replay.load_movie(config.movie, false)
		if opened.ok:
			var source: Dictionary = Wire.read_json(config.movie)
			for i in source.frames.size()+30:
				await physics_frame
				await process_frame
				if view.replay.finished: break
			value.movie = view.replay.result
			value.endings = view.runtime.endings(view.runtime.state)
			value.ok = view.replay.finished and value.movie.get("ok", false) and value.save_round_trip
		else:
			value.movie = opened
	var out := FileAccess.open(config.report, FileAccess.WRITE)
	if out != null:
		out.store_string(JSON.stringify(value)); out.close()
	print("AUTHOR_REPLAY ", JSON.stringify(value))
	await view.quit_cleanly(0 if value.ok else 1)
