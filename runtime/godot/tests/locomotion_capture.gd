extends SceneTree
## Base locomotion (docs/LOCOMOTION.md) in the engine: frame strips of the baked run and walk, and the planted-boot
## positions while the character travels at changing speed. Shipped path: actors/assets.gd (file parse, locomotion
## block from the file, N64 shader) and actors/character.gd (drive + advance_pose: continuous phase). A file without
## the block is driven exactly as actors/bridge.gd drives it (walk at speed / walk_stride_mps), as the control. A
## character row with "stepped": true plays the baked file on the stepped path (drive_step, the runtime before
## continuous phase): the before numbers and the known-bad control. The world has a ground line with marks every 0.1 m
## (every 0.5 m taller) behind the character, level with the floor.
## godot --path runtime/godot --script res://tests/locomotion_capture.gd -- <job.json>   (graphical Godot required)
const Assets = preload("res://actors/assets.gd")
const Actor = preload("res://actors/character.gd")
const DT := 1.0 / 60.0

func _initialize() -> void:
	call_deferred("run_job")

func vec(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])

func col(a: Array) -> Color:
	return Color(a[0], a[1], a[2])

func box(world: Node3D, size: Vector3, pos: Vector3, c: Color) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = c
	mi.material_override = m
	mi.position = pos
	world.add_child(mi)

## The ground line: a dark band whose top is the floor (y = 0) 0.6 m behind the character's path (x = -0.6), with a mark
## every 0.1 m along the way of travel (z) and a taller one every 0.5 m, from z = -2 to 40 m.
func ground_line(world: Node3D) -> void:
	box(world, Vector3(0.02, 0.03, 42.0), Vector3(-0.6, -0.015, 19.0), Color(0.08, 0.08, 0.1))
	for i in 421:
		var z := -2.0 + 0.1 * float(i)
		var tall := i % 5 == 0
		box(world, Vector3(0.02, 0.06 if tall else 0.025, 0.006 if tall else 0.004), Vector3(-0.6, (0.06 if tall else 0.025) / 2.0, z), Color(0.08, 0.08, 0.1))

func plane(world: Node3D, size: Vector2, pos: Vector3, c: Color) -> void:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = size
	mi.mesh = pm
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = c
	mi.material_override = m
	mi.position = pos
	world.add_child(mi)

## The two lines of actors/bridge.gd for a file without baked locomotion, or drive() for one with it.
func drive(actor, speed: float, walk_stride: float) -> void:
	if actor.locomotion.is_empty():
		actor.pose_speed = speed / walk_stride if speed > 0.05 else 1.0
		actor.play_clip("walk" if speed > 0.05 else "idle")
	else: actor.drive(speed, 0.05)

func sole_points(actor, sole: Dictionary) -> Dictionary:
	var out := {}
	for side in ["l", "r"]:
		var bone: int = actor.skeleton.find_bone("foot_" + side)
		var t: Transform3D = actor.skeleton.global_transform * actor.skeleton.get_bone_global_pose(bone)
		var rows := []
		for q in sole[side]:
			var p: Vector3 = t * vec(q)
			rows.append([p.x, p.y, p.z])
		out[side] = rows
	return out

## The pose as shown, in skeleton space: the same key gives the same numbers wherever the character stands.
func pose_of(actor) -> Array:
	var out := []
	for name in ["foot_l", "foot_r", "thigh_l", "upper_arm_l"]:
		var t: Transform3D = actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone(name))
		for v in [t.origin, t.basis.x, t.basis.y]: out.append_array([snappedf(v.x, 0.00001), snappedf(v.y, 0.00001), snappedf(v.z, 0.00001)])
	return out

