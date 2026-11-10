extends SceneTree
## MERGE2 frame-time probe (harness only; tests/ is never exported).
## Replays one pinned deterministic input movie through the production presenter
## and records per-frame CPU phases from global-priority timestamp markers:
##   physics scripts per consumer (Actions -100, presenter -50, player 0, module
##   host 10, actor bridge 12, movie 100), physics engine + deferred flush,
##   _process scripts, render CPU (RenderingServer measured), and the remaining
##   post-draw time (present / compositor / vsync wait, OS events).
## Levers only toggle presentation or instrumentation; the movie's state hashes
## prove every lever replayed the identical simulation.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Probe = preload("res://tests/merge2_perf_probe.gd")
const PHYS := [["start",-1000],["after_actions",-75],["after_presenter",-25],["after_player",5],["after_host",11],["after_bridge",15],["after_movie",150],["end",1000]]
var view
var replay
var config: Dictionary
var tokens := []
var marks := {}
var samples := []
var frame := 0
var room := ""
var room_age := 0
var rids := []
var instr_file: FileAccess
var instr_signature := ""
var heat := {}
var lever_frames := {}
var boot_ms := 0.0
var events := []
var shot_ticks := {}

func timed(label: String, count: int, body: Callable) -> Dictionary:
	var rows := []
	for i in count:
		var begin := Time.get_ticks_usec()
		body.call()
		rows.append((Time.get_ticks_usec() - begin) / 1000.0)
	rows.sort()
	return {"op":label, "n":count, "median_ms":rows[rows.size() / 2], "max_ms":rows[-1], "min_ms":rows[0]}

func make_and_free(c: Dictionary) -> void:
	var n = view.resolver.character(c)
	if n != null: n.free()

func micro() -> Array:
	# Isolated costs of event-time operations on the final replay state (simulation stopped).
	var out := []
	var rt = view.runtime
	out.append(timed("runtime.actions(state)", 200, func(): rt.actions(rt.state)))
	out.append(timed("contextual.select", 200, func(): view.contextual.select(view)))
	out.append(timed("sync_n64_ui", 100, func(): view.sync_n64_ui()))
	out.append(timed("sync_input_context", 200, func(): view.sync_input_context()))
	out.append(timed("refresh (incl. hidden action buttons)", 50, func(): view.refresh()))
	out.append(timed("codec.pack", 200, func(): view.codec.pack(rt)))
	out.append(timed("movie state()+digest", 50, func(): replay.digest(replay.state())))
	if view.module_host != null: out.append(timed("module state_hash", 100, func(): view.module_host.state_hash()))
	out.append(timed("room triangle_count (mesh readback)", 5, func(): view.room_root.triangle_count()))
	var protagonist: Dictionary = rt.characters.get(rt.game.metadata.get("protagonist", ""), {})
	out.append(timed("resolver.character(protagonist)", 5, func(): make_and_free(protagonist)))
	var position: Vector3 = view.player.position
	out.append(timed("enter_room(\"\") full rebuild", 5, func(): view.enter_room("")))
	view.player.position = position
	# Per room: full rebuild and the module travel preflight probe (build + immediate free).
	var location: String = rt.state.location
	for room in rt.game.rooms:
		rt.state.location = room.id
		out.append(timed("enter_room %s" % room.id, 5, func(): view.enter_room("")))
		out.append(timed("probe build+free %s" % room.id, 5, func(): probe_cycle(room.id)))
	rt.state.location = location
	return out

func probe_cycle(id: String) -> void:
	var probe = preload("res://view/room.gd").new()
	probe.theme = view.theme
	probe.build(view.runtime.rooms[id], view.runtime, view.resolver)
	probe.position = Vector3(2048, 0, 2048)
	probe.visible = false
	view.world.add_child(probe)
	probe.free()

class Instrument extends Node:
	var harness
	func _physics_process(_delta: float) -> void:
		harness.instrument()

func _initialize() -> void:
	call_deferred("run")

