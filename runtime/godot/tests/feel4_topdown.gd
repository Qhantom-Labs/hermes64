extends SceneTree
## FEEL4 evidence: top-down orthographic frame of every room (800x800, no UI), with the runtime's walkable boundary
## (inset by the capsule radius) drawn as a thin line and the door/objective targets as dots. Presentation only.
##   --output=<folder>
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var view

func _initialize() -> void: call_deferred("run")

func line_mesh(points: PackedVector3Array, color: Color) -> MeshInstance3D:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_LINES)
	for i in points.size():
		st.set_color(color); st.add_vertex(points[i])
		st.set_color(color); st.add_vertex(points[(i + 1) % points.size()])
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.vertex_color_use_as_albedo = true
	m.no_depth_test = true
	m.render_priority = 10
	mi.material_override = m
	return mi

func run() -> void:
	var out := ""
	for arg in OS.get_cmdline_user_args():
		if str(arg).begins_with("--output="): out = str(arg).trim_prefix("--output=")
	DirAccess.make_dir_recursive_absolute(out)
	view = View.new(); root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true, "scenes": "off", "save": "user://feel4-topdown.json"})
	if not booted.ok: print("BOOT FAILED ", booted); quit(2); return
	var ids: Array = view.runtime.rooms.keys(); ids.sort()
	for id in ids:
		view.runtime.state.location = id
		view.enter_room("")
		await physics_frame
		var room: Dictionary = view.runtime.rooms[id]
		var w: float = room.grid_size[0]; var d: float = room.grid_size[1]
		var sv := SubViewport.new()
		sv.size = Vector2i(800, 800)
		sv.world_3d = view.viewport.find_world_3d()
		sv.render_target_update_mode = SubViewport.UPDATE_ALWAYS
		var cam := Camera3D.new()
		cam.projection = Camera3D.PROJECTION_ORTHOGONAL
		cam.size = maxf(w, d) + 2.0
		cam.near = 0.05; cam.far = 80.0
		cam.position = Vector3(w / 2.0, 40.0, d / 2.0)
		cam.rotation = Vector3(-PI / 2.0, 0.0, 0.0)
		sv.add_child(cam)
		root.add_child(sv)
		cam.current = true
		var marks := Node3D.new()
		view.room_root.add_child(marks)
		var inset: PackedVector2Array = view.player.boundary_inset if view.player.boundary_inset.size() >= 3 else view.room_root.boundary_outline
		var pts := PackedVector3Array()
		for p in inset: pts.append(Vector3(p.x, 0.25, p.y))
		if pts.size() >= 3: marks.add_child(line_mesh(pts, Color(0.2, 1.0, 0.3)))
		var grid := PackedVector3Array([Vector3(0, 0.25, 0), Vector3(w, 0.25, 0), Vector3(w, 0.25, d), Vector3(0, 0.25, d)])
		marks.add_child(line_mesh(grid, Color(1.0, 0.3, 0.3)))
		for key in view.room_root.target_anchors:
			if not str(key).begins_with("move:"): continue
			var t: Vector3 = view.room_root.target_anchors[key]
			var s := 0.25
			marks.add_child(line_mesh(PackedVector3Array([t + Vector3(-s, 0.3, -s), t + Vector3(s, 0.3, -s), t + Vector3(s, 0.3, s), t + Vector3(-s, 0.3, s)]), Color(1, 1, 0.2)))
		for k in 4: await process_frame
		await RenderingServer.frame_post_draw
		var img := sv.get_texture().get_image()
		if img != null: img.save_png(out.path_join(id + "-top.png"))
		marks.queue_free()
		sv.queue_free()
		await process_frame
	print("FEEL4_TOPDOWN done ", ids.size())
	await view.quit_cleanly(0)
