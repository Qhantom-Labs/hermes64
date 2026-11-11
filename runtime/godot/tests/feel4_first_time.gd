extends SceneTree
## FEEL4 "first-time player" probe (windowed: needs rendering for frames). Boots the staged game with its scene
## cards, then plays like a newcomer who knows nothing about the level:
##   1. title cards play out; gameplay gets control on the roof; NO input for 3 s; frames at 0/1/2/3 s
##   2. measures the route: spawn -> exit door distance, door/marker on screen at spawn (frustum + projected size)
##   3. walks toward the goal (the marker's goal when a cue exists, else the room's only forward door) with bot
##      steering over the room navigation grid, presses E there, waits through the scene cards
##   4. in the canyon: same again for the wave start posts; presses E; frame when the wave has started
## Inputs go through Actions.submit_frame only. Writes <out>/first-time.json and PNG frames.
##   --output=<folder>  --label=<before|after>
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var view
var out := ""
var label := "probe"
var report := {"frames": [], "phases": [], "failures": []}
var tick := 0

func _initialize() -> void: call_deferred("run")

func frame(digital: Array) -> void:
	view.actions.submit_frame({"digital": digital})
	await physics_frame
	await process_frame
	tick += 1

func shot(name: String) -> void:
	var path := out.path_join("%s-%s.png" % [label, name])
	await view.capture(path)
	report.frames.append({"name": name, "tick": tick, "room": view.runtime.state.location, "file": path.get_file(), "cue": cue_state()})

func cue_state() -> Variant:
	var cue = view.world.get_node_or_null("goal_cue")
	if cue == null: return null
	var r: Dictionary = cue.report()
	var cam: Camera3D = view.get_viewport().get_camera_3d() if view.get_viewport() != null else null
	cam = view.drawing_camera() if view.has_method("drawing_camera") else cam
	if r.at != null and cam != null:
		var at := Vector3(r.at[0], 0.05, r.at[2])
		var top := at + Vector3.UP * 5.0
		r["ring_on_screen"] = cam.is_position_in_frustum(at)
		r["beam_on_screen"] = cam.is_position_in_frustum(top) or cam.is_position_in_frustum(at + Vector3.UP * 2.0)
		if not cam.is_position_behind(at): r["ring_px"] = [snappedf(cam.unproject_position(at).x, 0.1), snappedf(cam.unproject_position(at).y, 0.1)]
		r["viewport"] = [cam.get_viewport().get_visible_rect().size.x, cam.get_viewport().get_visible_rect().size.y]
	r.erase("log")
	return r

## Door/goal visibility from the drawn camera: frustum + projected height of a 3 m tall opening.
func visibility(at: Vector3) -> Dictionary:
	var cam: Camera3D = view.drawing_camera()
	var base := Vector3(at.x, 0.0, at.z)
	var top := base + Vector3.UP * 3.0
	var row := {"in_frustum": cam.is_position_in_frustum(base + Vector3.UP * 1.5), "distance_m": snappedf(Vector2(view.player.position.x - at.x, view.player.position.z - at.z).length(), 0.01)}
	if not cam.is_position_behind(base) and not cam.is_position_behind(top):
		var a := cam.unproject_position(base); var b := cam.unproject_position(top)
		row["px_height"] = snappedf(absf(a.y - b.y), 0.1)
		row["px"] = [snappedf(a.x, 0.1), snappedf(a.y, 0.1)]
		var vp: Vector2 = cam.get_viewport().get_visible_rect().size
		row["viewport"] = [vp.x, vp.y]
		row["on_screen"] = a.x >= 0 and a.x <= vp.x and b.y <= vp.y and a.y >= 0
	return row

func goal_for_room() -> Dictionary:
	var cue = view.world.get_node_or_null("goal_cue")
	if cue != null and not cue.goal.is_empty(): return {"id": cue.goal.id, "at": cue.goal.at, "source": "cue"}
	# No cue (before build): the room's forward target, computed the same way the cue would (probe knowledge).
	var probe_cue = load("res://view/goal_cue.gd")
	if probe_cue != null:
		var tmp = probe_cue.new(); tmp.view = view
		var g: Dictionary = tmp.find_goal(); tmp.free()
		if not g.is_empty(): return {"id": g.id, "at": g.at, "source": "probe"}
	return {}

func steer_keys(toward: Vector2) -> Array:
	var desired := (toward - Vector2(view.player.position.x, view.player.position.z)).normalized()
	var basis: Basis = view.player.latched_basis if view.player.latched else view.player.camera_basis
	var right := Vector2(basis.x.x, basis.x.z).normalized()
	var back := Vector2(basis.z.x, basis.z.z).normalized()
	var best := Vector2.ZERO
	var score := -INF
	for x in [-1, 0, 1]:
		for y in [-1, 0, 1]:
			if x == 0 and y == 0: continue
			var d: Vector2 = (right * x + back * y).normalized()
			if d.dot(desired) > score: score = d.dot(desired); best = Vector2(x, y)
	var keys := ["run"]
	if best.x < 0: keys.append("move_left")
	if best.x > 0: keys.append("move_right")
	if best.y < 0: keys.append("move_up")
	if best.y > 0: keys.append("move_down")
	return keys

