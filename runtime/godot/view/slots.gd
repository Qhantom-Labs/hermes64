extends RefCounted
## Texture slots (presentation only). The build bakes every filled slot (hermes64-mask/1 recipes, see
## kits/core/mask_recipe.py) into the game's theme.json:
##   "texture_slots": {"atlases": {role: {"path", "sha256", "slots": [...]}},
##                     "sheets":  {slot: {"path", "sha256", "consumer"}}}
## An atlas row is the pack's own atlas for that material role with the slot cells repainted; every surface of that
## role in the room gets it (the pieces whose UVs map a slot cell show the slot, all others look unchanged because the
## rest of the atlas is byte-identical). A sheet row is a standalone emblem for a named consumer; the only runtime
## consumer here is the room presentation "sky_signal" (its "texture" field, unless the room sets one itself).
## No texture_slots in the theme (every game built before slots, or nothing filled): nothing happens.

const Mat = preload("res://look/n64_mat.gd")

static var _tex_cache := {}

static func load_png(path: String, expected: String) -> Texture2D:
	var key := path + "#" + expected
	if _tex_cache.has(key): return _tex_cache[key]
	if path == "" or not FileAccess.file_exists(path): return null
	var raw := FileAccess.get_file_as_bytes(path)
	if expected != "" and FileAccess.get_sha256(path) != expected:
		push_error("Texture slot hash mismatch: " + path.get_file())
		return null
	var img := Image.new()
	if img.load_png_from_buffer(raw) != OK: return null
	var tex := ImageTexture.create_from_image(img)
	_tex_cache[key] = tex
	return tex

## One call from room.gd before the exterior/sky is composed. Returns the room presentation (a copy when a sheet
## consumer was filled in) and swaps slot atlases on every mesh already in the room and every mesh added later.
static func apply(room: Node, theme: Dictionary, presentation: Dictionary) -> Dictionary:
	var slots: Dictionary = theme.get("texture_slots", {})
	if slots.is_empty(): return presentation
	var by_role := {}
	for role in slots.get("atlases", {}):
		var row: Dictionary = slots.atlases[role]
		var tex := load_png(str(row.get("path", "")), str(row.get("sha256", "")))
		if tex != null: by_role[str(role)] = tex
	var out := presentation
	var sky: Dictionary = slots.get("sheets", {}).get("emblem_sky", {})
	if sky.get("consumer", "") == "sky_signal" and presentation.has("sky_signal") and str(presentation.sky_signal.get("texture", "")) == "":
		out = presentation.duplicate(true)
		out.sky_signal["texture"] = str(sky.get("path", ""))
	if by_role.is_empty(): return out
	room.set_meta("texture_slot_roles", by_role.keys())
	var swapped := {}
	swap_tree(room, by_role, swapped)
	# Later meshes (the rest of the room build, actors, effects): the presenter builds a room before adding it to
	# the world, so listen from the moment the room is in a tree; entering the tree also re-reports every node
	# built in between.
	var listen := func() -> void:
		var tree := room.get_tree()
		var cb := func(n: Node) -> void:
			if is_instance_valid(room) and (n == room or room.is_ancestor_of(n)): swap_tree(n, by_role, swapped)
		if not tree.node_added.is_connected(cb): tree.node_added.connect(cb)
		room.tree_exiting.connect(func() -> void:
			if tree.node_added.is_connected(cb): tree.node_added.disconnect(cb), CONNECT_ONE_SHOT)
	if room.is_inside_tree(): listen.call()
	else: room.tree_entered.connect(listen, CONNECT_ONE_SHOT)
	return out

static func swap_tree(node: Node, by_role: Dictionary, swapped: Dictionary) -> void:
	if node is MeshInstance3D and node.mesh != null:
		for i in node.mesh.get_surface_count():
			var m = node.get_surface_override_material(i)
			if not (m is ShaderMaterial): continue
			if m.get_meta("texture_slot", false): continue
			var role := str(m.get_meta("role", ""))
			if not by_role.has(role): continue
			var key: int = m.get_instance_id()
			if not swapped.has(key):
				var m2: ShaderMaterial = m.duplicate()
				Mat.bind_external(m2, by_role[role])
				m2.set_meta("texture_slot", true)
				swapped[key] = m2
			node.set_surface_override_material(i, swapped[key])
	for child in node.get_children(): swap_tree(child, by_role, swapped)
