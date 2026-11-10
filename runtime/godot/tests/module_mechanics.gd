extends SceneTree
var failures := []
var checks := 0
func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	# Wiring RED first, before preloading absent classes; behavior checks run once present.
	for file in ["input_adapter", "combat/runtime", "course/runtime", "regions/runtime", "host"]:
		expect(FileAccess.file_exists("res://modules/" + file + ".gd"), file + " implemented")
	if failures.is_empty():
		var adapter = load("res://modules/input_adapter.gd").new()
		adapter.inject(Vector2(2, 2), ["primary", "focus"])
		expect(adapter.get_move().length() <= 1.001 and adapter.just_pressed("primary"), "stub clamps move and edges")
		adapter.clear()
		expect(not adapter.just_pressed("primary") and adapter.get_move() == Vector2.ZERO, "boundary flush")
		var course = load("res://modules/course/runtime.gd").new()
		var track := {"start_position_m": [0,0,0], "countdown_ticks": 2, "time_limit_ticks": 120, "par_ticks": 30, "checkpoints": [{"id":"a","position_m":[1,0,0],"radius_m":0.2},{"id":"b","position_m":[2,0,0],"radius_m":0.2}]}
		course.begin(track, 12.0)
		course.tick(Vector3.ZERO, Vector3.ZERO, true)
		expect(course.countdown == 2 and course.elapsed == 0, "paused countdown frozen")
		course.tick(Vector3.ZERO, Vector3.ZERO)
		course.tick(Vector3.ZERO, Vector3.ZERO)
		expect(course.elapsed == 0 and course.countdown == 0, "countdown exact boundary")
		# Native sphere sweep cannot authorize a teleport larger than admitted speed.
		course.tick(Vector3.ZERO, Vector3(2,0,0))
		expect(course.history.is_empty(), "teleport shortcut gets no credit")
		expect(course.result == "failed", "teleport invalidates entire run, not just one segment")
		course.begin(track,12.0)
		course.countdown = 0
		for i in 11: course.tick(Vector3(i * 0.2,0,0), Vector3((i+1)*0.2,0,0))
		expect(course.history == ["a", "b"] and course.result == "completed", "ordered swept course succeeds")
		course.begin(track, 12.0)
		for i in 123: course.tick(Vector3.ZERO, Vector3.ZERO)
		expect(course.result == "failed", "deadline fails unreachable checkpoint")
		var Combat = load("res://modules/combat/runtime.gd")
		expect(not Combat.window(7, 8, 4) and Combat.window(8, 8, 4) and Combat.window(11, 8, 4) and not Combat.window(12, 8, 4), "half-open hit window")
		expect(Combat.iframe(14) and not Combat.iframe(15), "half-open dodge window")
		var r = load("res://core/runtime.gd").new()
		var vectors = load("res://core/wire.gd").read_json("res://module-vectors.json")
		r.configure(vectors[3].game)
		var regions = load("res://modules/regions/runtime.gd").new()
		regions.configure(r)
		expect(not regions.eligible("move:hub:to_arena", Vector3.ZERO, Vector3.ZERO), "ability gate blocks physical portal")
		r.step("interact:learn")
		expect(not regions.eligible("move:hub:to_arena", Vector3.ZERO, Vector3(8,0,8)), "remote portal refused")
		expect(regions.eligible("move:hub:to_arena", Vector3.ZERO, Vector3.ZERO), "ability and proximity permit portal")
	print("MODULE_MECHANICS checks=%d failures=%d" % [checks, failures.size()])
	for f in failures: print("FAIL ", f)
	quit(0 if failures.is_empty() else 1)
