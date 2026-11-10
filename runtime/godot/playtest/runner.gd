extends SceneTree
## Physical test driver. Uses production key input, CharacterBody3D and menu dispatch.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const RoomNavigation = preload("res://view/solid_navigation.gd")
var view
var config: Dictionary
var tick := 0
var last_event := 0
var first_event := -1
var events := []
var droughts := []
var stuck := []
var unreachable := []
var failures := []
var camera_bugs := []
var unlocated := []
var rooms := {}
var frames := []
var engine_frames := []
var engine_fps := []
var actions_done := []
var states := []
var input_file: FileAccess
var rng := RandomNumberGenerator.new()
var held := Vector2.ZERO
var grid: AStarGrid2D
var grid_room := ""
var start_memory := 0
var peak_memory := 0
var completed := false
var paths := []
var explorer_stalls := []
var geometry_dirty := true
var replay_files := []
var dispatches := []
# Per-frame work from timestamp probes (physics + engine step + process + render CPU).
# Replaces Performance.TIME_PROCESS as the rendered gate input: that monitor is the
# MAX of the last ~1 s window and includes RenderingServer sync/present (vsync) waits.
const FrameProbe = preload("res://playtest/frame_probe.gd")
const WARMUP_FRAMES := 72 # 1.2 s after each room entry: the previous gate's loading exclusion
var frame_marks := {}
var frame_rows := []
var frame_rids := []
var frame_index := 0
var frame_room := ""
var frame_room_age := 0
var boundary_frames := {}
var timing_boundaries := []
var slow_control := false

func _initialize() -> void:
	call_deferred("run")

func install_frame_probes() -> void:
	for row in [["ph:start",-1000,true],["ph:end",1000,true],["pr:start",-1000,false],["pr:end",1000,false]]:
		var p = FrameProbe.new()
		p.sink = self
		p.label = row[0]
		if row[2]: p.process_physics_priority = row[1]
		else: p.process_priority = row[1]
		root.add_child(p)
		if row[2]: p.set_process(false)
		else: p.set_physics_process(false)
	frame_rids = [view.viewport.get_viewport_rid(), root.get_viewport_rid()]
	for rid in frame_rids: RenderingServer.viewport_set_measure_render_time(rid, true)
	slow_control = config.get("control", "") == "slow_frames"

func frame_mark(label: String) -> void:
	var now := Time.get_ticks_usec()
	if label == "ph:start":
		if frame_marks.has("pr:end"): frame_finalize()
		frame_marks = {}
	frame_marks[label] = now
	if label == "ph:end" and slow_control and DisplayServer.get_name() != "headless":
		# Negative control only: a genuinely slow frame must fail the rendered gate.
		var until := now + 40000
		while Time.get_ticks_usec() < until: pass

func frame_finalize() -> void:
	for key in ["ph:start","ph:end","pr:start"]:
		if not frame_marks.has(key): return
	var location: String = view.runtime.state.location if view != null and view.runtime != null else ""
	if location != frame_room:
		frame_room = location
		frame_room_age = 0
	else:
		frame_room_age += 1
	var rc: float = RenderingServer.get_frame_setup_time_cpu()
	for rid in frame_rids: rc += RenderingServer.viewport_get_measured_render_time_cpu(rid)
	var ph: float = (frame_marks["ph:end"] - frame_marks["ph:start"]) / 1000.0
	var pe: float = (frame_marks["pr:start"] - frame_marks["ph:end"]) / 1000.0
	var pr: float = (frame_marks["pr:end"] - frame_marks["pr:start"]) / 1000.0
	frame_rows.append({"work":ph + pe + pr + rc, "physics":ph, "engine":pe, "process":pr, "render_cpu":rc, "room":frame_room, "room_age":frame_room_age, "boundary":boundary_frames.get(frame_index, "")})
	frame_index += 1

