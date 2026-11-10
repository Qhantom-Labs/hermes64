extends SceneTree
## Bounded production-facade bot: walks around real Thaw furniture/NPCs using
## Actions.submit_frame, not position assignment or direct story dispatch.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Solids = preload("res://view/solid_footprints.gd")
var view
var failures := []
var samples := []
var ticks := 0
var output := ""
var goal := Vector3.ZERO
var path := PackedVector3Array()
var penetration_ticks := 0

func _initialize() -> void: call_deferred("run")
func flat(p: Vector3) -> Vector2: return Vector2(p.x,p.z)
func frame(move := Vector2.ZERO) -> void:
	var digital := []
	for pair in [["move_left",move.x<0],["move_right",move.x>0],["move_up",move.y<0],["move_down",move.y>0]]:
		if pair[1]: digital.append(pair[0])
	view.actions.submit_frame({"digital":digital})
	await physics_frame
	await process_frame
	ticks += 1
	var p: Vector3 = view.player.position
	samples.append([p.x,p.y,p.z,view.player.facing_yaw])
	var shape := CapsuleShape3D.new()
	shape.radius = float(view.player.tuning.capsule_radius_m)-0.005
	shape.height = float(view.player.tuning.capsule_height_m)-0.02
	var q := PhysicsShapeQueryParameters3D.new()
	q.shape = shape; q.exclude = [view.player.get_rid()]
	q.transform = Transform3D(Basis.IDENTITY,view.player.global_position+Vector3.UP*(shape.height/2+0.01))
	if not view.world.get_world_3d().direct_space_state.intersect_shape(q,1).is_empty(): penetration_ticks += 1

func steer(toward: Vector3) -> Vector2:
	var desired := (flat(toward)-flat(view.player.position)).normalized()
	var best := Vector2.ZERO
	var score := -INF
	for x in [-1,0,1]:
		for y in [-1,0,1]:
			if x == 0 and y == 0: continue
			var input := Vector2(x,y)
			var basis: Basis = view.player.latched_basis if view.player.latched else view.player.camera_basis
			if view.player.latched and absf(input.angle_to(view.player.last_input))>float(view.player.tuning.latch_direction_rad): basis = view.player.camera_basis
			var direction: Vector2 = (flat(basis.x).normalized()*x+flat(basis.z).normalized()*y).normalized()
			if direction.dot(desired)>score: score = direction.dot(desired); best = input
	return best

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		if str(arg).begins_with("--output="): output = str(arg).trim_prefix("--output=")
	view = View.new(); root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true,"save":"user://feel2-solid-bot.json","replay_trace":true})
	if not booted.ok: failures.append("ordinary facade boot failed"); await finish(); return
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	# Exercise the documented caller seams pending parent-owned presenter wiring.
	var placed: Dictionary = view.player.place_in_room(view.room_root)
	if not placed.ok: failures.append(str(placed)); await finish(); return
	goal = view.room_root.target_anchors.get("tavi",Vector3.INF)
	if goal == Vector3.INF: failures.append("Thaw production NPC target missing"); await finish(); return
	for i in 12: await frame()
	view.room_root.update_interaction_targets(view.player.position)
	view.checkpoint = view.physical_checkpoint()
	var movie := output.get_base_dir().path_join("native-detour.h64movie.json")
	view.replay.start_record(movie,7)
	var nav = view.player.room_navigation
	path = nav.route(view.player.position,goal,0.65,true)
	if path.is_empty(): failures.append("no collision-free native bot route")
	var index := 0
	var reached := false
	for i in 1200:
		if path.is_empty(): break
		var edge := Solids.target_point(view.room_root.solid_definitions,goal,view.player.position)
		if flat(edge).distance_to(flat(view.player.position)) <= 0.85: reached = true; break
		while index < path.size()-1 and flat(view.player.position).distance_to(flat(path[index]))<0.24 and nav.segment_clear(view.player.position,path[index+1]): index += 1
		await frame(steer(path[index]))
	for i in 18: await frame()
	if not reached: failures.append("bot failed to reach the real NPC from a clear edge within 1200 ticks")
	if penetration_ticks != 0: failures.append("native bot penetrated room solids on %d ticks" % penetration_ticks)
	view.room_root.update_interaction_targets(view.player.position)
	var edge: Vector3 = view.room_root.target_positions.tavi
	var eye: Vector3 = view.player.global_position+Vector3.UP*0.8
	var q := PhysicsRayQueryParameters3D.create(eye,Vector3(edge.x,eye.y,edge.z))
	q.exclude = [view.player.get_rid()]
	if not view.world.get_world_3d().direct_space_state.intersect_ray(q).is_empty(): failures.append("NPC collider occluded the actual edge interaction ray")
	var recorded: Dictionary = view.replay.stop_record()
	if not recorded.ok: failures.append("production movie recording failed "+str(recorded))
	await finish()

func finish() -> void:
	var result := {"ok":failures.is_empty(),"failures":failures,"ticks":ticks,"waypoints":path.size(),"trace_sha256":JSON.stringify(samples,"",true,true).sha256_text(),"penetration_ticks":penetration_ticks,"position":str(view.player.position),"scope":"ordinary production facade + Actions.submit_frame; room-entry/edge caller methods invoked explicitly by harness; not a story win, not a rendered feel verdict"}
	if output != "":
		var file := FileAccess.open(output,FileAccess.WRITE); file.store_string(JSON.stringify(result,"  ",true)); file.close()
	print("FEEL2_SOLID_BOT ",JSON.stringify(result))
	await view.quit_cleanly(0 if result.ok else 1)