func mark(label: String) -> void:
	var now := Time.get_ticks_usec()
	if label == "ph:start":
		if marks.has("ph:start"): finalize(now)
		marks = {}
	marks[label] = now
	if label == "pr:end" and view != null and frame % 30 == 0 and needs_reapply():
		apply_levers()
		lever_frames[frame] = true
	if label == "pr:end" and "shots" in tokens and replay != null and replay.playing:
		# Render-equivalence diagnostic: the same replay ticks captured by two builds must match.
		var t: int = replay.cursor
		if (t % 120 == 0 or room_age == 30) and not shot_ticks.has(t):
			shot_ticks[t] = true
			var dir: String = config.output.path_join("shots")
			DirAccess.make_dir_recursive_absolute(dir)
			view.viewport.get_texture().get_image().save_png(dir.path_join("%05d-3d.png" % t))
			root.get_texture().get_image().save_png(dir.path_join("%05d-screen.png" % t))

func needs_reapply() -> bool:
	return "actors_off" in tokens or "lighting_off" in tokens or "room_off" in tokens

func finalize(next_start: int) -> void:
	for key in ["ph:end","pr:start","pr:end"]:
		if not marks.has(key): return
	if replay == null or not replay.playing and not replay.finished: return
	var location: String = view.runtime.state.location
	if location != room:
		room = location
		room_age = 0
	else:
		room_age += 1
	var s := {"f":frame,"t":replay.cursor,"r":room,"a":room_age}
	s["w"] = (next_start - marks["ph:start"]) / 1000.0
	s["ph"] = (marks["ph:end"] - marks["ph:start"]) / 1000.0
	s["pe"] = (marks["pr:start"] - marks["ph:end"]) / 1000.0
	s["pr"] = (marks["pr:end"] - marks["pr:start"]) / 1000.0
	s["po"] = (next_start - marks["pr:end"]) / 1000.0
	var seg := []
	for i in range(1, PHYS.size()):
		seg.append((marks["ph:" + PHYS[i][0]] - marks["ph:" + PHYS[i-1][0]]) / 1000.0)
	s["seg"] = seg
	var rc: float = RenderingServer.get_frame_setup_time_cpu()
	var rg := 0.0
	for rid in rids:
		rc += RenderingServer.viewport_get_measured_render_time_cpu(rid)
		rg += RenderingServer.viewport_get_measured_render_time_gpu(rid)
	s["rc"] = rc
	s["rg"] = rg
	s["dc"] = Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
	s["ob"] = Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
	s["pm"] = Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
	s["tp"] = Performance.get_monitor(Performance.TIME_PROCESS) * 1000.0
	s["tpp"] = Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS) * 1000.0
	s["h"] = replay.hash_ticks.has(replay.cursor)
	s["lv"] = lever_frames.has(frame)
	samples.append(s)
	frame += 1

func install_probes() -> void:
	for row in PHYS:
		var p = Probe.new()
		p.sink = self
		p.label = row[0]
		p.process_physics_priority = row[1]
		root.add_child(p)
		p.set_process(false)
	for row in [["start",-1000],["end",1000]]:
		var q = Probe.new()
		q.sink = self
		q.label = row[0]
		q.process_priority = row[1]
		root.add_child(q)
		q.set_physics_process(false)
	if "bot_instr" in tokens:
		var instrument := Instrument.new()
		instrument.harness = self
		instrument.process_physics_priority = 200
		root.add_child(instrument)