func measurement_boundary(reason: String) -> void:
	# Harness work (route grids, mesh/screenshot readbacks) is excluded from the
	# steady sample: this frame and the next two (a readback can stall the next sync).
	for i in 3: boundary_frames[frame_index + i] = reason
	timing_boundaries.append({"tick":tick,"frame":frame_index,"reason":reason})

static func percentile(values: Array, q: float):
	if values.is_empty(): return null
	var sorted := values.duplicate()
	sorted.sort()
	return sorted[mini(sorted.size() - 1, int(sorted.size() * q))]

func frame_timing() -> Dictionary:
	var steady := []
	var warm := []
	var all := []
	for row in frame_rows:
		all.append(row.work)
		if row.room_age <= WARMUP_FRAMES: warm.append(row.work)
		elif row.boundary == "": steady.append(row.work)
	var budget := 33.34
	return {"frame_work_p50_ms":percentile(steady, 0.5), "frame_work_p95_ms":percentile(steady, 0.95), "frame_work_p99_ms":percentile(steady, 0.99), "frame_work_max_ms":steady.max() if not steady.is_empty() else null,
		"warmup_work_p95_ms":percentile(warm, 0.95), "warmup_work_max_ms":warm.max() if not warm.is_empty() else null, "all_frames_work_max_ms":all.max() if not all.is_empty() else null,
		"frames_over_budget":all.filter(func(v): return v > budget).size(), "steady_frames":steady.size(), "warmup_frames":warm.size(), "frames":all.size(),
		"frame_scope":"per-frame CPU work = physics callbacks + physics step/deferred flush + process callbacks + RenderingServer measured render CPU, from global-priority timestamp probes; steady excludes the first %d frames after each room entry and explicit harness boundary frames (route grids, readbacks, captures). GPU execution and present/vsync waits are not CPU work and are excluded." % WARMUP_FRAMES,
		"control":"slow_frames (+40 ms busy wait per frame)" if slow_control else ""}

func keys(v: Vector2) -> void:
	held = v

func press(action: String) -> void:
	await step(Vector2.ZERO,[action])
	await step()

func flat(v: Vector3) -> Vector2:
	return Vector2(v.x,v.z)

func step(v := Vector2.ZERO, discrete := []) -> void:
	# A bot submits canonical frames, not animation-time inputs. Wait outside
	# its tick/recording clock while the exact same production envelope freezes.
	if view.room_transition != null and view.room_transition.active():
		await view.room_transition.finished
	keys(v)
	var digital: Array = discrete.duplicate()
	for pair in [["move_left",v.x<0],["move_right",v.x>0],["move_up",v.y<0],["move_down",v.y>0]]:
		if pair[1]: digital.append(pair[0])
	view.actions.submit_frame({"digital":digital})
	var begin := Time.get_ticks_usec()
	await physics_frame
	await process_frame
	tick += 1
	frames.append((Time.get_ticks_usec()-begin)/1000.0)
	if DisplayServer.get_name() != "headless":
		engine_frames.append(Performance.get_monitor(Performance.TIME_PROCESS)*1000.0)
		if Engine.get_frames_per_second() > 0: engine_fps.append(Engine.get_frames_per_second())
	peak_memory = maxi(peak_memory,int(Performance.get_monitor(Performance.MEMORY_STATIC)))
	var rid: String = view.runtime.state.location
	if not rooms.has(rid):
		var size: Array = view.runtime.rooms[rid].grid_size
		rooms[rid] = {"size":size,"heat":{},"samples":0,"triangles":0,"draw_calls":null,"rendered":DisplayServer.get_name() != "headless"}
	var row: Dictionary = rooms[rid]
	var pos: Vector3 = view.player.position
	var cell := "%d,%d" % [floori(pos.x*2),floori(pos.z*2)]
	row.heat[cell] = int(row.heat.get(cell,0))+1
	row.samples += 1
	# Mesh.get_faces() can synchronize GPU readback. Sample once per simulated
	# second and after each action/room creation, not every rendered frame.
	if should_measure_geometry(row):
		row.triangles = maxi(row.triangles,view.room_root.triangle_count()+view.room_root.triangle_count(view.player)+follower_triangles())
		geometry_dirty = false
	if row.rendered: row.draw_calls = maxi(0 if row.draw_calls == null else int(row.draw_calls),int(Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)))
	if tick % 6 == 0:
		input_file.store_line(JSON.stringify({"tick":tick,"room":rid,"input":[v.x,v.y],"position":[pos.x,pos.y,pos.z],"velocity":[view.player.velocity.x,view.player.velocity.y,view.player.velocity.z],"camera":view.room_root.camera_nodes[view.camera_index].id,"latched":view.player.latched,"grounded":view.player.is_on_floor()},"",true))
	var threshold := int(config.get("drought_seconds",20))*60
	if tick-last_event >= threshold:
		droughts.append({"room":rid,"start_tick":last_event,"end_tick":tick,"seconds":float(tick-last_event)/60})
		last_event = tick

