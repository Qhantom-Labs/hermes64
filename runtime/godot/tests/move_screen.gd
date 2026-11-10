extends SceneTree
## MOVE: scripted real-key walks. Every rendered frame, the on-screen direction
## of the held W/A/S/D intent (and of settled actual travel) must agree with the
## expected screen direction: W up / away, S down / toward, A left, D right.
## Uses only APIs present in cam-lane 15ab667a so the old code is a valid control.
const Room = preload("res://view/room.gd")
const THRESHOLD := 0.3
const SETTLE_TICKS := 15
var view
var held := {}
var since_change := 0
var rows := []
var scenario := ""
var stats := {}
var scenarios_order := []
var output := ""
var stalled := false

func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--output="): output = arg.trim_prefix("--output=")
	call_deferred("run")

func key(code: int, down: bool) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code; event.keycode = code; event.pressed = down
	Input.parse_input_event(event)
	if down: held[code] = true
	else: held.erase(code)
	since_change = 0

func mouse_button(down: bool) -> void:
	var event := InputEventMouseButton.new()
	event.button_index = MOUSE_BUTTON_LEFT; event.pressed = down; event.position = Vector2(400,300)
	Input.parse_input_event(event)

func drag(amount: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = Vector2(400,300); event.relative = amount; event.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(event)

func release_all() -> void:
	for code in held.keys(): key(code,false)

func expected_screen() -> Vector2:
	var e := Vector2.ZERO
	# last_wins opposite rule: the test never holds opposite keys simultaneously
	# for longer than the single press tick, so a plain sum is the expectation.
	if held.has(KEY_W): e.y -= 1
	if held.has(KEY_S): e.y += 1
	if held.has(KEY_A): e.x -= 1
	if held.has(KEY_D): e.x += 1
	return e.normalized()

func screen_dir(cam: Camera3D, at: Vector3, world: Vector3) -> Vector2:
	world.y = 0.0
	if world.length() < 0.0001: return Vector2.ZERO
	var a := cam.unproject_position(at)
	var b := cam.unproject_position(at + world.normalized() * 0.5)
	return (b - a).normalized()

func sample() -> void:
	if not stats.has(scenario): return
	var s: Dictionary = stats[scenario]
	if view.room_transition != null and view.room_transition.active(): s.masked += 1; return
	if view.actions.context != "gameplay": s.masked += 1; return
	var e := expected_screen()
	if e == Vector2.ZERO: return
	# The drawn camera. (process_frame fires before _process, when the fixed-
	# tick candidate is transiently `current`; the render rig draws the frame.)
	var cam: Camera3D = view.follow_camera.render_camera
	var at: Vector3 = view.player.global_position + Vector3.UP * 0.8
	var desired: Vector3 = view.player.desired_velocity
	desired.y = 0
	# since_change == 0: the key event is parsed but no 60 Hz tick has sampled
	# it yet (a >60 Hz render precedes the tick); intent is still the old key's.
	if desired.length() > 0.05 and since_change >= 1:
		var d := screen_dir(cam,at,desired).dot(e)
		s.frames += 1
		s.min_intent = minf(s.min_intent,d)
		if d < THRESHOLD:
			s.intent_fail += 1
			if s.fail_log.size() < 6:
				var rb: Vector3 = cam.global_basis.z
				var lb: Basis = view.player.latched_basis
				s.fail_log.append({"tick":view.actions.tick,"dot":snappedf(d,0.001),"keys":held.keys(),"follow_yaw":snappedf(view.follow_camera.yaw,0.001),"render_yaw":snappedf(atan2(rb.x,rb.z),0.001),"latched":view.player.latched,"latched_yaw":snappedf(atan2(lb.z.x,lb.z.z),0.001),"recentering":view.follow_camera.recentering,"pos":[snappedf(at.x,0.01),snappedf(at.z,0.01)],"desired":[snappedf(desired.x,0.01),snappedf(desired.z,0.01)],"since":since_change,"cam":str(cam.name),"frame_heading":view.actions.last_frame.get("heading"),"heading_yaw":view.follow_camera.get("heading_yaw")})
	var actual: Vector3 = view.player.actual_velocity
	actual.y = 0
	if since_change >= SETTLE_TICKS and actual.length() > 0.3 and desired.length() > 0.05 and actual.normalized().dot(desired.normalized()) > 0.9:
		var d2 := screen_dir(cam,at,actual).dot(e)
		s.actual_frames += 1
		s.min_actual = minf(s.min_actual,d2)
		if d2 < THRESHOLD: s.actual_fail += 1

func tick(n: int) -> void:
	# Count simulation ticks; sample every rendered frame in between.
	var target: int = view.actions.tick + n
	var frames := 0
	while view.actions.tick < target:
		# Room transitions legitimately hold the simulation clock (bounded).
		frames += 1
		if frames > n * 8 + 600:
			print("MOVE_SCREEN_STALL scenario=",scenario," tick=",view.actions.tick," context=",view.actions.context)
			stalled = true
			return
		var before: int = view.actions.tick
		await process_frame
		since_change += view.actions.tick - before
		sample()

func begin(name: String) -> void:
	release_all()
	await tick(20)
	scenario = name; scenarios_order.append(name)
	print("MOVE_SCREEN_PROGRESS ",name," tick=",view.actions.tick," room=",view.runtime.state.location," context=",view.actions.context)
	stats[name] = {"frames":0,"intent_fail":0,"min_intent":2.0,"actual_frames":0,"actual_fail":0,"min_actual":2.0,"masked":0,"fail_log":[],"room_before":view.runtime.state.location}
	centre_player()
	await tick(5)

func centre_player() -> void:
	var size: Array = view.runtime.rooms[view.runtime.state.location].grid_size
	view.player.position = Vector3(float(size[0])/2.0,0.1,float(size[1])/2.0)
	view.player.velocity = Vector3.ZERO
	var f = view.follow_camera
	if f.has_meta("room_key"): f.remove_meta("room_key")
	f.reset()

func finish_scenario() -> void:
	release_all()
	stats[scenario]["room_after"] = view.runtime.state.location
	await tick(10)

func run() -> void:
	view = load("res://main.tscn").instantiate(); root.add_child(view)
	for i in 30: await physics_frame
	await process_frame
	view.follow_camera.enabled = true
	# Dismiss opening narration/dialogue with real Enter presses.
	for i in 40:
		if view.actions.context == "gameplay" and not view.n64_ui.dlg_on: break
		key(KEY_ENTER,true); for k in 3: await physics_frame
		key(KEY_ENTER,false); for k in 6: await physics_frame
	var start_room: String = view.runtime.state.location

	await begin("straight_w")
	key(KEY_W,true); await tick(150)
	await finish_scenario()

	await begin("hard_reversal_w_to_s")
	key(KEY_W,true); await tick(120)
	key(KEY_S,true); key(KEY_W,false); await tick(180)
	await finish_scenario()

	await begin("hold_s_from_rest")
	key(KEY_S,true); await tick(240)
	await finish_scenario()

	await begin("strafe_a")
	key(KEY_A,true); await tick(240)
	await finish_scenario()

	await begin("circle_w_tap_d")
	key(KEY_W,true)
	for i in 8:
		await tick(30); key(KEY_D,true); await tick(15); key(KEY_D,false)
	await finish_scenario()

	await begin("orbit_keys_while_walking")
	key(KEY_W,true); await tick(30)
	key(KEY_L,true); await tick(150); key(KEY_L,false)
	await tick(30); key(KEY_W,false)
	key(KEY_S,true); await tick(20)
	key(KEY_J,true); await tick(150); key(KEY_J,false)
	await tick(30)
	await finish_scenario()

	await begin("mouse_orbit_while_walking")
	key(KEY_S,true); await tick(20)
	mouse_button(true)
	for i in 60:
		drag(Vector2(40,0)); await tick(1)
	mouse_button(false)
	await tick(60)
	await finish_scenario()

	await begin("recenter_while_walking")
	key(KEY_A,true); await tick(120); key(KEY_A,false)
	key(KEY_S,true); await tick(10)
	key(KEY_V,true); await tick(2); key(KEY_V,false)
	await tick(200)
	await finish_scenario()

	await begin("door_transition")
	var door_ok := await walk_through_door()
	stats[scenario]["door_crossed"] = door_ok
	await finish_scenario()

	var failures := []
	for name in scenarios_order:
		var s: Dictionary = stats[name]
		if s.frames == 0 and s.get("door_available",true): failures.append(name + ": no measured frames")
		if s.intent_fail > 0: failures.append(name + ": intent screen-direction failures " + str(s.intent_fail))
		if s.actual_fail > 0: failures.append(name + ": actual screen-direction failures " + str(s.actual_fail))
	var door_row: Dictionary = stats["door_transition"]
	if door_row.get("door_available",false) and not door_row.get("door_crossed",false): failures.append("door_transition: open door not crossed")
	if stalled: failures.append("simulation tick stalled during a scenario")
	var report := {"ok":failures.is_empty(),"failures":failures,"fps":Engine.max_fps,"physics_ticks":Engine.physics_ticks_per_second,"threshold":THRESHOLD,"start_room":start_room,"scenarios":stats,"order":scenarios_order}
	print("MOVE_SCREEN ",JSON.stringify(report))
	if output != "":
		var f := FileAccess.open(output,FileAccess.WRITE); f.store_string(JSON.stringify(report,"  ")); f.close()
	view.queue_free()
	for i in 5: await process_frame
	quit(0 if failures.is_empty() else 3)

func walk_through_door() -> bool:
	var room_id: String = view.runtime.state.location
	var room: Dictionary = view.runtime.rooms[room_id]
	if room.doors.is_empty(): return false
	var door: Dictionary = room.doors[0]
	var available := []
	for a in view.ui_actions: available.append(str(a.id))
	var open := false
	for candidate_door in room.doors:
		if ("move:"+room_id+":"+str(candidate_door.id)) in available: door = candidate_door; open = true; break
	stats[scenario]["available"] = available
	# A story-locked start room (Relay hub) has no open door: recorded, not faked.
	stats[scenario]["door_available"] = open
	if not open: return false
	var at: Vector3 = view.room_root.target_anchors.get("move:"+room_id+":"+str(door.id),Room.door_position(door,room.grid_size))
	var centre := Vector3(float(room.grid_size[0])/2.0,0.1,float(room.grid_size[1])/2.0)
	# Start 2.2m inside the door along the door->centre line.
	var inward := (centre - Vector3(at.x,0.1,at.z)); inward.y = 0
	view.player.position = Vector3(at.x,0.1,at.z) + inward.normalized() * minf(2.2,inward.length())
	view.player.velocity = Vector3.ZERO
	var f = view.follow_camera
	if f.has_meta("room_key"): f.remove_meta("room_key")
	f.reset()
	await tick(10)
	# Choose the key whose on-screen direction best matches the door on screen.
	var cam: Camera3D = view.follow_camera.render_camera
	var to_door: Vector2 = screen_dir(cam,view.player.global_position,Vector3(at.x,0.1,at.z)-view.player.global_position)
	var best := KEY_W; var best_dot := -2.0
	for pair in [[KEY_W,Vector2(0,-1)],[KEY_S,Vector2(0,1)],[KEY_A,Vector2(-1,0)],[KEY_D,Vector2(1,0)]]:
		if to_door.dot(pair[1]) > best_dot: best_dot = to_door.dot(pair[1]); best = pair[0]
	key(best,true)
	var guard := 0
	var pressed := false
	while view.runtime.state.location == room_id and guard < 600:
		# The transition freezes the clock until input is neutral: stop waiting
		# on ticks once it starts (released below).
		if view.room_transition != null and view.room_transition.active(): break
		await tick(1); guard += 1
		# Doors are contextual (E) portals: press E once the door is the
		# candidate, while STILL holding the walk key through the transition.
		var cand: Dictionary = view.current_candidate
		if not stats[scenario].has("candidates"): stats[scenario]["candidates"] = {}
		stats[scenario]["candidates"][str(cand.get("id",""))] = true
		if not pressed and str(cand.get("id","")).begins_with("move:"):
			# Frames, not ticks: the portal freezes the clock immediately.
			key(KEY_E,true)
			for k in 8: await physics_frame
			key(KEY_E,false); pressed = true
			since_change = SETTLE_TICKS # E is not a movement change
	stats[scenario]["door"] = {"room":room_id,"door":str(door.id),"wall":str(door.get("wall","")),"at":[at.x,at.z],"key":best,"end":[view.player.position.x,view.player.position.z],"grid":room.grid_size}
	# The (unchanged) transition releases only on neutral input: let go, wait
	# for the reveal to finish, then press W in the new room and measure it.
	release_all()
	var frames := 0
	while view.room_transition != null and view.room_transition.active() and frames < 3000:
		await process_frame; frames += 1
	stats[scenario]["transition_frames"] = frames
	stats[scenario]["transition_released"] = not (view.room_transition != null and view.room_transition.active())
	await tick(10)
	key(KEY_W,true); await tick(90)
	return view.runtime.state.location != room_id and stats[scenario]["transition_released"]