func instrument() -> void:
	# Mirrors the per-tick bookkeeping of playtest/module_runner.gd / runner.gd
	# (bot instrumentation, never production play): heat map, state hash, JSONL.
	if replay == null or not replay.playing: return
	var host = view.module_host
	var pos: Vector3 = view.player.position
	var cell := "%d,%d" % [floori(pos.x * 2), floori(pos.z * 2)]
	heat[cell] = int(heat.get(cell, 0)) + 1
	var _memory := int(Performance.get_monitor(Performance.MEMORY_STATIC))
	if host != null:
		var digest: String = host.state_hash()
		instr_file.store_line(JSON.stringify({"tick":frame,"move":[0,0],"buttons":[],"module_hash":digest,"player":[pos.x,pos.y,pos.z]}, "", true))
		var signature := "%s:%d:%d" % [view.runtime.state.location, host.generation, host.combat.wave if host.combat != null else -1]
		if signature != instr_signature:
			instr_signature = signature
			var _tri: int = view.room_root.triangle_count() + view.room_root.triangle_count(view.player)
	elif frame % 60 == 0:
		var _tri2: int = view.room_root.triangle_count() + view.room_root.triangle_count(view.player)
	if frame % 6 == 0:
		instr_file.store_line(JSON.stringify({"tick":frame,"room":view.runtime.state.location,"position":[pos.x,pos.y,pos.z],"velocity":[view.player.velocity.x,view.player.velocity.y,view.player.velocity.z],"camera":view.room_root.camera_nodes[view.camera_index].id,"latched":view.player.latched,"grounded":view.player.is_on_floor()}, "", true))

static func placed(n: Node) -> String:
	return str(n.get_meta("placed", ""))

func apply_levers(_room := "") -> void:
	if view == null or view.room_root == null: return
	for n in view.room_root.get_children():
		if not n is Node3D or n is Camera3D: continue
		var kind := placed(n)
		if kind == "actor":
			if "actors_off" in tokens: n.visible = false
		elif kind in ["light", "particles"]:
			if "lighting_off" in tokens: n.visible = false
		elif "room_off" in tokens:
			n.visible = false
	if "actors_off" in tokens:
		var visual = view.player.get_node_or_null("visual")
		if visual != null: visual.visible = false
		for f in view.followers.values(): f.visible = false
		if view.module_host != null and view.module_host.combat != null:
			for enemy in view.module_host.combat.enemies:
				if enemy.visual != null: enemy.visual.visible = false
		for n in view.world.find_children("*", "", true, false):
			if n.has_method("advance_pose"): n.set_process(false)
		for c in view.get_children():
			if c.get_script() == preload("res://actors/bridge.gd"): c.set_physics_process(false)
	if "lighting_off" in tokens:
		RenderingServer.global_shader_parameter_set("n64_classic", Vector4(0, 0, 0, 0))
	if "ui_off" in tokens:
		view.n64_ui.visible = false
		view.n64_ui.set_process(false)
		view.controls_hud.visible = false
		if view.module_host != null and view.module_host.hud != null: view.module_host.hud.visible = false
	if "msaa2" in tokens: view.viewport.msaa_3d = Viewport.MSAA_2X
	if "msaa0" in tokens: view.viewport.msaa_3d = Viewport.MSAA_DISABLED
	if "nearest" in tokens:
		for n in view.get_children():
			if n is TextureRect: n.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	if "viewport_half" in tokens: view.viewport.size = Vector2i(160, 120)