func should_measure_geometry(row: Dictionary) -> bool:
	return geometry_dirty or row.samples == 1 or tick % 60 == 0

func follower_triangles() -> int:
	var total := 0
	for n in view.followers.values(): total += view.room_root.triangle_count(n)
	return total

func target(id: String):
	view.room_root.update_interaction_targets(view.player.position)
	var positions: Dictionary = view.room_root.target_positions
	if positions.has(id): return positions[id]
	if id.begins_with("interact:"):
		for a in view.runtime.game.interactions:
			if "interact:"+a.id == id:
				if positions.has(a.target): return positions[a.target]
				if not unlocated.has(id): unlocated.append(id)
	return null

func near(at: Vector3) -> bool:
	return flat(view.player.position).distance_to(flat(at)) <= 1.05 and absf(at.y-view.player.position.y) <= 1.8

func build_grid() -> void:
	grid = AStarGrid2D.new()
	var size: Array = view.runtime.rooms[view.runtime.state.location].grid_size
	grid.region = Rect2i(0,0,int(size[0]*2),int(size[1]*2))
	grid.cell_size = Vector2(0.5,0.5)
	grid.offset = Vector2(0.25,0.25)
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	grid.update()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.28
	capsule.height = 1.3
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = capsule
	q.exclude = [view.player.get_rid()]
	for x in grid.region.size.x:
		for z in grid.region.size.y:
			var p := grid.get_point_position(Vector2i(x,z))
			q.transform = Transform3D(Basis.IDENTITY,Vector3(p.x,0.76,p.y))
			var blocked: bool = p.x < 0.4 or p.y < 0.4 or p.x > size[0]-0.4 or p.y > size[1]-0.4
			blocked = blocked or not view.world.get_world_3d().direct_space_state.intersect_shape(q,1).is_empty()
			grid.set_point_solid(Vector2i(x,z),blocked)
	grid_room = view.runtime.state.location

func route(at: Vector3) -> PackedVector2Array:
	var nav = RoomNavigation.new()
	var size: Array=view.room_root.data.grid_size
	nav.configure(view.room_root.solid_definitions,Vector2(size[0],size[1]),float(view.player.tuning.capsule_radius_m)+float(view.player.tuning.safe_margin_m),float(view.player.tuning.capsule_height_m),float(view.player.tuning.bounds_margin_m),view.room_root.get("boundary_outline") if view.room_root.get("boundary_outline")!=null else PackedVector2Array())
	var points:=nav.route(view.player.position,at,0.75,false)
	var out:=PackedVector2Array()
	for point in points: out.append(Vector2(point.x,point.z))
	return out

