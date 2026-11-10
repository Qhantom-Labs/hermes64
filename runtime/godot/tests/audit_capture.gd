extends "res://main.gd"
## STYLE AUDIT views (adventure_maker/audit.py). Run as the scene res://tests/audit_main.tscn with the ordinary
## main.gd arguments plus --screens=DIR [--audit_views=N]. For every room it first saves up to N extra authored
## camera views (UI hidden, 320x240 internal frame) and a mesh inventory of the default view: triangles, surfaces
## (draw-call estimate), cuboid placeholder boxes, surfaces without texture or vertex colour, and per-actor
## triangles. It then runs the unchanged capture_all pass (clean/key/depth/mask/classic/noglow + capture.json).
## Visual-coverage evidence only: teleported initial state, never a reachability or playthrough claim.
const AUDIT_FORMAT := "hermes64-audit-views/1"
const SURFACE_PLACED := ["piece", "floor", "prop", "wall", "shell", "yard", "landmark", "vista", "window", "door"]

func capture_all(folder: String) -> void:
	DirAccess.make_dir_recursive_absolute(folder)
	var extra := clampi(int(args.get("audit_views", "1")), 0, 2)
	var rows := []
	for room in runtime.game.rooms:
		runtime.state.location = room.id
		enter_room("")
		if follow_camera != null: follow_camera.enabled = false # audit labels refer to authored anchors
		refresh()
		n64_ui.skip_typing()
		n64_ui.visible = false
		await get_tree().create_timer(0.2).timeout
		var start := camera_index
		var inventory := audit_inventory()
		var views := []
		var count: int = room_root.camera_nodes.size()
		# The presenter re-picks the camera whose target is nearest the player every physics tick, so the player
		# stands at each extra camera's target while it is captured (in frame, and that camera stays current).
		var home: Vector3 = player.position
		for k in range(1, mini(count, extra + 1)):
			var entry: Dictionary = room_root.camera_nodes[posmod(start + k, count)]
			player.position = Vector3(entry.target.x, home.y, entry.target.z)
			select_camera(start + k)
			await get_tree().process_frame
			var shot := "%s-view%d-clean.png" % [room.id, k]
			if str(room_root.camera_nodes[camera_index].id) == str(entry.id) and await capture_low(folder.path_join(shot)):
				views.append({"file": shot, "camera": str(entry.id)})
		player.position = home
		select_camera(start)
		n64_ui.visible = true
		rows.append({"id": room.id, "cameras": count, "default_camera": str(room_root.camera_nodes[start].id) if count > 0 else "", "views": views, "inventory": inventory})
	var file := FileAccess.open(folder.path_join("audit-views.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"format": AUDIT_FORMAT, "rooms": rows, "display": DisplayServer.get_name()}, "\t", true))
	file.close()
	await super.capture_all(folder)

## Top-level room child that owns a mesh (its asset_ref / placed metadata names the authored piece).
func owner_of(node: Node) -> Node:
	var n := node
	while n != null and n.get_parent() != room_root and n.get_parent() != null:
		n = n.get_parent()
	return n

func audit_inventory() -> Dictionary:
	var cuboids := []
	var untextured := []
	var actors := []
	var surfaces := 0
	for n in room_root.get_children():
		if str(n.get_meta("placed", "")) == "actor" or n.get_meta("real_character", false):
			# Body triangles exclude blob-shadow fans (named *shadow*), which the room total still counts.
			var shadow := 0
			for s in n.find_children("*shadow*", "MeshInstance3D", true, false):
				shadow += room_root.triangle_count(s)
			var centre: Vector3 = Room.world_aabb(n).get_center()
			var seen: bool = camera != null and is_instance_valid(camera) and camera.is_position_in_frustum(centre)
			actors.append({"node": str(n.name), "triangles": room_root.triangle_count(n) - shadow, "shadow_triangles": shadow, "in_frame": seen})
	var meshes: Array = room_root.find_children("*", "MeshInstance3D", true, false)
	for mi in meshes:
		if not mi.is_visible_in_tree() or mi.mesh == null: continue
		var count: int = mi.mesh.get_surface_count()
		surfaces += count
		var owner_node := owner_of(mi)
		var placed := str(owner_node.get_meta("placed", "")) if owner_node != null else ""
		var ref := str(owner_node.get_meta("asset_ref", owner_node.name)) if owner_node != null else str(mi.name)
		if mi.mesh is BoxMesh and str(mi.name) != "floor_collision":
			cuboids.append({"name": str(mi.name), "ref": ref, "placed": placed})
			continue
		if not placed in SURFACE_PLACED: continue
		for i in count:
			var mat = mi.material_override if mi.material_override != null else mi.get_active_material(i)
			var kind := str(mat.get_meta("kind", "")) if mat != null else ""
			if kind in ["emissive", "glass_env", "chrome_env", "view_plane", "water"]: continue
			var textured: bool = mat is ShaderMaterial and bool(mat.get_shader_parameter("has_texture"))
			var vcol: bool = mi.mesh is ArrayMesh and (mi.mesh.surface_get_format(i) & Mesh.ARRAY_FORMAT_COLOR) != 0
			if not textured and not vcol:
				untextured.append({"name": str(mi.name), "ref": ref, "placed": placed, "kind": kind})
	var player_tris: int = room_root.triangle_count(player) if player != null else 0
	return {"triangles": room_root.triangle_count() + player_tris, "player_triangles": player_tris, "surfaces": surfaces, "cuboids": cuboids, "untextured": untextured.slice(0, 24), "untextured_count": untextured.size(), "actors": actors}