func walk_to(at: Vector3, max_ticks: int, shots_every := 0, shot_prefix := "") -> int:
	var started := tick
	var path: PackedVector3Array = view.player.room_navigation.route(view.player.position, at, 0.5, false)
	path.append(at)
	var i := 0
	while tick - started < max_ticks:
		var p := Vector2(view.player.position.x, view.player.position.z)
		if p.distance_to(Vector2(at.x, at.z)) <= 0.6: break
		while i < path.size() - 1 and p.distance_to(Vector2(path[i].x, path[i].z)) < 0.35: i += 1
		await frame(steer_keys(Vector2(path[i].x, path[i].z)))
		if shots_every > 0 and (tick - started) % shots_every == 0: await shot("%s-%d" % [shot_prefix, (tick - started) / shots_every])
	for k in 6: await frame([])
	return tick - started

func wait_gameplay(max_ticks: int) -> int:
	var started := tick
	while tick - started < max_ticks:
		var busy: bool = (view.scene_cards != null and str(view.scene_cards.phase) != "idle") or (view.room_transition != null and view.room_transition.active()) or (view.module_host != null and not view.module_host.pending.is_empty()) or view.actions.context != "gameplay"
		if not busy and tick - started > 2: break
		await frame([])
	return tick - started

func press(action: String) -> void:
	await frame([action])
	await frame([])

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		if str(arg).begins_with("--output="): out = str(arg).trim_prefix("--output=")
		if str(arg).begins_with("--label="): label = str(arg).trim_prefix("--label=")
	DirAccess.make_dir_recursive_absolute(out)
	view = View.new(); root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true, "save": "user://feel4-first.json"})
	if not booted.ok: report.failures.append("boot " + str(booted)); await finish(); return
	view.actions.configure({"version": 1}); view.actions.set_source("bot")
	var t_cards := await wait_gameplay(3000)
	report.phases.append({"phase": "opening cards", "ticks": t_cards, "room": view.runtime.state.location})
	report["spawn"] = [view.player.position.x, view.player.position.z]
	var g := goal_for_room()
	report["roof_goal"] = {"id": g.get("id", ""), "at": [g.at.x, g.at.z] if g.get("at") is Vector3 else null, "source": g.get("source", "")}
	if g.get("at") is Vector3: report["roof_goal_visibility_at_spawn"] = visibility(g.at)
	var door_node = null
	for n in view.room_root.get_children():
		if str(n.get_meta("placed", "")) == "door": door_node = n
	if door_node != null:
		var box: AABB = view.room_root.world_aabb(door_node)
		report["door_portal"] = {"position": [door_node.position.x, door_node.position.z], "size_m": [snappedf(box.size.x, 0.01), snappedf(box.size.y, 0.01), snappedf(box.size.z, 0.01)],
			"visibility_at_spawn": visibility(door_node.position)}
	await shot("roof-t0")
	for s in 3:
		for k in 60: await frame([])
		await shot("roof-t%d" % (s + 1))
	if not g.get("at") is Vector3: report.failures.append("no roof goal"); await finish(); return
	# Pause screen (Esc): the existing settings panel, plus (FEEL4 games) the full keycap list under it.
	await press("menu")
	for k in 10: await frame([])
	await shot("pause")
	report["pause_open"] = view.belt.settings_open
	await press("menu")
	for k in 10: await frame([])
	var t_walk := await walk_to(g.at, 900, 150, "roof-walk")
	report.phases.append({"phase": "walk to roof goal", "ticks": t_walk, "end_distance_m": snappedf(Vector2(view.player.position.x - g.at.x, view.player.position.z - g.at.z).length(), 0.01)})
	await shot("roof-door-approach")
	var before_room: String = view.runtime.state.location
	await press("primary")
	var t_gloat := await wait_gameplay(4000)
	report.phases.append({"phase": "door + scene cards", "ticks": t_gloat, "room": view.runtime.state.location, "scenes_played": view.scene_cards.played.keys() if view.scene_cards != null else []})
	if view.runtime.state.location == before_room: report.failures.append("E at the roof goal did not leave the roof"); await finish(); return
	for k in 30: await frame([])
	await shot("canyon-arrival")
	var cg := goal_for_room()
	report["canyon_goal"] = {"id": cg.get("id", ""), "at": [cg.at.x, cg.at.z] if cg.get("at") is Vector3 else null}
	if cg.get("at") is Vector3:
		report["canyon_goal_visibility_at_arrival"] = visibility(cg.at)
		var t2 := await walk_to(cg.at, 900)
		report.phases.append({"phase": "walk to canyon goal", "ticks": t2})
		await press("primary")
		for k in 50: await frame([])
		var active: String = str(view.runtime.state.modules.get("active", ""))
		report.phases.append({"phase": "wave start", "active": active, "robots": view.module_host.combat.enemies.size() if view.module_host != null and view.module_host.combat != null else 0})
		await shot("canyon-wave-start")
		if active == "": report.failures.append("E at the canyon goal did not start the wave")
	await finish()

func finish() -> void:
	var cue = view.world.get_node_or_null("goal_cue") if view != null else null
	report["cue_log"] = cue.log if cue != null else null
	var hint = view.viewport.get_node_or_null("controls_hint") if view != null else null
	report["controls_hint"] = hint.report() if hint != null else null
	report["ok"] = report.failures.is_empty()
	var f := FileAccess.open(out.path_join("%s-first-time.json" % label), FileAccess.WRITE); f.store_string(JSON.stringify(report, "  ", true)); f.close()
	print("FEEL4_FIRST_TIME ", JSON.stringify({"ok": report.ok, "failures": report.failures, "phases": report.phases}))
	await view.quit_cleanly(0 if report.ok else 3)