func steer(toward: Vector2) -> Vector2:
	var desired := (toward-flat(view.player.position)).normalized()
	var basis: Basis = view.player.latched_basis if view.player.latched else view.player.camera_basis
	var right := flat(basis.x).normalized()
	var back := flat(basis.z).normalized()
	var best := Vector2.ZERO
	var score := -INF
	for x in [-1,0,1]:
		for y in [-1,0,1]:
			if x == 0 and y == 0: continue
			var candidate := Vector2(x,y)
			# A direction change releases the production latch; predict that exact rule.
			var b: Basis = basis
			if view.player.latched and absf(candidate.angle_to(view.player.last_input)) > 0.6: b = view.player.camera_basis
			var dir: Vector2 = (flat(b.x).normalized()*x+flat(b.z).normalized()*y).normalized()
			var s: float = dir.dot(desired)
			if s > score: score = s; best = candidate
	return best

func walk(id: String, at: Vector3) -> bool:
	if near(at): return true
	measurement_boundary("collision route construction")
	var way := route(at)
	if way.is_empty():
		# Attempt native steering as well: a graph failure alone is not a collision proof.
		var start: Vector3 = view.player.position
		for i in 120: await step(steer(flat(at)))
		if not near(at):
			unreachable.append({"action":id,"room":view.runtime.state.location,"target":[at.x,at.y,at.z],"reason":"no collision-free approach within grid/radius bounds","distance_m":flat(view.player.position).distance_to(flat(at))})
			if start.distance_to(view.player.position) < 0.1: stuck.append({"action":id,"tick":tick,"reason":"120 ticks input without displacement"})
		return near(at)
	var index := 0
	var checkpoint: Vector3 = view.player.position
	var recent := {}
	for i in 2400:
		if near(at): keys(Vector2.ZERO); return true
		while index < way.size()-1 and flat(view.player.position).distance_to(way[index]) < 0.23: index += 1
		await step(steer(way[index]))
		if i % 120 == 119:
			var cell := "%d,%d" % [roundi(view.player.position.x*4),roundi(view.player.position.z*4)]
			recent[cell] = int(recent.get(cell,0))+1
			if checkpoint.distance_to(view.player.position) < 0.08 or recent[cell] > 3:
				stuck.append({"action":id,"room":view.runtime.state.location,"tick":tick,"position":[view.player.position.x,view.player.position.z],"reason":"no displacement / repeated position loop"})
				return false
			checkpoint = view.player.position
	stuck.append({"action":id,"tick":tick,"reason":"40 simulated seconds without target arrival"})
	return false

func activate(id: String) -> bool:
	keys(Vector2.ZERO)
	var before := dispatches.size()
	var ix := -1
	for i in view.ui_actions.size():
		if view.ui_actions[i].id == id: ix = i
	if ix < 0: failures.append("action unavailable: "+id); return false
	# Tick-separated actions use the exact same provider as keyboard and replay.
	if not view.menu_open: await press("action_menu")
	# Opening Tab resets selection to zero; a retained dialogue list may not.
	while view.menu_index != ix: await press("move_down")
	await press("primary")
	geometry_dirty = true
	await step()
	# A legal re-inspection may preserve state. Verify the actual authoritative
	# receipt instead of mistaking idempotence (or WAIT) for a failed input.
	if dispatches.size()!=before+1 or dispatches[-1].action!=id or not dispatches[-1].ok:
		failures.append("menu input did not dispatch: "+id); return false
	actions_done.append(id)
	states.append(view.runtime.state.duplicate(true))
	if id != "wait":
		if first_event < 0: first_event = tick
		events.append({"tick":tick,"action":id,"room":view.runtime.state.location})
		last_event = tick
	return true

func cut_probe() -> void:
	await step(Vector2(0,-1))
	var old: Vector3 = view.player.direction(Vector2(0,-1))
	for angle in [PI/2,PI,PI*1.5]:
		view.player.camera_cut(Basis(Vector3.UP,angle))
		var after: Vector3 = view.player.direction(Vector2(0,-1))
		if old.distance_to(after) > 0.001: camera_bugs.append("held heading changed through repeated cuts")
	view.player.direction(Vector2.ZERO)
	if view.player.latched: camera_bugs.append("neutral did not release latch")
	view.select_camera(view.camera_index)
	await step()

