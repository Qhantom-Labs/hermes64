extends SceneTree
## CHARSYS: clip import test + golden captures through the shipped runtime path: view/assets.gd (GLTF + N64
## shader), actors/character.gd (STEP playback at 15 fps, blob shadow), SubViewport readback (presenter.capture_low).
## godot --path runtime/godot --script res://tests/charsys_capture.gd -- <job.json>   (graphical Godot required)
const Assets = preload("res://view/assets.gd")
const Actor = preload("res://actors/character.gd")

func _initialize() -> void:
	call_deferred("run_job")

func vec(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])

func col(a: Array) -> Color:
	return Color(a[0], a[1], a[2])

func pose(s: Skeleton3D) -> Array:
	var out := []
	if s == null: return out
	for i in s.get_bone_count(): out.append(s.get_bone_global_pose(i))
	return out

func same_pose(a: Array, b: Array) -> bool:
	if a.size() != b.size(): return false
	for i in a.size():
		var x: Transform3D = a[i]
		var y: Transform3D = b[i]
		if not x.is_equal_approx(y): return false
	return true

func finite_pose(p: Array) -> bool:
	for t in p:
		var tr: Transform3D = t
		if not (is_finite(tr.origin.x) and is_finite(tr.origin.y) and is_finite(tr.origin.z)): return false
	return true

func plane(world: Node3D, size: Vector2, pos: Vector3, rot: Vector3, c: Color) -> void:
	var mi := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = size
	mi.mesh = pm
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = c
	mi.material_override = m
	mi.position = pos
	mi.rotation = rot
	world.add_child(mi)

func run_job() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or DisplayServer.get_name() == "headless":
		push_error("charsys capture requires a graphical Godot")
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
	var room := Node3D.new()
	world.add_child(room)
	room.visible = false
	plane(room, Vector2(12, 12), Vector3(0, 0, 0), Vector3.ZERO, col(job.room.floor))
	plane(room, Vector2(12, 8), Vector3(0, 4, -3.2), Vector3(PI / 2, 0, 0), col(job.room.wall))
	plane(room, Vector2(12, 8), Vector3(-3.4, 4, 0), Vector3(0, 0, -PI / 2), col(job.room.wall))
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.current = true
	var resolver = Assets.new()
	resolver.configure({}, job.get("theme", {}))
	var report := {"ok": true, "characters": [], "renderer": "Godot shipped view/assets.gd + actors/character.gd + N64 shader"}
	for ch in job.characters:
		var scene = resolver.load_row({"path": ch.glb})
		var row := {"id": ch.id, "loaded": scene != null, "clips": [], "frames": []}
		if scene == null:
			report.ok = false
			report.characters.append(row)
			continue
		var actor = Actor.new()
		world.add_child(actor)
		actor.manual_clock = true
		actor.configure(scene, {"character_id": ch.id, "source_rig": ch.rig})
		for fr in ch.frames:  # frames before the clip test: a clip that keys extra bones leaves them posed
			actor.clip = ""
			actor.play_clip(fr.clip)
			for k in int(fr.key): actor.advance_pose(1.0 / 15.0)
			actor.rotation.y = deg_to_rad(float(fr.get("yaw", 0)))
			room.visible = bool(fr.get("room", false))
			camera.position = vec(fr.eye)
			camera.look_at(vec(fr.target), Vector3.UP)
			camera.near = 0.01
			camera.far = 200.0
			if fr.has("ortho"):
				camera.projection = Camera3D.PROJECTION_ORTHOGONAL
				camera.size = fr.ortho
			else:
				camera.projection = Camera3D.PROJECTION_PERSPECTIVE
				camera.fov = fr.get("fov", 62.0)
			for tick in 3: await process_frame
			await RenderingServer.frame_post_draw
			var image := viewport.get_texture().get_image()
			var ok := image != null and not image.is_empty()
			if ok:
				DirAccess.make_dir_recursive_absolute(String(fr.out).get_base_dir())
				ok = image.save_png(fr.out) == OK
			row.frames.append({"out": fr.out, "ok": ok})
			report.ok = report.ok and ok
		actor.clip = ""
		actor.play_clip("idle")
		var idle_pose := pose(actor.skeleton)
		for name in ch.clips:
			var info := {"clip": name, "present": actor.animation != null and actor.animation.has_animation(name)}
			if info.present:
				var a: Animation = actor.animation.get_animation(name)
				info.length = a.length
				info.tracks = a.get_track_count()
				actor.clip = ""
				actor.play_clip(name)
				var p0 := pose(actor.skeleton)
				var moved := false
				var finite := finite_pose(p0)
				for k in 15:
					actor.advance_pose(1.0 / 15.0)
					var pk := pose(actor.skeleton)
					finite = finite and finite_pose(pk)
					if pk != p0: moved = true
				info.moves = moved
				info.finite = finite
				actor.clip = ""
				actor.play_clip("idle")
				info.returns_to_idle = same_pose(pose(actor.skeleton), idle_pose)
				# a held pose (sleep_curled) plays without moving; playing = present, finite, STEP, a real length
				info.ok = finite and info.returns_to_idle and a.length > 0.0 and a.track_get_interpolation_type(0) == Animation.INTERPOLATION_NEAREST
			else:
				info.ok = false
			report.ok = report.ok and info.ok
			row.clips.append(info)
		report.characters.append(row)
		actor.queue_free()
		resolver.cache.clear()
		await process_frame
	FileAccess.open(job.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit(0 if report.ok else 3)
