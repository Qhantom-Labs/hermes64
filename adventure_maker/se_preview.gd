extends SceneTree
## STYLEENGINE-2 preview (copied into a staged runtime under the project; never part of an exported game).
## Static pieces through the production asset shading (view/assets.gd load_row + shade: N64 world shader, baked /
## unlit material kinds) in the pack's light profile, from fixed angles: front, side, back, top, three-quarter and
## one game-distance view. Writes one PNG per view, one sheet PNG (3 x 2 tiles in that order) and a JSON report.
const ViewAssets = preload("res://view/assets.gd")
const Rig = preload("res://look/rig.gd")
const VIEWS := ["front", "side", "back", "top", "three_quarter", "game"]

var viewport: SubViewport
var world: Node3D
var camera: Camera3D

func _initialize() -> void:
	call_deferred("run_job")

func bounds(root_node: Node3D) -> AABB:
	var box := AABB()
	var started := false
	for n in root_node.find_children("*", "MeshInstance3D", true, false):
		var mi: MeshInstance3D = n
		var mesh: Mesh = mi.mesh
		if mesh == null:
			continue
		for i in mesh.get_surface_count():
			var arrays: Array = mesh.surface_get_arrays(i)
			for v in arrays[Mesh.ARRAY_VERTEX]:
				var p: Vector3 = mi.global_transform * v
				if not started:
					box = AABB(p, Vector3.ZERO)
					started = true
				else:
					box = box.expand(p)
	return box

func view_dir(name: String) -> Vector3:
	# glTF axes: +Y up, the piece's front faces +Z (meshkit front -Y)
	match name:
		"front": return Vector3(0.0, 0.18, 1.0).normalized()
		"side": return Vector3(1.0, 0.18, 0.0).normalized()
		"back": return Vector3(0.0, 0.18, -1.0).normalized()
		"top": return Vector3(0.0, 1.0, 0.02).normalized()
		"three_quarter": return Vector3(0.62, 0.45, 0.78).normalized()
	return Vector3(0.45, 0.5, 0.74).normalized()

func frame_distance(box: AABB, dir: Vector3, up: Vector3) -> float:
	var center := box.get_center()
	var right := up.cross(dir).normalized()
	var true_up := dir.cross(right).normalized()
	var tan_v := tan(deg_to_rad(camera.fov) * 0.5)
	var aspect := float(viewport.size.x) / float(viewport.size.y)
	var distance := 0.0
	for i in 8:
		var delta: Vector3 = box.get_endpoint(i) - center
		var depth := delta.dot(dir)
		distance = maxf(distance, depth + absf(delta.dot(right)) / (tan_v * aspect) * 1.12)
		distance = maxf(distance, depth + absf(delta.dot(true_up)) / tan_v * 1.12)
	return maxf(distance, 0.6)

func run_job() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 1 or DisplayServer.get_name() == "headless":
		push_error("A graphical Godot and one job path are required")
		quit(2)
		return
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var theme: Dictionary = job.get("theme", {})
	var tile: int = int(job.get("tile", 320))
	viewport = SubViewport.new()
	viewport.size = Vector2i(tile, tile)
	viewport.own_world_3d = true
	viewport.msaa_3d = Viewport.MSAA_DISABLED
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	root.add_child(viewport)
	world = Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(job.get("background", "#8e9399"))
	world.add_child(environment)
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new()
	pm.size = Vector2(400, 400)
	ground.mesh = pm
	var neutral := StandardMaterial3D.new()
	neutral.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	neutral.albedo_color = Color(job.get("ground", "#6f747a"))
	ground.material_override = neutral
	ground.position.y = -0.002
	world.add_child(ground)
	camera = Camera3D.new()
	world.add_child(camera)
	camera.current = true
	camera.fov = 40.0
	camera.near = 0.02
	camera.far = 600.0
	var resolver = ViewAssets.new()
	resolver.configure({}, theme)
	if Rig.has_look(theme):
		Rig.apply(Rig.profile(theme, String(job.get("profile", "exterior"))), [])
	var report := {"ok": true, "engine": Engine.get_version_info(), "renderer": RenderingServer.get_current_rendering_method(),
		"views": VIEWS, "pieces": []}
	for piece in job.pieces:
		var holder := Node3D.new()
		world.add_child(holder)
		var loaded := 0
		for part in piece.parts:
			var node: Node3D = resolver.load_row({"path": part.glb})
			if node == null:
				continue
			holder.add_child(node)
			var at: Array = part.get("at", [0.0, 0.0, 0.0])
			node.position = Vector3(float(at[0]), float(at[1]), float(at[2]))
			node.rotation.y = deg_to_rad(float(part.get("yaw", 0.0)))
			var sc: float = float(part.get("scale", 1.0))
			node.scale = Vector3(sc, sc, sc)
			loaded += 1
		if loaded == 0:
			report.ok = false
			report.pieces.append({"id": piece.id, "ok": false, "reason": "GLB failed to load"})
			holder.queue_free()
			continue
		for tick in 3:
			await process_frame
		var box := bounds(holder)
		var center := box.get_center()
		var sheet := Image.create(tile * 3, tile * 2, false, Image.FORMAT_RGBA8)
		var shots := {}
		var ok := true
		for vi in VIEWS.size():
			var name: String = VIEWS[vi]
			var dir := view_dir(name)
			var up := Vector3(0, 0, -1) if name == "top" else Vector3.UP
			if name == "game":
				camera.fov = 60.0
				var d := maxf(6.5, box.get_longest_axis_size() * 1.6)
				camera.position = Vector3(center.x, box.position.y, center.z) + dir * d
			else:
				camera.fov = 40.0
				camera.position = center + dir * frame_distance(box, dir, up)
			camera.look_at(center, up)
			for tick in 3:
				await process_frame
			await RenderingServer.frame_post_draw
			var image := viewport.get_texture().get_image()
			if image == null or image.is_empty():
				ok = false
				continue
			image.convert(Image.FORMAT_RGBA8)
			var out: String = String(piece.out_dir) + "/" + name + ".png"
			if image.save_png(out) != OK:
				ok = false
			shots[name] = out
			sheet.blit_rect(image, Rect2i(0, 0, tile, tile), Vector2i((vi % 3) * tile, (vi / 3) * tile))
		var sheet_path: String = String(piece.out_dir) + "/sheet.png"
		if sheet.save_png(sheet_path) != OK:
			ok = false
		report.pieces.append({"id": piece.id, "ok": ok, "loaded": loaded, "shots": shots, "sheet": sheet_path,
			"size_m": [box.size.x, box.size.y, box.size.z], "center": [center.x, center.y, center.z]})
		report.ok = report.ok and ok
		print("PREVIEW ", piece.id, " ", ok)
		holder.queue_free()
		resolver.clear_caches()
		await process_frame
	FileAccess.open(job.report, FileAccess.WRITE).store_string(JSON.stringify(report, "\t"))
	quit(0 if report.ok else 3)