func trap() -> void:
	var p: Vector3 = view.player.position
	for entry in [[Vector3(-0.5,0,0),Vector3(0.2,2,1.2)],[Vector3(0.5,0,0),Vector3(0.2,2,1.2)],[Vector3(0,0,-0.5),Vector3(1.2,2,0.2)],[Vector3(0,0,0.5),Vector3(1.2,2,0.2)]]:
		var body := StaticBody3D.new()
		var shape := CollisionShape3D.new()
		var box := BoxShape3D.new()
		box.size = entry[1]
		shape.shape = box
		body.add_child(shape)
		view.world.add_child(body)
		body.position = p+entry[0]+Vector3(0,0.8,0)

func run() -> void:
	config = Wire.read_json("res://playtest-config.json")
	rng.seed = int(config.get("seed",7))
	input_file = FileAccess.open(config.output.path_join("inputs.jsonl"),FileAccess.WRITE)
	view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","save":"user://ship-save.json"})
	if not booted.ok: failures.append(str(booted)); await finish(); return
	view.state_changed.connect(func(result): dispatches.append(result))
	view.options["replay_trace"] = true
	view.actions.configure({"version":1})
	view.actions.set_source("bot")
	install_frame_probes()
	start_memory = int(Performance.get_monitor(Performance.MEMORY_STATIC))
	await step()
	if config.get("control","") == "script_error":
		var bad = load("res://playtest/script_error.gd").new()
		root.add_child(bad)
	await cut_probe()
	for trace in config.get("traces",[]):
		view.runtime.configure(view.runtime.game)
		view.enter_room("")
		view.refresh()
		grid_room = ""
		if config.get("control","") == "collision_trap": trap()
		await step()
		var movie_path: String = config.output.path_join("winning-"+str(paths.size())+".h64movie.json")
		view.replay.start_record(movie_path,int(config.get("seed",7)))
		var passed := true
		for id in trace.actions:
			var at = target(id)
			if at != null and not await walk(id,at): passed = false; break
			if not await activate(id): passed = false; break
			if DisplayServer.get_name() != "headless" and not FileAccess.file_exists(config.output.path_join(view.runtime.state.location+".png")):
				measurement_boundary("screenshot readback")
				await view.capture_low(config.output.path_join(view.runtime.state.location+".png"))
		passed = passed and view.runtime.endings(view.runtime.state).has(trace.ending)
		var recorded: Dictionary = view.replay.stop_record()
		if recorded.ok: replay_files.append(movie_path.get_file())
		else: failures.append("movie record failed: "+str(recorded))
		paths.append({"ending":trace.ending,"passed":passed})
	completed = not paths.is_empty() and paths.all(func(x): return x.passed)
	if config.mode in ["both","monkey"]:
		view.runtime.configure(view.runtime.game)
		view.enter_room("")
		view.refresh()
		grid_room = ""
		await step()
		view.replay.start_record(config.output.path_join("explorer.h64movie.json"),int(config.get("seed",7)))
		var until := tick+int(config.get("seconds",30))*60
		var aim := Vector2.ZERO
		var prior_position: Vector3 = view.player.position
		var prior_room: String = view.runtime.state.location
		var recent_cells := {}
		while tick < until:
			if tick % 45 == 0: aim = Vector2(rng.randi_range(-1,1),rng.randi_range(-1,1))
			await step(aim)
			if tick % 120 == 0:
				var cell := "%s:%d,%d" % [view.runtime.state.location,roundi(view.player.position.x*2),roundi(view.player.position.z*2)]
				recent_cells[cell] = int(recent_cells.get(cell,0))+1
				if prior_room == view.runtime.state.location and aim != Vector2.ZERO and (prior_position.distance_to(view.player.position)<0.08 or recent_cells[cell]>3):
					explorer_stalls.append({"tick":tick,"cell":cell,"reason":"wander no displacement / repeated cell; bounded observation only"})
				prior_position = view.player.position
				prior_room = view.runtime.state.location
			# Fixed cameras need no camera input to complete or explore.
			if tick % 30 == 0:
				var choices := []
				for a in view.runtime.actions(view.runtime.state):
					var at = target(a.id)
					if at == null or near(at): choices.append(a.id)
				if not choices.is_empty(): await activate(choices[rng.randi_range(0,choices.size()-1)])
	await finish()

