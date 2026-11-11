extends "res://actors/main.gd"
## Crowd capture (ROOF lane): the normal capture_all pipeline (actors/main.gd -> main.gd) with extra combat models
## standing in the room, plus a frame-time probe. Generic: any game, any room, any GLB rows; nothing names a story.
##
##   godot --path RUNTIME res://tests/crowd_capture.tscn -- --game=... --pack=... --bindings=... --screens=DIR \
##         --crowd=crowd.json [--perf_frames=600] [--perf_warmup=120]
##
## crowd.json: {"rooms": {room_id: [{"id","path","sha256","position":[x,y,z],"yaw","scale","lift_m","clip"}]}}
## Extras go through the resolver's enemy_actor() (the same path the combat host uses for robot art) and are
## parented to room_root with meta placed="actor", so the room triangle count and the actor split include them.
## perf.json per room: wall-clock frame intervals (vsync off: pass --disable-vsync), TIME_PROCESS, draw calls,
## primitives in frame and the triangle split. Evidence, not a gameplay replay (no combat simulation runs).
var crowd := {}
var probes := {}
var perf_rows := []

func _ready() -> void:
	var user_args := OS.get_cmdline_user_args()
	for a in user_args:
		if a.begins_with("--crowd="):
			var parsed = Wire.read_json(a.trim_prefix("--crowd="))
			if parsed is Dictionary:
				crowd = parsed.get("rooms", {})
				probes = parsed.get("probes", {})
	await super._ready()

func enter_room(from_action: String) -> void:
	super.enter_room(from_action)
	add_crowd()
	if args.get("hide_people", "0") == "1":     # environment-only frames (no player, actors or crowd drawn)
		player.visible = false
		for n in room_root.get_children():
			if str(n.get_meta("placed", "")) == "actor": n.visible = false

func add_crowd() -> void:
	var rows: Array = crowd.get(runtime.state.location, [])
	for row in rows:
		var actor = resolver.enemy_actor(row) if resolver.has_method("enemy_actor") else null
		if actor == null:
			push_error("crowd: model missing " + str(row.get("id", "")))
			continue
		room_root.add_child(actor)
		actor.name = "crowd_" + str(row.get("label", row.get("id", "x")))
		actor.set_meta("placed", "actor")
		actor.set_meta("crowd", true)
		var p: Array = row.get("position", [0, 0, 0])
		actor.position = Vector3(p[0], float(p[1]) + float(row.get("lift_m", 0.0)), p[2])
		actor.rotation_degrees.y = float(row.get("yaw", 0.0)) + 180.0   # model faces +Z, like the combat host
		var s := float(row.get("scale", 1.0))
		actor.scale = Vector3(s, s, s)
		if actor.has_method("play_clip"): actor.play_clip(str(row.get("clip", "idle_combat")))

func split_counts() -> Dictionary:
	var crowd_tris := 0
	var crowd_n := 0
	var actor_tris := 0
	var actor_n := 0
	for n in room_root.get_children():
		if str(n.get_meta("placed", "")) != "actor" and not n.get_meta("real_character", false): continue
		var t: int = room_root.triangle_count(n)
		if n.get_meta("crowd", false):
			crowd_tris += t; crowd_n += 1
		else:
			actor_tris += t; actor_n += 1
	var total: int = room_root.triangle_count() + room_root.triangle_count(player)
	return {"total": total, "player": room_root.triangle_count(player), "actors": actor_tris, "actor_count": actor_n,
		"crowd": crowd_tris, "crowd_count": crowd_n, "environment": total - room_root.triangle_count(player) - actor_tris - crowd_tris}

## Floor probe points (room x,z at y=0) -> [px, py, camera distance m] in the 320x240 frame of the room camera.
## Used offline to sample the floor under telegraphs in the -clean/-depth passes (tools.telegraph_contrast).
func probe_pixels() -> Array:
	var out := []
	var cam: Camera3D = room_root.camera_nodes[camera_index].node
	for p in probes.get(runtime.state.location, []):
		var w := Vector3(float(p[0]), 0.02, float(p[1]))
		if cam.is_position_behind(w): continue
		if player.visible and Vector2(w.x - player.position.x, w.z - player.position.z).length() < 0.9: continue
		var px: Vector2 = cam.unproject_position(w)
		out.append([snappedf(px.x, 0.1), snappedf(px.y, 0.1), snappedf(cam.global_position.distance_to(w), 0.01), p[0], p[1]])
	return out

static func pct(values: Array) -> Dictionary:
	var v := values.duplicate()
	v.sort()
	var n := v.size()
	if n == 0: return {"p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
	var s := 0.0
	for x in v: s += float(x)
	return {"p50": snappedf(v[n / 2], 0.001), "p90": snappedf(v[int(n * 0.9)], 0.001), "p95": snappedf(v[int(n * 0.95)], 0.001),
		"p99": snappedf(v[mini(n - 1, int(n * 0.99))], 0.001), "max": snappedf(v[n - 1], 0.001), "mean": snappedf(s / n, 0.001)}

func capture_all(folder: String) -> void:
	DirAccess.make_dir_recursive_absolute(folder)
	var frames := int(args.get("perf_frames", "600"))
	var warm := int(args.get("perf_warmup", "120"))
	n64_ui.visible = false
	var low_rid: RID = viewport.get_viewport_rid()
	var win_rid: RID = get_viewport().get_viewport_rid()
	RenderingServer.viewport_set_measure_render_time(low_rid, true)
	RenderingServer.viewport_set_measure_render_time(win_rid, true)
	for room in runtime.game.rooms:
		runtime.state.location = room.id
		enter_room("")
		for i in warm: await get_tree().process_frame
		var gaps := []
		var proc := []
		var rcpu := []
		var rgpu := []
		var draws := 0
		var prims := 0
		var last := Time.get_ticks_usec()
		for i in frames:
			await get_tree().process_frame
			var now := Time.get_ticks_usec()
			gaps.append((now - last) / 1000.0)
			last = now
			proc.append(Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0)
			rcpu.append(RenderingServer.viewport_get_measured_render_time_cpu(low_rid) + RenderingServer.viewport_get_measured_render_time_cpu(win_rid))
			rgpu.append(RenderingServer.viewport_get_measured_render_time_gpu(low_rid) + RenderingServer.viewport_get_measured_render_time_gpu(win_rid))
			draws = maxi(draws, int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)))
			prims = maxi(prims, int(Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)))
		var over := gaps.filter(func(x): return x > 8.0).size()
		perf_rows.append({"id": room.id, "frames": gaps.size(), "frame_ms": pct(gaps), "over_8ms_frames": over,
			"frame_ms_median": pct(gaps).p50, "frame_ms_p95": pct(gaps).p95, "frame_ms_max": pct(gaps).max,
			"process_ms": pct(proc), "process_ms_p95": pct(proc).p95, "render_cpu_ms": pct(rcpu), "render_gpu_ms": pct(rgpu),
			"draw_calls_max": draws, "primitives_in_frame_max": prims, "triangles": split_counts(), "probes": probe_pixels()})
	n64_ui.visible = true
	var f := FileAccess.open(folder.path_join("perf.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify({"rooms": perf_rows, "renderer": RenderingServer.get_current_rendering_method(),
		"device": RenderingServer.get_video_adapter_name(), "vendor": RenderingServer.get_video_adapter_vendor(),
		"engine": Engine.get_version_info().string, "window": [get_window().size.x, get_window().size.y],
		"vsync": DisplayServer.window_get_vsync_mode(), "max_fps": Engine.max_fps}, "\t", true))
	f.close()
	await super.capture_all(folder)
