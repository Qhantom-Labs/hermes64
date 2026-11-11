extends Node
const Wire = preload("res://core/wire.gd")
const Runtime = preload("res://core/runtime.gd")
const SaveCodec = preload("res://core/save_codec.gd")
var rooms := {}
var shots := []
var failures := []
var frame_deltas := []
var prior_usec := 0

func _process(_delta: float) -> void:
	var now := Time.get_ticks_usec()
	if prior_usec != 0: frame_deltas.append((now - prior_usec) / 1000.0)
	prior_usec = now

func pause_frames(count: int) -> void:
	for i in count: await get_tree().process_frame

func room_capture(view, directory: String) -> void:
	var rid: String = view.runtime.state.location
	if rooms.has(rid): return
	await pause_frames(4)
	var path := directory.path_join("room-" + rid + ".png")
	var captured: bool = await view.capture(path)
	rooms[rid] = captured
	if captured: shots.append(path)
	elif DisplayServer.get_name() != "headless": failures.append("capture failed " + rid)

func run(view, replay_path: String, directory: String) -> void:
	var started := Time.get_ticks_usec()
	var replay = Wire.read_json(replay_path)
	if not replay is Dictionary or replay.game_hash != view.runtime.game.game_hash:
		print("BOT ERROR: replay provenance mismatch")
		await view.quit_cleanly(2)
		return
	await pause_frames(20)
	var steps := 0
	var endings := []
	var roundtrips := []
	for trace in replay.traces:
		view.runtime.configure(view.runtime.game)
		view.enter_room("")
		view.last_text = view.boxed(view.runtime.rooms[view.runtime.state.location].description)
		view.refresh()
		await room_capture(view, directory)
		for step in trace.steps:
			if view.runtime.state != step.before: failures.append(trace.name + " before mismatch")
			var result: Dictionary = view.dispatch(step.action)
			if not result.ok or view.runtime.state != step.after: failures.append(trace.name + " action mismatch " + step.action)
			steps += 1
			await pause_frames(2)
			await room_capture(view, directory)
		if view.runtime.endings(view.runtime.state) != trace.terminal: failures.append(trace.name + " ending mismatch")
		var packed: Dictionary = view.codec.pack(view.runtime)
		DirAccess.make_dir_recursive_absolute(directory.path_join("saves"))
		var save_file_path: String = directory.path_join("saves").path_join(trace.name.replace("/", "_") + ".json")
		var save_file := FileAccess.open(save_file_path, FileAccess.WRITE)
		save_file.store_string(JSON.stringify(packed, "	", true))
		save_file.close()
		var fresh = Runtime.new()
		fresh.configure(view.runtime.game)
		var codec = SaveCodec.new()
		var restored: Dictionary = codec.load_into(fresh, Wire.read_json(save_file_path))
		var ok: bool = restored.ok and fresh.state == view.runtime.state
		roundtrips.append({"trace": trace.name, "ok": ok, "explored": restored.get("explored", 0), "reason": restored.get("reason", "")})
		if not ok: failures.append(trace.name + " save roundtrip " + str(restored))
		if trace.ending != "":
			endings.append(trace.ending)
			await pause_frames(4)
			var path := directory.path_join("ending-" + trace.ending + ".png")
			if await view.capture(path): shots.append(path)
		print("BOT TRACE ", trace.name, " steps=", trace.steps.size(), " roundtrip=", ok, " explored=", restored.get("explored", 0))
	frame_deltas.sort()
	var total := 0.0
	for value in frame_deltas: total += value
	var metrics := {"samples": frame_deltas.size()}
	if not frame_deltas.is_empty():
		metrics.merge({"mean_ms": total / frame_deltas.size(), "median_ms": frame_deltas[frame_deltas.size() / 2], "p95_ms": frame_deltas[int(frame_deltas.size() * 0.95)], "max_ms": frame_deltas[-1]})
	var report := {"game_hash": replay.game_hash, "witnesses": replay.traces.size(), "steps": steps, "endings": endings,
		"rooms": rooms, "shots": shots, "roundtrips": roundtrips, "failures": failures,
		"elapsed_ms": (Time.get_ticks_usec() - started) / 1000.0, "frame_intervals": metrics,
		"room_build_ms": view.build_samples, "missing_assets": view.resolver.missing.keys(), "loaded_assets": view.resolver.loaded,
		"display": DisplayServer.get_name(), "renderer": RenderingServer.get_current_rendering_method(), "adapter": RenderingServer.get_video_adapter_name()}
	DirAccess.make_dir_recursive_absolute(directory)
	var file := FileAccess.open(directory.path_join("bot-result.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "\t"))
	file.close()
	print("BOT SUMMARY witnesses=%d steps=%d endings=%s rooms=%d screenshots=%d failures=%d frame_intervals=%s" % [replay.traces.size(), steps, str(endings), rooms.size(), shots.size(), failures.size(), str(metrics)])
	await view.quit_cleanly(0 if failures.is_empty() else 1)
