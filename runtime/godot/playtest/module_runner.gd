extends "res://playtest/runner.gd"
## Additive module bots; never inject outcomes, health, or winning positions.
const ModuleView = preload("res://playtest/module_view.gd")
const CombatBot = preload("res://playtest/combat_bot.gd")
var buttons := []
var hashes := []
var snapshots: FileAccess
var captures := {}
var module_names := []
var combat_metrics := []
var geometry_signature := ""
var steady_frames := []
var quiet_after_usec := 0
func measurement_boundary(reason: String) -> void:
	# The legacy monitor sample (retained, not the gate) updates at ~1 Hz; let a
	# load/readback window expire. Instrumentation clock only, never gameplay authority.
	quiet_after_usec = Time.get_ticks_usec() + 1200000
	super.measurement_boundary(reason)
func should_measure_geometry(_row: Dictionary) -> bool:
	# This driver records exact topology at each room/attempt/wave change below.
	return false
func near(at: Vector3) -> bool:
	return flat(view.player.position).distance_to(flat(at)) <= 0.88 and absf(at.y-view.player.position.y) <= 0.5
func target(id: String):
	var at: Vector3 = view.module_host.anchor(id)
	if at != Vector3.INF: return at
	return super.target(id)
func step(v := Vector2.ZERO, discrete := []) -> void:
	await super.step(v, discrete + buttons)
	var host = view.module_host
	var signature: String = "%s:%d:%d" % [view.runtime.state.location,host.generation,host.combat.wave if host.combat != null else -1]
	# get_faces synchronizes GPU readback. Mesh topology changes at room/attempt/wave boundaries, not each movement tick.
	if signature != geometry_signature:
		var tri: int = view.room_root.triangle_count() + view.room_root.triangle_count(view.player)
		if host.combat != null:
			for enemy in host.combat.enemies: tri += view.room_root.triangle_count(enemy.body)
		rooms[view.runtime.state.location].triangles = maxi(rooms[view.runtime.state.location].triangles, tri)
		geometry_signature = signature
		measurement_boundary("room/attempt/wave topology readback")
	if DisplayServer.get_name() != "headless" and Time.get_ticks_usec() > quiet_after_usec:
		steady_frames.append(Performance.get_monitor(Performance.TIME_PROCESS)*1000.0)
	var hash: String = host.state_hash()
	hashes.append(hash)
	snapshots.store_line(JSON.stringify({"tick":tick,"move":[v.x,v.y],"buttons":buttons,"module_hash":hash,"player":[view.player.position.x,view.player.position.y,view.player.position.z]},"",true))
	if DisplayServer.get_name() != "headless":
		var kind: String = "combat" if host.combat != null else ("course" if host.course != null else "region_"+view.runtime.state.location)
		var ready: bool = (host.combat == null or host.combat.tick_index > 45) and (host.course == null or host.course.elapsed > 180) and tick > 20 and host.pending.is_empty()
		if not captures.has(kind) and ready:
			captures[kind] = true
			measurement_boundary("screenshot readback")
			await view.capture_low(config.output.path_join(kind+".png"))
func activate(id: String) -> bool:
	if id.begins_with("assume:"):
		if not id.begins_with("assume:complete:"): failures.append("physical trace cannot model failure as success"); return false
		return await challenge_bot()
	var at = target(id)
	if at != null and not near(at): return false
	buttons = []
	# Portal dispatch emits its authoritative receipt only after staged clearance.
	if id.begins_with("move:") and view.runtime.modules.catalogue.has("regions"):
		var before := dispatches.size()
		var ix := -1
		for i in view.ui_actions.size():
			if view.ui_actions[i].id == id: ix = i
		if ix < 0: return false
		if not view.menu_open: await press("action_menu")
		while view.menu_index != ix: await press("move_down")
		await press("primary")
		for i in 24:
			if view.module_host.pending.is_empty(): break
			await step()
		if dispatches.size() != before+1 or dispatches[-1].action != id or not dispatches[-1].ok:
			failures.append("guarded portal did not commit "+id); return false
		actions_done.append(id); states.append(view.runtime.state.duplicate(true))
		events.append({"tick":tick,"action":id,"room":view.runtime.state.location}); last_event = tick
		grid_room = ""
		return true
	return await super.activate(id)
