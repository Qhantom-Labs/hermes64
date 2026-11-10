extends SceneTree
## Static/reference proof capture using the shipped GLTF resolver and N64 shader.
## Same SubViewport/readback mechanism as presenter.capture_low, no art approval.
const Assets = preload("res://view/assets.gd")

func _initialize() -> void:
	call_deferred("run_job")

func vec(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])

func freeze_scroll(node: Node) -> void:
	if node is MeshInstance3D:
		for i in node.mesh.get_surface_count():
			var mat = node.get_active_material(i)
			if mat is ShaderMaterial: mat.set_shader_parameter("uv_scroll", Vector2.ZERO)
	for child in node.get_children(): freeze_scroll(child)

func run_job() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or DisplayServer.get_name() == "headless":
		push_error("Capture requires a graphical Godot; configure godot_path")
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
	env.environment.background_color = Color(0.06, 0.07, 0.09)
	world.add_child(env)
	var camera := Camera3D.new()
	world.add_child(camera)
	camera.current = true
	var resolver = Assets.new()
	var report := {"ok":true,"frames":[],"renderer":"Godot shipped assets.gd + N64 shader"}
	for frame in job.frames:
		resolver.configure({}, frame.theme)
		var group := Node3D.new()
		world.add_child(group)
		var loaded := 0
		for piece in frame.pieces:
			var node = resolver.load_row({"path":piece.glb})
			if node == null:
				report.ok = false
				continue
			group.add_child(node)
			node.position = vec(piece.get("pos", [0,0,0]))
			node.rotation.y = deg_to_rad(float(piece.get("rot_y_deg",0)))
			freeze_scroll(node)
			loaded += 1
		camera.position = vec(frame.eye)
		camera.look_at(vec(frame.target), Vector3.UP)
		camera.near = 0.01
		camera.far = 500.0
		if frame.has("ortho"):
			camera.projection = Camera3D.PROJECTION_ORTHOGONAL
			camera.size = frame.ortho
		else:
			camera.projection = Camera3D.PROJECTION_PERSPECTIVE
			camera.fov = frame.get("fov", 70.0)
		for tick in 4: await process_frame
		await RenderingServer.frame_post_draw
		var image := viewport.get_texture().get_image()
		var ok := image != null and not image.is_empty()
		if ok:
			DirAccess.make_dir_recursive_absolute(frame.out.get_base_dir())
			ok = image.save_png(frame.out) == OK
		report.frames.append({"out":frame.out,"ok":ok,"loaded":loaded,"expected":frame.pieces.size()})
		report.ok = report.ok and ok and loaded == frame.pieces.size()
		group.queue_free()
		resolver.cache.clear()
		await process_frame
	FileAccess.open(job.report,FileAccess.WRITE).store_string(JSON.stringify(report,"\t"))
	quit(0 if report.ok else 3)