func run() -> void:
	var started_usec := Time.get_ticks_usec()
	config = Wire.read_json("res://merge2-perf.json")
	tokens = config.get("tokens", [])
	# COMBAT lane lever: the same build with the combat readability profile off (camera, light, telegraph), so the
	# readability layer's own cost is an A/B on one movie. Builds without the profile ignore it.
	if FileAccess.file_exists("res://modules/combat/readability.gd"):
		var R = load("res://modules/combat/readability.gd")
		var d: Dictionary = R.defaults().duplicate(true)
		var off := []
		if "readability_off" in tokens: off = ["camera", "light", "telegraph"]
		for group in ["camera", "light", "telegraph"]:
			if ("readability_" + group + "_off") in tokens: off.append(group)
		for group in off: d[group]["enabled"] = false
		if not off.is_empty(): R.cached = d
	if DisplayServer.get_name() == "headless":
		print("PERF requires a real renderer")
		quit(2)
		return
	install_probes()
	view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack":"res://theme.json", "bindings":"res://bindings.json", "save":config.output.path_join("perf-save.json")})
	if not booted.ok:
		print("PERF BOOT ", booted)
		await view.quit_cleanly(2)
		return
	for c in view.get_children():
		if c.get_script() == preload("res://actors/bridge.gd"): c.process_physics_priority = 12
	if "bot_instr" in tokens:
		instr_file = FileAccess.open(config.output.path_join("instrument.jsonl"), FileAccess.WRITE)
	view.room_entered.connect(apply_levers)
	view.state_changed.connect(func(result): events.append({"t":replay.cursor if replay != null else -1, "f":frame, "kind":"dispatch", "action":str(result.get("action", ""))}))
	view.room_entered.connect(func(id): events.append({"t":replay.cursor if replay != null else -1, "f":frame, "kind":"room", "room":id}))
	if view.module_host != null:
		view.module_host.story_event.connect(func(kind, _payload): events.append({"t":replay.cursor if replay != null else -1, "f":frame, "kind":"module", "event":kind}))
	var movie_data = Wire.read_json(config.movie)
	if not movie_data is Dictionary:
		print("PERF movie unreadable")
		await view.quit_cleanly(2)
		return
	var old = view.replay
	replay = preload("res://tests/merge2_perf_movie.gd").new()
	view.add_child(replay)
	replay.attach(view)
	replay.extensions = old.extensions.duplicate()
	view.remove_child(old)
	old.queue_free()
	view.replay = replay
	var real_build: String = replay.real_build_hash()
	if config.get("pin_build", false): replay.pinned_build = str(movie_data.header.build_hash)
	rids = [view.viewport.get_viewport_rid(), root.get_viewport_rid()]
	for rid in rids: RenderingServer.viewport_set_measure_render_time(rid, true)
	if "warm_chars" in tokens:
		# Diagnostic: give this process a warm character cache, like a bot process that
		# already played an earlier trace before recording this movie.
		for row in view.resolver.characters:
			make_and_free({"id":str(row.get("character_id", "")), "body_id":row.get("body_id", ""), "base_rig_id":row.get("base_rig_id", ""), "params":row.get("params", {})})
	var playback: Dictionary = replay.begin_playback(movie_data, false)
	if not playback.ok:
		print("PERF playback refused ", playback)
		await view.quit_cleanly(2)
		return
	if "no_hash" in tokens: replay.movie.hashes = [replay.movie.hashes[-1]]
	apply_levers()
	boot_ms = (Time.get_ticks_usec() - started_usec) / 1000.0
	while not replay.finished:
		await process_frame
	await process_frame
	await process_frame
	if instr_file != null: instr_file.close()
	var micro_rows := micro() if "micro" in tokens else []
	var out := {"micro":micro_rows, "events":events, "tokens":tokens, "display":DisplayServer.get_name(), "method":RenderingServer.get_current_rendering_method(), "driver":RenderingServer.get_current_rendering_driver_name(), "adapter":RenderingServer.get_video_adapter_name(), "vsync":DisplayServer.window_get_vsync_mode(), "window":[root.size.x, root.size.y], "engine":Engine.get_version_info().string, "boot_ms":boot_ms, "replay":replay.result, "movie_build":str(movie_data.header.build_hash), "real_build":real_build, "pinned":replay.pinned_build != "", "phases":PHYS, "samples":samples, "scope":"60 Hz fixed-step movie replay; per-frame CPU timestamps from global-priority markers; render CPU from RenderingServer measurement; po = post-draw wall (present/compositor/vsync wait + OS). Not a device FPS certification."}
	var f := FileAccess.open(config.output.path_join("native.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(out, "", true))
	f.close()
	print("PERF tokens=", tokens, " frames=", samples.size(), " replay_ok=", replay.result.get("ok", false))
	await view.quit_cleanly(0 if replay.result.get("ok", false) else 1)
