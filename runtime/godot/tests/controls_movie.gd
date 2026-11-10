extends SceneTree
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var view
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	if not ResourceLoader.exists("res://input/movie.gd"):
		check(false,"input movie implementation missing"); quit(1); return
	view = View.new(); root.add_child(view)
	view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true})
	view.actions.set_source("bot")
	for i in 5: await physics_frame; await process_frame
	var path := "res://../acceptance.h64movie.json"
	check(view.replay.start_record(path,7).ok,"record opens")
	var recorded_states := {}
	for t in 240:
		var digital := []
		if t < 90: digital.append("move_right")
		if t >= 100 and t < 150: digital.append("move_up"); digital.append("walk")
		if t == 160 or t == 190: digital.append("action_menu")
		if t == 170: digital.append("move_down")
		if t == 180: digital.append("primary")
		if view.room_transition != null and view.room_transition.active(): await view.room_transition.finished
		view.actions.submit_frame({"digital":digital})
		await physics_frame; await process_frame
		if (t+1)%60 == 0: recorded_states[t+1] = view.replay.state()
	check(view.replay.stop_record().ok,"record finishes")
	var movie: Dictionary = Wire.read_json(path)
	check(movie.frames.size() == 240 and movie.hashes.size() >= 4,"per-tick frames and periodic hashes")
	check(movie.header.version == 1 and movie.header.seed == 7 and movie.header.build_hash.length()==64,"versioned hashed header")
	var good: Dictionary = view.replay.validate_movie(movie)
	check(good.ok,"valid movie")
	for field in ["version","game_hash","build_hash","tick_rate"]:
		var bad: Dictionary = movie.duplicate(true); bad.header[field] = -1
		check(not view.replay.validate_movie(bad).ok,"reject header " + field)
	var malformed: Dictionary = movie.duplicate(true); malformed.frames[0] = {"digital":["not_an_action"]}
	check(not view.replay.validate_movie(malformed).ok,"reject invalid input record")
	for field in ["player","actions","belt","checkpoint"]:
		var bad: Dictionary = movie.duplicate(true); bad.header.initial[field] = []
		check(not view.replay.validate_movie(bad).ok,"reject malformed initial " + field)
	var bad_vector: Dictionary = movie.duplicate(true); bad_vector.header.initial.player.position = [0,0]
	check(not view.replay.validate_movie(bad_vector).ok,"reject short position vector")
	var extra_state: Dictionary = movie.duplicate(true); extra_state.header.initial.extensions = {"unknown_module":{}}
	check(not view.replay.validate_movie(extra_state).ok,"refuse unloaded state extension")
	var bad_hash: Dictionary = movie.duplicate(true); bad_hash.hashes[0].hash = "0".repeat(64)
	check(view.replay.begin_playback(bad_hash,false).ok,"mismatch fixture starts")
	for i in 1000:
		await physics_frame; await process_frame
		if view.replay.finished: break
	check(not view.replay.result.ok and view.replay.result.has("tick"),"state mismatch reports first divergent checkpoint")
	var results := []
	for run_index in 2:
		check(view.replay.begin_playback(movie,false).ok,"playback starts")
		for i in 1000:
			await physics_frame; await process_frame
			if view.replay.finished: break
		results.append(view.replay.result.duplicate(true))
		if not view.replay.result.ok:
			var current: Dictionary = view.replay.state()
			var expected: Dictionary = recorded_states[view.replay.result.tick]
			for k in current:
				if current[k] != expected[k]: print("STATE DIFF ",k," expected=",expected[k]," actual=",current[k])
		check(view.replay.result.ok,"playback recorded hashes match " + str(view.replay.result))
	check(results[0] == results[1],"two playback hashes identical")
	print("CONTROLS REPLAY ",JSON.stringify({"failures":failures,"results":results,"path":ProjectSettings.globalize_path(path)}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
