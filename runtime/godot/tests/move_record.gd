extends SceneTree
## MOVE: record a LIVE production movie (real key + mouse-orbit events) so frames
## carry the recorded view heading, then the Python driver replays it strictly
## at 30/60/144. Proves camera-relative movement is replay-deterministic.
var view
var output := ""

func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--output="): output = arg.trim_prefix("--output=")
	call_deferred("run")

func key(code: int, down: bool) -> void:
	var e := InputEventKey.new(); e.physical_keycode = code; e.keycode = code; e.pressed = down
	Input.parse_input_event(e)

func mouse(down: bool) -> void:
	var e := InputEventMouseButton.new(); e.button_index = MOUSE_BUTTON_LEFT; e.pressed = down; e.position = Vector2(400,300)
	Input.parse_input_event(e)

func drag(v: Vector2) -> void:
	var e := InputEventMouseMotion.new(); e.position = Vector2(400,300); e.relative = v; e.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(e)

func ticks(n: int) -> void:
	for i in n: await physics_frame

func run() -> void:
	view = load("res://main.tscn").instantiate(); root.add_child(view)
	await ticks(30)
	for i in 40:
		if view.actions.context == "gameplay" and not view.n64_ui.dlg_on: break
		key(KEY_ENTER,true); await ticks(3); key(KEY_ENTER,false); await ticks(6)
	var movie := output.get_base_dir().path_join("live.h64movie.json")
	var started: Dictionary = view.replay.start_record(movie,7)
	if not started.ok:
		print("MOVE_RECORD ",JSON.stringify({"ok":false,"reason":started})); quit(2); return
	key(KEY_W,true); await ticks(60)
	mouse(true)
	for i in 50:
		drag(Vector2(30,0)); await ticks(1)
	mouse(false)
	await ticks(40); key(KEY_W,false)
	key(KEY_S,true); await ticks(120)
	key(KEY_A,true); await ticks(40); key(KEY_A,false)
	key(KEY_V,true); await ticks(2); key(KEY_V,false); await ticks(90)
	key(KEY_S,false); key(KEY_L,true); key(KEY_D,true); await ticks(90); key(KEY_L,false); key(KEY_D,false)
	await ticks(20)
	var stopped: Dictionary = view.replay.stop_record()
	var data = JSON.parse_string(FileAccess.get_file_as_string(movie))
	var with_heading := 0; var orbit_frames := 0
	for f in data.frames:
		if f.has("heading"):
			with_heading += 1
			if int(f.heading[1]) == 1: orbit_frames += 1
	var report := {"ok":stopped.get("ok",false) and with_heading == data.frames.size() and orbit_frames > 0,"movie":movie,"ticks":data.frames.size(),"hashes":data.hashes.size(),"frames_with_heading":with_heading,"orbit_frames":orbit_frames}
	print("MOVE_RECORD ",JSON.stringify(report))
	var f := FileAccess.open(output,FileAccess.WRITE); f.store_string(JSON.stringify(report,"  ")); f.close()
	view.queue_free()
	await ticks(3)
	quit(0 if report.ok else 3)