func challenge_bot() -> bool:
	var host = view.module_host
	var id: String = host.active_id
	var started := tick
	var dodged_wave := -1
	if id == "": failures.append("no live challenge executor"); return false
	for i in 5400:
		if host.active_id == "": break
		var aim := Vector2.ZERO
		buttons = []
		if host.combat != null and host.combat.extended:
			# COMBAT lane: robots/boss (API 1.1.0) read the telegraph language; see playtest/combat_bot.gd.
			var plan: Dictionary = CombatBot.decide(view, host.combat)
			buttons = plan.buttons
			if plan.aim != null: aim = steer(flat(plan.aim))
		elif host.combat != null:
			var combat = host.combat
			buttons = ["focus"]
			var enemy = combat.find_target(combat.target)
			if enemy == null:
				var distance := INF
				for e in combat.enemies:
					var d: float = e.body.position.distance_to(view.player.position)
					if e.hp > 0 and d < distance: enemy = e; distance = d
			if enemy != null:
				var distance: float = enemy.body.position.distance_to(view.player.position)
				if distance > 1.35: aim = steer(flat(enemy.body.position))
				if distance <= 1.65 and combat.age < 0 and combat.roll_age < 0 and combat.hurt_age < 0:
					if enemy.state == "telegraph" and dodged_wave != combat.wave:
						buttons.append("dodge")
						dodged_wave = combat.wave
					else: buttons.append("primary")
		elif host.course != null:
			var c = host.course
			if c.countdown == 0 and c.history.size() < c.track.checkpoints.size():
				var p: Array = c.track.checkpoints[c.history.size()].position_m
				if c.elapsed == 20: buttons.append("dodge")
				aim = steer(Vector2(p[0], p[2]))
		await step(aim)
	buttons = []
	keys(Vector2.ZERO)
	var success: bool = view.runtime.state.modules.completed.has(id)
	if not success:
		failures.append("physical challenge not cleared: "+id)
		for i in 65:
			if host.retry_ticks == 0: break
			await step()
	else:
		events.append({"tick":tick,"action":"observed:"+id,"room":view.runtime.state.location})
		last_event = tick
	paths.append({"challenge":id,"passed":success,"ticks":tick-started})
	return success
func visit_regions() -> bool:
	# Derive actual door routes from currently legal finite states, then walk every edge.
	var origin: String = view.runtime.state.location
	for region in view.runtime.modules.regions.values():
		if region.room == origin: continue
		var queue := [{"state":view.runtime.state.duplicate(true),"path":[]}]
		var seen := {}
		var way := []
		while not queue.is_empty():
			var row: Dictionary = queue.pop_front()
			if row.state.location == region.room: way = row.path; break
			if seen.has(row.state.location): continue
			seen[row.state.location] = true
			for action in view.runtime.actions(row.state):
				if action.id.begins_with("move:"): queue.append({"state":action.state,"path":row.path+[action.id]})
		for action in way:
			var at = target(action)
			if not await walk(action,at) or not await activate(action): return false
		# Return along each reciprocal edge before taking the ending route.
		for action in way.duplicate().slice(0,way.size()):
			var parts: PackedStringArray = str(way.pop_back()).split(":")
			var old: Dictionary = view.runtime.rooms[parts[1]]
			var door: Dictionary = old.doors.filter(func(d): return d.id == parts[2])[0]
			var back: String = "move:"+door.to_room+":"+door.to_door
			if not await walk(back,target(back)) or not await activate(back): return false
	return true
func run() -> void:
	config = Wire.read_json("res://playtest-config.json")
	input_file = FileAccess.open(config.output.path_join("inputs.jsonl"),FileAccess.WRITE)
	snapshots = FileAccess.open(config.output.path_join("module-inputs.jsonl"),FileAccess.WRITE)
	view = ModuleView.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","save":config.output.path_join("checkpoint.json")})
	if not booted.ok: failures.append(str(booted)); await finish(); return
	view.state_changed.connect(func(result): dispatches.append(result))
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	view.options["replay_trace"] = true
	install_frame_probes()
	start_memory = int(Performance.get_monitor(Performance.MEMORY_STATIC))
	for id in view.runtime.modules.catalogue:
		if id in ["combat","course","regions"]: module_names.append(id)
	await step()
	view.replay.start_record(config.output.path_join("modules.h64movie.json"),int(config.get("seed",7)))
	# All movement, menus and combat buttons use the production Actions reducer.
	for trace in config.traces:
		var passed := true
		for id in trace.actions:
			if not str(id).begins_with("assume:"):
				var at = target(id)
				if at != null and not await walk(id,at): passed = false; break
			if not await activate(id): passed = false; break
			if id == "interact:learn" and module_names == ["regions"]:
				if not await visit_regions(): passed = false; break
		passed = passed and view.runtime.endings(view.runtime.state).has(trace.ending)
		paths.append({"ending":trace.ending,"passed":passed})
	completed = not paths.is_empty() and paths.all(func(p): return p.passed)
	for id in view.runtime.modules.challenges:
		if not view.module_host.attempts.any(func(a): return a.challenge == id and a.success):
			completed = false
			failures.append("no successful physical coverage for "+id)
	await finish()