func run_job() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or DisplayServer.get_name() == "headless":
		push_error("locomotion capture requires a graphical Godot")
		quit(2)
		return
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var viewport := SubViewport.new()
	viewport.size = Vector2i(job.size[0], job.size[1])
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	var world := Node3D.new()
	viewport.add_child(world)
	var env := WorldEnvironment.new()
	env.environment = Environment.new()
	env.environment.background_mode = Environment.BG_COLOR
	env.environment.background_color = col(job.background)
	world.add_child(env)
	plane(world, Vector2(400, 400), Vector3.ZERO, col(job.floor))
	ground_line(world)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.current = true
	camera.near = 0.01
	camera.far = 200.0
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	var resolver = Assets.new()
	resolver.configure({}, job.get("theme", {}))
	var report := {"ok": true, "characters": [], "engine": Engine.get_version_info().string,
		"path": "actors/assets.gd instance_glb + locomotion_block, actors/character.gd drive + advance_pose"}
	for ch in job.characters:
		var model = resolver.instance_glb(ch.glb)
		var row := {"id": ch.id, "loaded": model != null, "frames": [], "plays": []}
		if model == null:
			report.ok = false
			report.characters.append(row)
			continue
		var actor = Actor.new()
		world.add_child(actor)
		actor.manual_clock = true
		actor.configure(model, {"character_id": ch.id, "source_rig": ch.rig})
		actor.set_locomotion(resolver.locomotion_block(ch.glb))
		if ch.get("stepped", false): actor.loco = {}     # the stepped path: before continuous phase (known-bad control)
		resolver.shade_character(model, actor)
		actor.expression(0)
		row.block = actor.locomotion
		row.continuous = not actor.loco.is_empty()
		if row.continuous:
			row.tables = {"planted": actor.loco.planted, "windows": actor.loco.windows, "start": actor.loco.start, "lo": actor.loco.lo, "clear": actor.loco.clear}
		row.clip_lengths = {}
		for name in ["walk", "run"]:
			if actor.animation.has_animation(name): row.clip_lengths[name] = actor.animation.get_animation(name).length
		# ---- frame strips: every key of one cycle, in place: the key itself (continuous runtime), or through drive() at
		# the cycle's own stride speed (stepped runtime, control)
		for fr in ch.get("frames", []):
			actor.position = Vector3.ZERO
			actor.clip = ""
			actor.play_clip("idle")
			if row.continuous: actor.show_cycle(fr.clip, float(fr.key))
			else:
				drive(actor, float(fr.speed), float(job.walk_stride_mps))
				for k in int(fr.key): actor.advance_pose(1.0 / 15.0)
			actor.rotation.y = deg_to_rad(float(fr.get("yaw", 0)))
			camera.position = vec(fr.eye)
			camera.look_at(vec(fr.target), Vector3.UP)
			camera.size = fr.ortho
			for tick in 3: await process_frame
			await RenderingServer.frame_post_draw
			var image := viewport.get_texture().get_image()
			var ok := image != null and not image.is_empty()
			if ok:
				DirAccess.make_dir_recursive_absolute(String(fr.out).get_base_dir())
				ok = image.save_png(fr.out) == OK
			row.frames.append({"out": fr.out, "ok": ok, "clip": actor.clip, "sample_key": roundi(actor.sample_time * 15.0)})
			report.ok = report.ok and ok
		# ---- play: travel along +z at 60 ticks/s; the speed follows each target with the controller's accel and brake
		actor.rotation.y = 0.0
		for play in ch.get("plays", []):
			actor.position = Vector3.ZERO
			actor.clip = ""
			actor.play_clip("idle")
			var speed := float(play.get("start_mps", 0.0))
			var ticks := []
			var shot := 0
			var gshot := 0
			for seg in play.segments:
				var accel := float(seg.get("accel", job.accel_mps2))
				var brake := float(seg.get("brake", job.brake_mps2))
				for i in int(round(float(seg.seconds) / DT)):
					var target := float(seg.mps)
					speed = minf(target, speed + accel * DT) if target > speed else maxf(target, speed - brake * DT)
					actor.position.z += speed * DT
					drive(actor, speed, float(job.walk_stride_mps))
					actor.advance_pose(DT)
					var rec := {"mps": speed, "z": actor.position.z, "clip": actor.clip, "key": roundi(actor.sample_time * 15.0)}
					rec.pose = pose_of(actor)
					if ch.has("sole"): rec.sole = sole_points(actor, ch.sole)
					ticks.append(rec)
					if play.has("travel") and ticks.size() % int(play.travel.every_ticks) == 0 and shot < int(play.travel.count):
						camera.position = Vector3(float(play.travel.distance), float(play.travel.height), actor.position.z)
						camera.look_at(Vector3(0, float(play.travel.height), actor.position.z), Vector3.UP)
						camera.size = play.travel.ortho
						for tick in 3: await process_frame
						await RenderingServer.frame_post_draw
						var im := viewport.get_texture().get_image()
						var path := "%s-%02d.png" % [play.travel.out, shot]
						DirAccess.make_dir_recursive_absolute(path.get_base_dir())
						report.ok = report.ok and im != null and im.save_png(path) == OK
						shot += 1
					# ground-line strip: the camera stays at one place on the way while the character passes it
					var g: Dictionary = play.get("ground", {})
					if not g.is_empty() and ticks.size() >= int(g.from_tick) and (ticks.size() - int(g.from_tick)) % int(g.every_ticks) == 0 and gshot < int(g.count):
						viewport.size = Vector2i(int(g.size[0]), int(g.size[1]))
						camera.position = Vector3(float(g.distance), float(g.height), float(g.z))
						camera.look_at(Vector3(0, float(g.height), float(g.z)), Vector3.UP)
						camera.size = float(g.ortho)
						for tick in 3: await process_frame
						await RenderingServer.frame_post_draw
						var gim := viewport.get_texture().get_image()
						var gpath := "%s-%02d.png" % [g.out, gshot]
						DirAccess.make_dir_recursive_absolute(gpath.get_base_dir())
						report.ok = report.ok and gim != null and gim.save_png(gpath) == OK
						viewport.size = Vector2i(job.size[0], job.size[1])
						gshot += 1
			row.plays.append({"name": play.name, "ticks": ticks})
		report.characters.append(row)
		actor.queue_free()
		await process_frame
	FileAccess.open(job.report, FileAccess.WRITE).store_string(JSON.stringify(report))
	quit(0 if report.ok else 3)