func finish() -> void:
	if view != null and view.replay != null and view.replay.recording:
		var recorded: Dictionary = view.replay.stop_record()
		if recorded.ok: replay_files.append(recorded.path.get_file())
	keys(Vector2.ZERO)
	frames.sort()
	var timing := {"scope":"await-frame intervals exclude routing/collection; whole-probe throughput includes them. Engine frame/FPS samples only with real renderer. No GPU/device FPS certification.","samples":frames.size()}
	if not frames.is_empty(): timing.merge({"median_ms":frames[frames.size()/2],"p95_ms":frames[mini(frames.size()-1,int(frames.size()*0.95))],"max_ms":frames[-1]})
	if not frames.is_empty(): timing["wall_throughput_fps"] = 1000.0 / maxf(0.001,frames.reduce(func(a,b): return a+b,0.0)/frames.size())
	engine_frames.sort()
	engine_fps.sort()
	# Retained for transparency, NOT the gate: Godot's TIME_PROCESS is a 1 s max incl. present waits.
	timing["monitor_time_process_p95_ms"] = engine_frames[mini(engine_frames.size()-1,int(engine_frames.size()*0.95))] if not engine_frames.is_empty() else null
	timing["engine_fps_median"] = engine_fps[engine_fps.size()/2] if not engine_fps.is_empty() else null
	timing.merge(frame_timing())
	timing["boundaries"] = timing_boundaries
	var out := {"completed":completed,"paths":paths,"failures":failures,"stuck":stuck,"unreachable":unreachable,"camera_bugs":camera_bugs,"unlocated_interactions":unlocated,"events":events,"droughts":droughts,"first_event_seconds":float(first_event)/60 if first_event >= 0 else null,"ticks":tick,"simulation_seconds":float(tick)/60,"rooms":rooms,"timing":timing,"memory":{"start_bytes":start_memory,"peak_bytes":peak_memory,"end_bytes":int(Performance.get_monitor(Performance.MEMORY_STATIC)),"scope":"engine static allocator, not OS RSS; exit leak warnings checked by parent"},"actions":actions_done,"states":states,"missing_assets":view.resolver.missing.keys(),"display":DisplayServer.get_name(),"engine":Engine.get_version_info().string,"fixed_fps":60,"seed":config.get("seed",7)}
	var f := FileAccess.open(config.output.path_join("native.json"),FileAccess.WRITE)
	out["replay_files"] = replay_files
	out["explorer_stalls"] = explorer_stalls
	out["render_verified"] = DisplayServer.get_name() != "headless" and rooms.size() == view.runtime.rooms.size() and rooms.values().all(func(r): return r.draw_calls != null and r.draw_calls > 0)
	out["budget"] = {"triangles_per_room":6000,"draw_calls_per_room":256,"rendered_p95_ms":33.34}
	out["resource_monitors_before_teardown"] = {"objects":Performance.get_monitor(Performance.OBJECT_COUNT),"resources":Performance.get_monitor(Performance.OBJECT_RESOURCE_COUNT),"orphan_nodes":Performance.get_monitor(Performance.OBJECT_ORPHAN_NODE_COUNT),"scope":"live counts before teardown; parent separately records exit RID/ObjectDB diagnostics"}
	f.store_string(JSON.stringify(out,"",true))
	f.close()
	input_file.close()
	print("PHYSICAL ticks=%d paths=%d completed=%s events=%d stuck=%d unreachable=%d" % [tick,paths.size(),completed,events.size(),stuck.size(),unreachable.size()])
	await view.quit_cleanly()