func finish() -> void:
	if view.replay != null and view.replay.recording:
		var recorded: Dictionary = view.replay.stop_record()
		if recorded.ok: replay_files.append(recorded.path.get_file())
		else: failures.append("module movie recording failed")
	keys(Vector2.ZERO)
	if snapshots != null: snapshots.close()
	var host = view.module_host
	var tested := []
	for attempt in host.attempts:
		if not tested.has(attempt.kind): tested.append(attempt.kind)
	if host.events.any(func(e): return e.kind == "region_unlocked"): tested.append("regions")
	var value := {"game_hash":view.runtime.game.game_hash,"completed":completed,"module_physical":true,"modules_tested":module_names,"attempts":host.attempts,"module_events":host.events,"state_hashes":hashes,"final_state":view.runtime.state,"paths":paths,"failures":failures,"stuck":stuck,"unreachable":unreachable,"transition_errors":host.transition_errors,"camera_bugs":camera_bugs,"events":events,"first_event_seconds":float(first_event)/60 if first_event >= 0 else null,"ticks":tick,"rooms":rooms,"missing_assets":view.resolver.missing.keys(),"display":DisplayServer.get_name(),"engine":Engine.get_version_info().string,"fixed_hz":60,"render_verified":DisplayServer.get_name()!="headless","captures":captures.keys(),"human_tested":"not_run","input_scope":"production Actions.submit_frame for every movement/menu/combat input","replay_files":replay_files}
	value.modules_tested = tested
	# MERGE3: which clip keys were on screen when hits, contacts and attacks landed (presentation audit).
	value.combat_clips = host.combat_audit
	engine_frames.sort()
	frames.sort()
	steady_frames.sort()
	var samples := FileAccess.open(config.output.path_join("timing-samples.json"),FileAccess.WRITE)
	samples.store_string(JSON.stringify({"frame_rows":frame_rows,"monitor_time_process_ms":engine_frames,"monitor_steady_time_process_ms":steady_frames,"await_frame_ms":frames,"boundaries":timing_boundaries})); samples.close()
	value.timing = {"samples":frames.size(),"monitor_steady_samples":steady_frames.size(),"scope":"60 Hz fixed-step. Gate input: per-frame CPU work from timestamp probes (frame_scope). Godot's TIME_PROCESS monitor (1 s window maximum including RenderingServer sync/present waits) is retained as monitor_* for transparency only. No device FPS certification."}
	if not engine_frames.is_empty(): value.timing.monitor_all_frame_p95_ms = engine_frames[mini(engine_frames.size()-1,int(engine_frames.size()*0.95))]
	if not steady_frames.is_empty(): value.timing.monitor_time_process_p95_ms = steady_frames[mini(steady_frames.size()-1,int(steady_frames.size()*0.95))]
	value.timing.merge(frame_timing())
	value.timing["boundaries"] = timing_boundaries
	if DisplayServer.get_name() != "headless" and value.timing.frame_work_p95_ms == null: value.failures.append("no steady rendered performance sample")
	value.memory = {"start_bytes":start_memory,"peak_bytes":peak_memory,"end_bytes":int(Performance.get_monitor(Performance.MEMORY_STATIC)),"scope":"engine static allocator, including temporary destination preflight scene; not OS RSS"}
	value.budget = {"triangles_per_visible_room":6000,"draw_calls_per_room":256,"rendered_p95_ms":33.34}
	var file := FileAccess.open(config.output.path_join("native.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(value,"",true)); file.close()
	if input_file != null: input_file.close()
	print("MODULE_PHYSICAL completed=%s ticks=%d attempts=%d failures=%s" % [completed,tick,host.attempts.size(),str(failures)])
	await view.quit_cleanly()
