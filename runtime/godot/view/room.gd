extends Node3D
const Fog = preload("res://view/fog.gdshader")
const Solids = preload("res://view/solid_footprints.gd")
var solid_definitions := []
var solid_bodies := []
var solid_sources := {}
var solids_built := false
var solid_sequence := 0
var target_anchors := {}
var pickup_targets := {}
var data: Dictionary
var theme: Dictionary = {}
var camera_nodes := []
var target_positions := {}
var presentation := {}
var asset_resolver
var real_piece_count := 0
var lights := []
var shell_info := {}
var yard_info := {}
var exterior_cam := {}
var protagonist_id := ""

func piece(ref: String, pos: Vector3, scale_by := Vector3.ONE, yaw := 0.0, kind := "piece") -> Node3D:
	var node = asset_resolver.resolve(ref)
	if node == null:
		node = box(self, "MISSING_" + ref.replace("/", "_"), Vector3(0.5,0.5,0.5),pos,Color.MAGENTA)
		node.set_meta("placeholder",true)
		node.scale = scale_by
		node.rotation_order = EULER_ORDER_YXZ
		node.rotation_degrees.y = yaw
	else:
		add_child(node)
		node.position = pos
		node.scale = scale_by
		node.rotation_order = EULER_ORDER_YXZ
		node.rotation_degrees.y = yaw
		real_piece_count += 1
	node.set_meta("placed", kind)
	if kind in ["piece","prop","dressing","wall"] and ref != "_wall":
		solid_sequence += 1
		register_solid("piece:%04d:%s" % [solid_sequence,ref],ref,node)
	return node

func triangle_count(node: Node = null) -> int:
	if node == null: node = self
	var total := 0
	if node is MeshInstance3D and node.mesh != null:
		var mesh: Mesh = node.mesh
		for i in mesh.get_surface_count():
			if mesh is ArrayMesh:
				# Stored surface lengths: same count as the arrays, without the GPU
				# vertex-buffer readback surface_get_arrays() forces on RD/Metal.
				var indices: int = mesh.surface_get_array_index_len(i)
				total += (indices if indices > 0 else mesh.surface_get_array_len(i)) / 3
			else:
				var arrays: Array = mesh.surface_get_arrays(i) # primitive meshes: CPU-generated
				total += (arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX] != null else arrays[Mesh.ARRAY_VERTEX].size()) / 3
	for child in node.get_children(): total += triangle_count(child)
	return total

## Reference implementation (GPU readback on RD). Kept for the equality test only.
func triangle_count_readback(node: Node = null) -> int:
	if node == null: node = self
	var total := 0
	if node is MeshInstance3D:
		for i in node.mesh.get_surface_count():
			var arrays: Array = node.mesh.surface_get_arrays(i)
			total += (arrays[Mesh.ARRAY_INDEX].size() if arrays[Mesh.ARRAY_INDEX] != null else arrays[Mesh.ARRAY_VERTEX].size()) / 3
	for child in node.get_children(): total += triangle_count_readback(child)
	return total

## Scene budget split for the audit: environment (everything the room builds except actors) vs actors (story
## characters placed in the room, with their own shadow geometry) vs the player visual. Top environment
## contributors by node help trimming scenery to the room cap without touching actors.
func triangle_split(player: Node = null) -> Dictionary:
	var actors := 0
	var top := []
	for n in get_children():
		var t := triangle_count(n)
		if str(n.get_meta("placed", "")) == "actor" or n.get_meta("real_character", false):
			actors += t
		elif t > 0:
			top.append([str(n.name), str(n.get_meta("asset_ref", n.get_meta("placed", ""))), t])
	top.sort_custom(func(a, b): return a[2] > b[2])
	var p := triangle_count(player) if player != null else 0
	var total := triangle_count()
	return {"environment": total - actors, "actors": actors, "player": p, "total": total + p, "top": top.slice(0, 10)}

static func vector(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])

func color(key: String) -> Color:
	return Color.from_string(theme.get("palette", {}).get(key, "#999999"), Color.GRAY)

func material(tint: Color) -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = Fog
	m.set_shader_parameter("tint", tint)
	m.set_shader_parameter("fog_color", Color.from_string(theme.get("fog", {}).get("color", "#222222"), Color.GRAY))
	m.set_shader_parameter("fog_near", theme.get("fog", {}).get("near", 6.0))
	m.set_shader_parameter("fog_far", theme.get("fog", {}).get("far", 28.0))
	return m

func box(parent: Node3D, label: String, size: Vector3, pos: Vector3, tint: Color, collision := false) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = label
	var shape := BoxMesh.new()
	shape.size = size
	mesh.mesh = shape
	mesh.material_override = material(tint)
	mesh.position = pos
	parent.add_child(mesh)
	if collision:
		var body := StaticBody3D.new()
		var collider := CollisionShape3D.new()
		var bounds := BoxShape3D.new()
		bounds.size = size
		collider.shape = bounds
		body.add_child(collider)
		mesh.add_child(body)
	return mesh

func sphere(parent: Node3D, label: String, pos: Vector3, radius: float, tint: Color) -> MeshInstance3D:
	var mesh := MeshInstance3D.new()
	mesh.name = label
	var shape := SphereMesh.new()
	shape.radius = radius
	shape.height = radius * 2.0
	shape.radial_segments = 8
	shape.rings = 4
	mesh.mesh = shape
	mesh.material_override = material(tint)
	mesh.position = pos
	parent.add_child(mesh)
	return mesh

func person(parent: Node3D, params: Dictionary = {}, animal := false) -> Node3D:
	var root := Node3D.new()
	root.set_meta("character_params", params.duplicate(true))
	parent.add_child(root)
	var tint := Color.from_string(params.get("colour", theme.palette.body), color("body"))
	if animal:
		tint = Color.from_string(theme.get("coat_colors", {}).get(params.get("coat", ""), tint.to_html()), tint)
		box(root, "body", Vector3(0.4, 0.3, 0.65), Vector3(0, 0.23, 0), tint)
		sphere(root, "head", Vector3(0, 0.48, -0.25), 0.2, tint)
		box(root, "ear_l", Vector3(0.08, 0.18, 0.1), Vector3(-0.13, 0.67, -0.25), tint)
		box(root, "ear_r", Vector3(0.08, 0.18, 0.1), Vector3(0.13, 0.67, -0.25), tint)
	else:
		var suit: Dictionary = params.get("suit", {})
		tint = Color.from_string(suit.get("vest_colour", tint.to_html()), tint)
		box(root, "vest", Vector3(0.55, 0.6, 0.35), Vector3(0, 0.8, 0), tint)
		box(root, "boot_l", Vector3(0.22, 0.45, 0.32), Vector3(-0.16, 0.25, 0), color("boots"))
		box(root, "boot_r", Vector3(0.22, 0.45, 0.32), Vector3(0.16, 0.25, 0), color("boots"))
		var head: Dictionary = theme.get("head_styles", {}).get(suit.get("hood", ""), {})
		sphere(root, "hood", Vector3(0, 1.35, 0), 0.33, Color.from_string(head.get("color", theme.palette.head), color("head")))
		if head.get("void", false):
			sphere(root, "void", Vector3(0, 1.35, -0.23), 0.23, color("void"))
	return root

func build(room: Dictionary, runtime, resolver) -> void:
	data = room
	name = room.id
	var w: float = room.grid_size[0]
	var d: float = room.grid_size[1]
	asset_resolver = resolver
	presentation = runtime.game.metadata.get("presentation", {}).get("rooms", {}).get(room.id, {})
	for interaction in runtime.game.get("interactions",[]):
		if interaction.room == room.id and interaction.kind in ["take","collect"]: pickup_targets[str(interaction.target)] = true
	protagonist_id = str(runtime.game.metadata.get("protagonist", ""))
	var exterior: bool = presentation.get("exterior", false)
	# Pack shell (ROOMLOOK): a real enclosed kit room with cut openings, built by hermes64_build_assets.
	var shell_row = resolver.mapping.get("shell/" + room.id, null) if not exterior else null
	var shell_node: Node3D = null
	if shell_row is Dictionary:
		shell_node = resolver.resolve("shell/" + room.id)
		if shell_node != null:
			add_child(shell_node)
			shell_node.position = Vector3(w/2, 0, d/2)
			shell_node.name = "shell"
			shell_node.set_meta("placed", "shell")
			real_piece_count += 1
			shell_info = shell_row
	# Pack yard (ROOMLOOK outdoors): terraced kit landscape for exterior rooms, built by hermes64_build_assets.
	var ext: Dictionary = theme.get("look", {}).get("exterior", {})
	var yard_row = resolver.mapping.get("yard/" + room.id, null) if exterior else null
	var yard_node: Node3D = null
	if yard_row is Dictionary:
		yard_node = resolver.resolve("yard/" + room.id)
		if yard_node != null:
			add_child(yard_node)
			yard_node.position = Vector3(w/2, 0, d/2)
			yard_node.name = "yard"
			yard_node.set_meta("placed", "yard")
			real_piece_count += 1
			yard_info = yard_row
	if shell_node == null and yard_node == null and presentation.get("floor", "_floor") != "": piece(presentation.get("floor", "_floor"), Vector3(w/2,-0.1,d/2), vector(presentation.get("floor_scale",[w/3,1,d/3])), 0.0, "floor")
	# Invisible collision is separate from the kit visuals. Actions never gain geometric preconditions.
	var floor_collision = box(self,"floor_collision",Vector3(w,0.2,d),Vector3(w/2,-0.1,d/2),color("floor"),true)
	floor_collision.visible = false
	# DUNGEONKIT: a room assembled from kit pieces (presentation "kit_shell": true) brings its own walls and cut
	# door openings, so the legacy placeholder walls/window are not added.
	var kit_shell: bool = bool(presentation.get("kit_shell", false))
	if not exterior and shell_node == null and not kit_shell:
		piece("_wall",Vector3(w/2,0,0),Vector3(w/2,1,1),0.0,"wall")
		piece("_wall",Vector3(0,0,d/2),Vector3(d/2,1,1),90,"wall")
		piece("_wall",Vector3(w/2,0,d),Vector3(w/2,0.1,1),180,"wall")
		piece("_wall",Vector3(w,0,d/2),Vector3(d/2,0.1,1),-90,"wall")
		piece("arch.window",Vector3(w*0.6,1.1,0.08),Vector3.ONE,0.0,"window")
	var shell_doors := {}
	if shell_node != null: shell_doors = place_openings(w, d)
	var backdrop: Dictionary = theme.get("look", {}).get("backdrop", {})
	var superseded: Array = ext.get("supersede", []) if yard_node != null else []
	var backdrop_here: bool = exterior or bool(backdrop.get("interiors", true))
	if not backdrop.is_empty() and backdrop_here and (yard_node != null or not presentation.get("pieces", []).any(func(x): return x.get("asset", "") == backdrop.get("asset", ""))):
		# exteriors: the dome must enclose the vista rings (look.exterior.backdrop_scale)
		var bs := float(ext.get("backdrop_scale", backdrop.get("scale", 0.1))) if yard_node != null else float(backdrop.get("scale", 0.1))
		piece(str(backdrop.asset), Vector3(w/2, float(backdrop.get("y", 0.0)), d/2), Vector3(bs, bs, bs), 0.0, "backdrop")
	for placed in presentation.get("pieces", []):
		if superseded.has(placed.asset): continue
		# State-swapped piece (CITY lane: lockable gates): {"asset": locked, "flag": f, "asset_when_set": open}
		var ref: String = str(placed.asset)
		if placed.has("flag") and bool(runtime.state.flags.get(str(placed.flag), false)): ref = str(placed.get("asset_when_set", ref))
		piece(ref, vector(placed.get("position",[w/2,0,d/2])),vector(placed.get("scale",[1,1,1])),float(placed.get("yaw",0)),str(placed.get("kind","piece")))
		# DUNGEONKIT: kit structure declares its kind ("shell"/"wall"/"floor"); wall- or ceiling-hung props "mounted": true
		var placed_node: Node = get_child(get_child_count() - 1)
		if placed.has("kind"): placed_node.set_meta("placed", str(placed.kind))
		if bool(placed.get("mounted", false)): placed_node.set_meta("mounted", true)
		# MOVE: free-standing authored scenery (fences/railings, columns, rocks,
		# trees, buildings) blocks like props. Room structure (shell/wall/floor/
		# ceiling kinds) is the boundary's job; walk-through kits and hung or
		# out-of-grid pieces are excluded by policy, never by asset name.
		var kind := str(placed.get("kind","piece"))
		var at: Vector3 = placed_node.position if placed_node is Node3D else Vector3.ZERO
		if kind in ["piece","dressing"] and not bool(placed.get("mounted", false)) and at.y <= 0.5 and at.x > 0.0 and at.x < w and at.z > 0.0 and at.z < d and placed_node is Node3D:
			register_solid("piece:%02d:%s" % [scenery_index, ref], ref, placed_node, {"scenery":true})
		scenery_index += 1
	var props := Node3D.new()
	props.name = "props"
	add_child(props)
	var bound_props := {}
	var character_anchors := {}
	var anchors: Dictionary = runtime.game.metadata.get("collectible_prop_ids", {})
	for c in runtime.collections.values():
		if c.room == room.id and anchors.has(c.id):
			bound_props[anchors[c.id]] = c
			pickup_targets[str(anchors[c.id])] = true
	for prop in room.props:
		var pos := vector(presentation.get("props", {}).get(prop.id, {}).get("position", prop.position))
		target_positions[prop.id] = pos
		target_positions[prop.asset] = pos
		if bound_props.has(prop.id):
			var collectible: Dictionary = bound_props[prop.id]
			target_positions["collect:" + collectible.id] = pos
			target_positions["recall:" + collectible.id] = pos
			if collectible.character != "":
				character_anchors[collectible.character] = pos
				continue
			if runtime.state.collected.has(collectible.id): continue
		var node = resolver.resolve(prop.asset)
		if node == null:
			node = box(props, prop.id, Vector3(0.7, 0.7, 0.7), pos, color("prop"))
		else:
			props.add_child(node)
			node.name = prop.id
			node.position = pos
		node.set_meta("placed", "prop")
		node.rotation_order = EULER_ORDER_YXZ
		var place: Dictionary = presentation.get("props", {}).get(prop.id,{})
		node.rotation_degrees = vector(place.get("rotation",prop.rotation))
		node.scale = vector(place.get("scale",[1,1,1]))
		if not pickup_targets.has(str(prop.id)):
			register_solid("prop:" + str(prop.id),str(prop.asset),node)
	if yard_node != null: shell_doors.merge(place_exits(w, d, ext))
	for door in room.doors:
		if shell_doors.has(door.id):
			target_positions["move:" + room.id + ":" + door.id] = shell_doors[door.id]
			continue
		var pos := door_position(door, room.grid_size)
		var door_node := piece("arch.door",pos,Vector3.ONE,{"north":0.0,"south":180.0,"west":90.0,"east":-90.0}.get(door.wall,0.0),"door")
		if kit_shell: door_node.set_meta("opening_cut", true)  # kit room walls carry the cut (socket-checked by the room compiler)
		target_positions["move:" + room.id + ":" + door.id] = pos
	var character_index := 0
	for cid in room.character_ids:
		if cid == runtime.game.metadata.get("protagonist", ""): continue
		var following := false
		for collectible in runtime.collections.values():
			if collectible.character == cid and collectible.follower_flag != "" and runtime.state.collected.has(collectible.id): following = true
		if following: continue
		var c: Dictionary = runtime.characters[cid]
		var actor = resolver.character(c)
		if actor == null: actor = person(self, c.params, c.params.has("coat"))
		else: add_child(actor)
		actor.name = "actor_" + cid
		actor.set_meta("placed", "actor")
		var authored: Dictionary = presentation.get("characters", {}).get(cid, {})
		actor.position = vector(authored.position) if authored.has("position") else character_anchors.get(cid, Vector3(2 + fmod(character_index * 1.5, maxf(1, w - 3)), 0, d * 0.4))
		actor.rotation_degrees.y = float(authored.get("yaw",180))
		target_positions[cid] = actor.position
		register_solid("actor:" + str(cid),"character:" + str(cid),actor,{"actor":true,"animal":c.params.has("coat")})
		character_index += 1
	var local_collectibles := []
	for c in runtime.game.get("collectibles", []):
		if c.room == room.id: local_collectibles.append(c)
	for i in local_collectibles.size():
		var c: Dictionary = local_collectibles[i]
		var pos: Vector3 = target_positions.get("collect:" + c.id, target_positions.get(c.character, Vector3(1.5 + fmod(i * 1.4, maxf(1, w - 2)), 0.6, d * 0.65 + floor(i * 1.4 / maxf(1, w - 2)))))
		pos = vector(presentation.get("collectibles",{}).get(c.id,{}).get("position",[pos.x,pos.y,pos.z]))
		target_positions["collect:" + c.id] = pos
		target_positions["recall:" + c.id] = pos
		if not runtime.state.collected.has(c.id) and c.character == "" and not anchors.has(c.id):
			var visual = resolver.resolve(c.asset)
			if visual == null: visual = sphere(self, "collect_" + c.id, pos, 0.24, color("collectible"))
			else:
				add_child(visual)
				visual.position = pos
			visual.set_meta("placed", "collectible")
	for id in presentation.get("interactions",{}): target_positions[id] = vector(presentation.interactions[id].position)
	var cameras: Array = presentation.get("cameras", room.cameras)

	if cameras.is_empty(): cameras = [{"id":"default","position":[w*1.1,w*0.7,d*1.3],"look_at":[w/2,0.8,d/2]}]
	for raw_anchor in cameras:
		var anchor: Dictionary = inside_camera(raw_anchor, w, d) if yard_info.is_empty() else exterior_camera(raw_anchor, w, d, ext)
		var cam := Camera3D.new()
		cam.name = anchor.id
		cam.position = vector(anchor.position)
		cam.fov = float(anchor.get("fov",52))
		cam.near = 0.05
		add_child(cam)
		camera_nodes.append({"node": cam, "target": vector(anchor.look_at), "id": anchor.id})
	compose_exterior(w, d, theme.get("look", {}).get("exterior", {}))
	target_anchors = target_positions.duplicate()
	build_solid_bodies()
	build_boundary(w, d)

## MOVE: solid room boundary derived from authored room data. The walkable
## outline of the shell (interior) or yard (exterior) kit, clipped to the grid;
## otherwise the grid rectangle (legacy placeholder walls / kit-shell rooms).
## Doors/exits are contextual portals whose walk targets sit INSIDE the outline,
## so the boundary is closed. The player enforces it analytically (player.gd
## clamp_to_floor_outline, sliding); navigation/reachability use the same outline.
## Camera/interaction rays are unchanged.
var scenery_index := 0
var boundary_outline := PackedVector2Array()
var boundary_source := ""

static func outline_room_space(outline: Array, w: float, d: float) -> PackedVector2Array:
	var out := PackedVector2Array()
	for p in outline: out.append(Vector2(w/2 + float(p[0]), d/2 + float(p[1])))
	return out

static func boundary_polygon(raw: PackedVector2Array, w: float, d: float) -> PackedVector2Array:
	var rect := PackedVector2Array([Vector2(0,0),Vector2(w,0),Vector2(w,d),Vector2(0,d)])
	if raw.size() < 3: return rect
	var best := PackedVector2Array()
	var best_area := 0.0
	for poly in Geometry2D.intersect_polygons(raw, rect):
		var area := absf(polygon_area(poly))
		if area > best_area: best_area = area; best = poly
	if best.size() < 3 or best_area < 1.0: return rect
	return best

static func polygon_area(poly: PackedVector2Array) -> float:
	var a := 0.0
	for i in poly.size(): a += poly[i].cross(poly[(i+1)%poly.size()])
	return a * 0.5

func build_boundary(w: float, d: float) -> void:
	var raw := PackedVector2Array()
	boundary_source = "grid_rect"
	var info: Dictionary = shell_info if not shell_info.is_empty() else yard_info
	var outline: Array = info.get("meta", {}).get("walkable_outline_gltf", [])
	if outline.size() >= 3:
		raw = outline_room_space(outline, w, d)
		boundary_source = "shell_outline" if not shell_info.is_empty() else "yard_outline"
	boundary_outline = boundary_polygon(raw, w, d)
	# Deliberately NO native bodies: a first version used thin box segments on
	# its own layer, but capsule recovery against many rotated segments of a
	# curved wall drifted 0.3 mm with render cadence (Thaw dome replay diverged
	# at 30 vs 60 FPS). The player's analytic outline clamp is exact and slides.

func register_solid(id: String, ref: String, node: Node3D, policy: Dictionary = {}) -> void:
	var raw = asset_resolver.mapping.get(ref,{})
	var binding: Dictionary = raw.duplicate(true) if raw is Dictionary else {}
	binding.merge(policy,true)
	solid_sources[id] = {"ref":ref,"transform":node.transform,"binding":binding,"node":node}
	node.set_meta("solid_id",id)
	if solids_built: build_solid_bodies()

func build_solid_bodies() -> void:
	for body in solid_bodies: body.free()
	solid_bodies.clear()
	solid_definitions.clear()
	var ids: Array = solid_sources.keys()
	ids.sort()
	for id in ids:
		var source: Dictionary = solid_sources[id]
		var row: Dictionary = Solids.definition(str(id),source.ref,source.transform,source.binding)
		if not row.is_empty(): solid_definitions.append(row)
	solid_definitions.sort_custom(func(a,b): return str(a.id) < str(b.id))
	for row in solid_definitions:
		var body := Solids.body_for(row)
		add_child(body)
		solid_bodies.append(body)
	solids_built = true

## The selector still dispatches the original story ID. Only its physical prompt
## anchor moves to an exposed edge, so a target never occludes its own ray.
func update_interaction_targets(from: Vector3) -> void:
	var ids: Array = target_anchors.keys()
	ids.sort()
	for id in ids:
		target_positions[id] = Solids.target_point(solid_definitions,target_anchors[id],from)

## ---------------------------------------------------------------- exterior composition (pack look.exterior)
## Height of the yard surface at a grid point (playfield 0, then terrace treads), from the kit meta.
func yard_height(x: float, z: float, w: float, d: float) -> float:
	var meta: Dictionary = yard_info.get("meta", {})
	var outline: Array = meta.get("walkable_outline_gltf", [])
	if outline.size() < 3: return 0.0
	var local := Vector2(x - w / 2, z - d / 2)
	if local.length() < 0.01: return 0.0
	var edge := ray_outline(local.normalized(), outline)
	var beyond := local.length() - edge
	if beyond <= 0.0: return 0.0
	var h := 0.0
	for t in meta.get("terraces", []):
		if beyond >= float(t.inner_offset): h = float(t.height)
	return h

## Fixed exterior camera: on the authored side, standing on the first ledge behind the playfield, low and looking
## across the field toward the far ridge so ground, ridge, landmark and sky share the frame (near/mid/far).
func exterior_camera(anchor: Dictionary, w: float, d: float, ext: Dictionary) -> Dictionary:
	var policy: Dictionary = ext.get("camera", {})
	var meta: Dictionary = yard_info.get("meta", {})
	var outline: Array = meta.get("walkable_outline_gltf", [])
	if policy.is_empty() or outline.size() < 3: return anchor
	var c := Vector2(w / 2, d / 2)
	var p := vector(anchor.position)
	var local := Vector2(p.x, p.z) - c
	var dir := local.normalized() if local.length() > 0.01 else Vector2(0, 1)
	var r := ray_outline(dir, outline)
	if r <= 0.0: return anchor
	var hp := c + dir * (r + float(policy.get("back", 2.0)))
	var ground := yard_height(hp.x, hp.y, w, d)
	var tgt := c - dir * r * float(policy.get("target_frac", 0.5))
	var out := anchor.duplicate(true)
	out["position"] = [hp.x, ground + float(policy.get("height", 3.0)), hp.y]
	out["look_at"] = [tgt.x, float(policy.get("target_y", 1.5)), tgt.y]
	out["fov"] = float(policy.get("fov", 60))
	out["reframed"] = true
	exterior_cam = out
	return out

## Door buildings at the yard exits (the pass cut into terraces/ridge); returns walk targets by door id.
func place_exits(w: float, d: float, ext: Dictionary) -> Dictionary:
	var meta: Dictionary = yard_info.get("meta", {})
	var plan: Dictionary = yard_info.get("yard_plan", {})
	var by_index := {}
	for e in meta.get("exits", []): by_index[int(e.index)] = e
	var targets := {}
	var bcfg: Dictionary = ext.get("door_building", {})
	for row in plan.get("exits", []):
		var e = by_index.get(int(row.index), null)
		if e == null: continue
		var yaw := float(e.yaw_deg)
		var base := Vector3(w / 2 + float(e.pos_gltf[0]), 0.0, d / 2 + float(e.pos_gltf[2]))
		var inward := Basis(Vector3.UP, deg_to_rad(yaw)) * Vector3(0, 0, 1)
		targets[str(row.get("door_id", ""))] = base + inward * 1.0
		if bcfg.is_empty(): continue
		var bs := float(bcfg.get("scale", 1.0))
		var node := piece(str(bcfg.asset), base - inward * float(bcfg.get("back", 2.5)), Vector3(bs, bs, bs), yaw, "door")
		node.set_meta("opening_cut", true)
	return targets

## Darken one instance (foreground framing reads as a chunky dark silhouette); materials duplicated per instance.
func shade_instance(n: Node, k: float) -> void:
	for mi in n.find_children("*", "MeshInstance3D", true, false) + ([n] if n is MeshInstance3D else []):
		for i in mi.mesh.get_surface_count():
			var m = mi.get_surface_override_material(i)
			if m is ShaderMaterial:
				var mm: ShaderMaterial = m.duplicate()
				var raw = mm.get_shader_parameter("tint")
				var t := Color.WHITE
				if raw is Color: t = raw
				elif raw is Vector4: t = Color(raw.x, raw.y, raw.z, raw.w)
				mm.set_shader_parameter("tint", Color(t.r * k, t.g * k, t.b * k, t.a))
				mi.set_surface_override_material(i, mm)

static func hashf(i: float) -> float:
	return fposmod(sin(i * 12.9898 + 78.233) * 43758.5453, 1.0)

func mounted_piece(ref: String, pos: Vector3, sc: Vector3, yaw: float, kind: String) -> Node3D:
	var n := piece(ref, pos, sc, yaw, kind)
	n.set_meta("mounted", true)
	return n

## Vista rings, landmark on the far skyline, framing objects near the lens, rock clusters, rhythmic posts along
## the paths, vegetation on the ledges and a particle field. All from pack data; positions are deterministic.
func compose_exterior(w: float, d: float, ext: Dictionary) -> void:
	if yard_info.is_empty() or ext.is_empty(): return
	var meta: Dictionary = yard_info.get("meta", {})
	var outline: Array = meta.get("walkable_outline_gltf", [])
	var c := Vector2(w / 2, d / 2)
	var terr_top := 0.0
	for t in meta.get("terraces", []): terr_top = maxf(terr_top, float(t.height))
	var vista: Dictionary = ext.get("vista", {})
	if not vista.is_empty():
		# distant rings stand on the terrace plane (above_terraces) so they rise over the lowered ridge at the view gap
		var vsc = vista.get("scale", 1.0)  # number or [sx, sy, sz] (sy stretches the silhouettes, radius kept)
		var v3 := Vector3(vsc[0], vsc[1], vsc[2]) if vsc is Array else Vector3(float(vsc), float(vsc), float(vsc))
		var vy := float(vista.get("y", 0.0)) + (terr_top if vista.get("above_terraces", false) else 0.0)
		piece(str(vista.asset), Vector3(w / 2, vy, d / 2), v3, 0.0, "vista")
	var cam_p := Vector2(w / 2, d * 2)
	var cam_t := c
	if not exterior_cam.is_empty():
		cam_p = Vector2(float(exterior_cam.position[0]), float(exterior_cam.position[2]))
		cam_t = Vector2(float(exterior_cam.look_at[0]), float(exterior_cam.look_at[2]))
	var fwd := (cam_t - cam_p).normalized()
	var right := Vector2(-fwd.y, fwd.x)
	var terr_h := 0.0
	for t in meta.get("terraces", []): terr_h = maxf(terr_h, float(t.height))
	var ridge: Dictionary = meta.get("ridge", {})
	var lm: Dictionary = ext.get("landmark", {})
	if not lm.is_empty():
		var dirl := (fwd + right * float(lm.get("side", 0.0))).normalized()
		var edge := ray_outline(dirl, outline)
		var crest := edge + float(ridge.get("base_offset", 0.0)) + float(ridge.get("run", 0.0)) * float(lm.get("crest_frac", 0.7))
		var at := c + dirl * maxf(crest, float(lm.get("distance", 0.0)))
		var ls := float(lm.get("scale", 1.0))
		var y := terr_h + float(ridge.get("height", 0.0)) * float(lm.get("height_frac", 0.8))
		var lnode := mounted_piece(str(lm.asset), Vector3(at.x, y, at.y), Vector3(ls, ls, ls), float(lm.get("yaw", 0.0)), "landmark")
		if lm.has("shade"): shade_instance(lnode, float(lm.shade))
	var i := 0
	for f in ext.get("framing", []):
		i += 1
		var dist := float(f.get("distance", 4.5))
		var lateral := float(f.get("side", 1.0)) * dist * tan(deg_to_rad(float(exterior_cam.get("fov", 60)) * 0.5 * 1.15))
		var fp := cam_p + fwd * dist + right * lateral
		var sc = f.get("scale", 1.0)
		var s3 := Vector3(sc[0], sc[1], sc[2]) if sc is Array else Vector3(float(sc), float(sc), float(sc))
		var fnode := mounted_piece(str(f.asset), Vector3(fp.x, yard_height(fp.x, fp.y, w, d), fp.y), s3, hashf(i) * 360.0, "framing")
		if f.has("shade"): shade_instance(fnode, float(f.shade))
	var k := 0
	for cl in ext.get("clusters", []):
		var at: Array = cl.get("at", [0.75, 0.3])
		var cc := Vector2(float(at[0]) * w, float(at[1]) * d)
		var sr: Array = cl.get("scale", [0.4, 0.9])
		for j in int(cl.get("count", 6)):
			k += 1
			var a := hashf(k * 3.1) * TAU
			var rr := float(cl.get("spread", 1.5)) * sqrt(hashf(k * 5.7))
			var q := cc + Vector2(cos(a), sin(a)) * rr
			var s := lerpf(float(sr[0]), float(sr[1]), hashf(k * 7.3))
			var dn := mounted_piece(str(cl.asset), Vector3(q.x, 0.0, q.y), Vector3(s, s * lerpf(0.7, 1.1, hashf(k)), s), hashf(k * 9.1) * 360.0, "dressing")
			if cl.has("shade"): shade_instance(dn, float(cl.shade))
	var rh: Dictionary = ext.get("rhythm", {})
	if not rh.is_empty():
		var placed := 0
		for path in meta.get("paths_gltf", []):
			var acc := 0.0
			var side := 1.0
			for pi in range(1, path.size()):
				var a2 := Vector2(float(path[pi - 1][0]), float(path[pi - 1][1]))
				var b2 := Vector2(float(path[pi][0]), float(path[pi][1]))
				var seg := b2 - a2
				var L := seg.length()
				var t := 0.0
				while acc + L - t >= float(rh.get("spacing", 3.0)) and placed < int(rh.get("max", 10)):
					t += float(rh.get("spacing", 3.0)) - acc
					acc = 0.0
					var q := a2 + seg.normalized() * t + Vector2(-seg.y, seg.x).normalized() * side * float(rh.get("offset", 1.2))
					var gq := c + q
					if gq.x > 0.3 and gq.x < w - 0.3 and gq.y > 0.3 and gq.y < d - 0.3:
						var rs := float(rh.get("scale", 1.0))
						mounted_piece(str(rh.asset), Vector3(gq.x, 0.0, gq.y), Vector3(rs, rs, rs), 0.0, "dressing")
						placed += 1
					side = -side
				acc += L - t
	var veg: Dictionary = ext.get("vegetation", {})
	var terraces: Array = meta.get("terraces", [])
	if not veg.is_empty() and not terraces.is_empty():
		var cam_dir := (cam_p - c).normalized()
		var vr: Array = veg.get("scale", [0.8, 1.2])
		for j in int(veg.get("count", 8)):
			var a := TAU * (j + 0.5) / float(veg.get("count", 8)) + hashf(j * 1.9) * 0.5
			var dirv := Vector2(cos(a), sin(a))
			if dirv.dot(cam_dir) > 0.35: continue
			var exit_near := false
			for e in meta.get("exits", []):
				var ed := Vector2(float(e.pos_gltf[0]), float(e.pos_gltf[2])).normalized()
				if ed.dot(dirv) > 0.93: exit_near = true
			if exit_near: continue
			var t: Dictionary = terraces[j % terraces.size()]
			var edge := ray_outline(dirv, outline)
			var off := lerpf(float(t.inner_offset), float(t.outer_offset), 0.35 + 0.3 * hashf(j * 4.3))
			var q := c + dirv * (edge + off)
			var s := lerpf(float(vr[0]), float(vr[1]), hashf(j * 6.1))
			var dn := mounted_piece(str(veg.asset), Vector3(q.x, float(t.height), q.y), Vector3(s, s, s), hashf(j * 8.7) * 360.0, "dressing")
			if veg.has("shade"): shade_instance(dn, float(veg.shade))
	ground_marks(w, d, ext)
	var pc: Dictionary = ext.get("particles", {})
	if not pc.is_empty(): particle_field(Vector3(w / 2, 0, d / 2), pc)

## Lead-the-eye ground marks (look.exterior "trail" / "drifts"): a footprint trail from the protagonist's mark to
## the nearest door building, and wind drift lines (lit crest + blue lee) across the playfield. Soft 2-triangle
## decals; deterministic; hidden in the gate's distance/region passes.
func ground_marks(w: float, d: float, ext: Dictionary) -> void:
	var tr: Dictionary = ext.get("trail", {})
	var chars: Dictionary = presentation.get("characters", {})
	if not tr.is_empty():
		var start := Vector2(w * 0.7, d * 0.8)
		if chars.has(protagonist_id) and (chars[protagonist_id] as Dictionary).has("position"):
			var pp := vector(chars[protagonist_id].position)
			start = Vector2(pp.x, pp.z)
		# lead INTO the picture: the door building deepest in front of the fixed camera, not the nearest one
		var cam_p := Vector2(w / 2, d * 2)
		var cam_t := Vector2(w / 2, d / 2)
		if not exterior_cam.is_empty():
			cam_p = Vector2(float(exterior_cam.position[0]), float(exterior_cam.position[2]))
			cam_t = Vector2(float(exterior_cam.look_at[0]), float(exterior_cam.look_at[2]))
		var fwd := (cam_t - cam_p).normalized()
		var goal := Vector2(-1, -1)
		var best := -INF
		for n in get_children():
			if not str(n.get_meta("asset_ref", "")) in tr.get("to", []): continue
			var q := Vector2(n.position.x, n.position.z)
			var depth := (q - cam_p).dot(fwd)
			var side := absf((q - cam_p).dot(Vector2(-fwd.y, fwd.x))) / maxf(depth, 0.1)
			if depth <= 0.0 or side > 0.9: continue
			var score := depth - 0.5 * q.distance_to(start)
			if score > best:
				best = score
				goal = q
		set_meta("trail", {"from": [snappedf(start.x, 0.01), snappedf(start.y, 0.01)], "to": [snappedf(goal.x, 0.01), snappedf(goal.y, 0.01)]})
		if goal.x >= 0.0:
			var stop := float(tr.get("stop", 1.6))
			var path := goal - start
			var L := maxf(0.0, path.length() - stop - 0.6)
			var dir := path.normalized()
			var side := Vector2(-dir.y, dir.x)
			var step := float(tr.get("spacing", 0.6))
			var fs: Array = tr.get("size", [0.2, 0.34])
			var col := Color.from_string(str(tr.get("color", "#7d8de0")), Color.GRAY)
			var n := 0
			var t := 0.6
			while t < L and n < int(tr.get("max", 24)):
				# gentle S-curve so the trail reads as walked, not ruled
				var bend := sin(t / maxf(L, 0.1) * PI * 2.0) * float(tr.get("bend", 0.35))
				var q := start + dir * t + side * (bend + (0.12 if n % 2 == 0 else -0.12))
				var tangent := (dir + side * cos(t / maxf(L, 0.1) * PI * 2.0) * float(tr.get("bend", 0.35)) * PI * 2.0 / maxf(L, 0.1)).normalized()
				var m := disc_card(Vector3(q.x, yard_height(q.x, q.y, w, d) + float(tr.get("lift", 0.03)), q.y), 1.0, col, float(tr.get("strength", 0.5)), "trail_%d" % n)
				m.rotation = Vector3(-PI / 2, -tangent.angle() + PI / 2, 0)
				m.scale = Vector3(float(fs[0]), float(fs[1]), 1.0)
				n += 1
				t += step
	var dr: Dictionary = ext.get("drifts", {})
	if not dr.is_empty():
		var lr: Array = dr.get("length", [2.5, 5.0])
		var wr: Array = dr.get("width", [0.3, 0.55])
		var yaw := deg_to_rad(float(dr.get("angle", 20.0)))
		if str(dr.get("orient", "world")) == "across" and not exterior_cam.is_empty():
			# lie across the fixed camera's view: at a grazing view a streak along the view axis collapses to a dot
			var cf := Vector2(float(exterior_cam.look_at[0]) - float(exterior_cam.position[0]), float(exterior_cam.look_at[2]) - float(exterior_cam.position[2])).normalized()
			yaw = Vector2(-cf.y, cf.x).angle() + deg_to_rad(float(dr.get("angle", 0.0)))
		var crest := Color.from_string(str(dr.get("crest", "#ffffff")), Color.WHITE)
		var lee := Color.from_string(str(dr.get("lee", "#8e9ff5")), Color.GRAY)
		var dv := Vector2(cos(yaw), sin(yaw))
		var nv := Vector2(-dv.y, dv.x)
		for j in int(dr.get("count", 6)):
			var q := Vector2(lerpf(0.15, 0.85, hashf(j * 2.3 + 11.0)) * w, lerpf(0.15, 0.85, hashf(j * 3.7 + 5.0)) * d)
			var L := lerpf(float(lr[0]), float(lr[1]), hashf(j * 1.3))
			var W := lerpf(float(wr[0]), float(wr[1]), hashf(j * 4.1))
			var jy := deg_to_rad(float(dr.get("jitter", 0.0))) * (hashf(j * 6.7) * 2.0 - 1.0)
			for k in 2:
				var o := q + nv.rotated(jy) * (0.0 if k == 0 else W * 0.55)
				var m := disc_card(Vector3(o.x, yard_height(o.x, o.y, w, d) + float(dr.get("lift", 0.02)) + 0.003 * k, o.y), 1.0, crest if k == 0 else lee, float(dr.get("strength", 0.35)) * (1.0 if k == 0 else 0.8), "drift_%d_%d" % [j, k])
				m.rotation = Vector3(-PI / 2, -(yaw + jy), 0)
				m.scale = Vector3(L, W, 1.0)

func particle_field(at: Vector3, pc: Dictionary) -> void:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	var q := QuadMesh.new()
	q.size = Vector2(1, 1)
	mm.mesh = q
	mm.instance_count = int(pc.get("count", 150))
	for i in mm.instance_count: mm.set_instance_transform(i, Transform3D.IDENTITY)
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	var area: Array = pc.get("area", [30, 10, 30])
	mi.custom_aabb = AABB(Vector3(-float(area[0]) / 2 - 1, -1, -float(area[2]) / 2 - 1), Vector3(float(area[0]) + 2, float(area[1]) + 2, float(area[2]) + 2))
	var m := ShaderMaterial.new()
	m.shader = preload("res://shaders/n64_snow.gdshader")
	m.set_shader_parameter("color", Color.from_string(str(pc.get("color", "#ffffff")), Color.WHITE))
	m.set_shader_parameter("area", Vector3(float(area[0]), float(area[1]), float(area[2])))
	m.set_shader_parameter("speed", float(pc.get("speed", 0.5)))
	m.set_shader_parameter("drift", float(pc.get("drift", 0.2)))
	m.set_shader_parameter("size", float(pc.get("size", 0.07)))
	mi.material_override = m
	mi.position = at
	mi.name = "particles"
	mi.set_meta("placed", "particles")
	add_child(mi)

## Door/window kit modules dropped into the shell's cut openings (placement from the kit meta, refs from the
## build plan). Returns {door_id: walk target just inside the opening}.
func place_openings(w: float, d: float) -> Dictionary:
	var meta: Dictionary = shell_info.get("meta", {})
	var plan: Dictionary = shell_info.get("shell_plan", {})
	var by_index := {}
	for op in meta.get("openings", []): by_index[int(op.index)] = op
	var targets := {}
	for row in plan.get("openings", []):
		var op = by_index.get(int(row.index), null)
		if op == null: continue
		var yaw := float(op.yaw_deg)
		var base := Vector3(w/2 + float(op.pos_gltf[0]), 0.0, d/2 + float(op.pos_gltf[2]))
		var inward := Basis(Vector3.UP, deg_to_rad(yaw)) * Vector3(0, 0, 1)
		var ref := str(row.get("ref", ""))
		if row.kind == "door":
			var y := float(op.sill) - float(row.get("threshold", 0.0))
			var node := piece(ref if ref != "" else "arch.door", base + Vector3(0, y, 0), Vector3.ONE, yaw, "door")
			node.set_meta("opening_cut", true)
			targets[str(row.get("door_id", ""))] = base + inward * 0.7
		elif ref != "":
			piece(ref, base, Vector3.ONE, yaw, "window")
	return targets

## Pack support policy (look.supports): nothing hovers. A prop authored above the floor drops onto the furniture
## under it; tall pieces with their own legs/pedestal stand on the floor; small things get the pack's support
## piece (side table) under them. Presentation only: story ids, targets and actions are untouched.
func settle() -> void:
	var cfg: Dictionary = theme.get("look", {}).get("supports", {})
	if cfg.is_empty() or not is_inside_tree(): return
	var skip := ["actor", "shell", "backdrop", "light", "wall", "window", "door", "floor", "yard", "vista", "landmark", "framing", "particles"]
	var nodes := []
	for n in find_children("*", "Node3D", true, false):
		if n.has_meta("placed") and not str(n.get_meta("placed")) in skip: nodes.append(n)
	nodes.sort_custom(func(a, b): return world_aabb(a).position.y < world_aabb(b).position.y)
	for n in nodes:
		var kind := str(n.get_meta("placed"))
		if not kind in ["prop", "piece", "collectible"] or n.get_meta("mounted", false): continue
		var a := world_aabb(n)
		if a.size == Vector3.ZERO or a.position.y <= 0.06: continue
		var c := a.get_center()
		var top := 0.0
		for s in nodes:
			if s == n: continue
			var b := world_aabb(s)
			if b.size == Vector3.ZERO or c.x < b.position.x or c.x > b.end.x or c.z < b.position.z or c.z > b.end.z: continue
			if b.end.y <= a.position.y + 0.05 and b.end.y > top: top = b.end.y
		if top > 0.0 and a.position.y - top <= float(cfg.get("max_drop", 0.6)):
			n.global_position.y -= a.position.y - top
			n.set_meta("settled", "furniture")
			continue
		if a.size.y >= float(cfg.get("drop_min_height", 0.45)) or a.position.y < float(cfg.get("min_support", 0.3)) or not cfg.has("asset"):
			n.global_position.y -= a.position.y
			n.set_meta("settled", "floor")
			continue
		var sup := piece(str(cfg.asset), Vector3(c.x, 0, c.z), Vector3.ONE, 0.0, "dressing")
		var sb := world_aabb(sup)
		if sb.size.y <= 0.01: continue
		var k := clampf(a.position.y / sb.size.y, float(cfg.get("min_scale", 0.6)), float(cfg.get("max_scale", 1.0)))
		sup.scale = Vector3(1, k, 1)
		sb = world_aabb(sup)
		n.global_position.y += sb.end.y - a.position.y
		n.set_meta("settled", "support")
		nodes.append(sup)
	# Settling is a one-shot deterministic placement operation, not animation.
	# Freeze its result; subsequent rendered mesh/camera transforms have no say.
	for source in solid_sources.values():
		if is_instance_valid(source.node): source.transform = source.node.transform
	build_solid_bodies()

## Pack camera policy (look.camera): a fixed camera authored outside an enclosed shell is pulled inside the
## room on the same side, at eye-ish height, looking across the room. Authored cameras inside are kept.
func inside_camera(anchor: Dictionary, w: float, d: float) -> Dictionary:
	var policy: Dictionary = theme.get("look", {}).get("camera", {})
	if shell_info.is_empty() or str(policy.get("policy", "")) != "inside": return anchor
	var meta: Dictionary = shell_info.get("meta", {})
	var outline: Array = meta.get("walkable_outline_gltf", [])
	if outline.size() < 3: return anchor
	var height := float(meta.get("height", 3.0))
	var c := Vector2(w / 2, d / 2)
	var p := vector(anchor.position)
	var local := Vector2(p.x, p.z) - c
	if Geometry2D.is_point_in_polygon(local, packed(outline)) and p.y < height - 0.3: return anchor
	var dir := local.normalized() if local.length() > 0.01 else Vector2(1, 1).normalized()
	# Elongated rooms are framed along their long axis (corridors read as corridors, not as a far wall).
	var aspect := float(policy.get("long_axis_aspect", 1.4))
	if w / d >= aspect: dir = Vector2(signf(dir.x) if absf(dir.x) > 0.01 else 1.0, dir.y * 0.45).normalized()
	elif d / w >= aspect: dir = Vector2(dir.x * 0.45, signf(dir.y) if absf(dir.y) > 0.01 else 1.0).normalized()
	var r := ray_outline(dir, outline)
	if r <= 0.0: return anchor
	var inset := float(policy.get("inset", 0.7))
	var hp := c + dir * maxf(r - inset, r * 0.5)
	var cy := clampf(float(policy.get("height_frac", 0.72)) * height, 1.5, height - 0.35)
	var tgt := c - dir * r * float(policy.get("target_frac", 0.15))
	var out := anchor.duplicate(true)
	out["position"] = [hp.x, cy, hp.y]
	out["look_at"] = [tgt.x, float(policy.get("target_y", 0.9)), tgt.y]
	out["fov"] = float(policy.get("fov", 66))
	out["reframed"] = true
	return out

## Pack camera policy (look.camera.people): once the room is dressed (after settle), each inside camera is
## re-aimed so the room's people sit in the frame naturally: nobody looming at the lens, figures not stacked
## behind one another, no tall piece crowding the frame next to the lens. Candidates orbit the room centre on the
## inside-camera ring (same inset/height); the authored side is preferred. Deterministic; story data untouched.
func frame_people() -> void:
	var pol: Dictionary = theme.get("look", {}).get("camera", {}).get("people", {})
	if pol.is_empty() or shell_info.is_empty() or presentation.get("exterior", false) or camera_nodes.is_empty() or not is_inside_tree(): return
	var outline: Array = shell_info.get("meta", {}).get("walkable_outline_gltf", [])
	if outline.size() < 3: return
	var w := float(data.grid_size[0])
	var d := float(data.grid_size[1])
	var c := Vector2(w / 2, d / 2)
	var people := []
	var seen := {}
	for n in get_children():
		if str(n.get_meta("placed", "")) != "actor": continue
		var a := world_aabb(n)
		if a.size == Vector3.ZERO: continue
		people.append({"feet": Vector3(a.get_center().x, a.position.y, a.get_center().z), "h": a.size.y, "r": maxf(0.22, maxf(a.size.x, a.size.z) * 0.5), "human": a.size.y > 1.0})
		seen[str(n.name).trim_prefix("actor_")] = true
	var chars: Dictionary = presentation.get("characters", {})
	if chars.has(protagonist_id) and not seen.has(protagonist_id) and (chars[protagonist_id] as Dictionary).has("position"):
		var pp := vector(chars[protagonist_id].position)
		people.append({"feet": Vector3(pp.x, 0, pp.z), "h": 1.75, "r": 0.32, "human": true})
	if people.is_empty(): return
	var occluders := []
	for n in get_children() + get_node("props").get_children():
		var kind := str(n.get_meta("placed", ""))
		if not kind in ["prop", "piece", "dressing", "collectible"]: continue
		var a := world_aabb(n)
		if a.size != Vector3.ZERO and a.size.y >= float(pol.get("occluder_min_height", 0.0)): occluders.append(a)
	var centroid := Vector3.ZERO
	for q in people: centroid += q.feet as Vector3
	centroid /= float(people.size())
	var max_turn := float(pol.get("max_turn", 36.0))
	var steps := int(pol.get("steps", 3))
	var inset := float(theme.get("look", {}).get("camera", {}).get("inset", 0.7))
	for entry in camera_nodes:
		var cam: Camera3D = entry.node
		var p0 := Vector2(cam.position.x, cam.position.z) - c
		if p0.length() < 0.01: continue
		var a0 := atan2(p0.y, p0.x)
		var t0: Vector3 = entry.target
		var tf := float(theme.get("look", {}).get("camera", {}).get("target_frac", 0.2))
		var best_score := INF
		var best_pos := cam.position
		var best_tgt := t0
		var cand := []
		var trace := []
		var top_y := float(shell_info.get("meta", {}).get("height", 3.0)) - 0.35
		for lift in [0.0, float(pol.get("lift", 0.0))]:
			if lift > 0.0 and cam.position.y + lift > top_y: continue
			for dfov in pol.get("fovs", [0]):
				for k in range(-steps, steps + 1):
					cand.append([float(k) / float(maxi(steps, 1)) * max_turn, lift, float(dfov)])
		var fov0 := cam.fov
		var best_fov := fov0
		for cnd in cand:
			var off: float = cnd[0]
			var ang := a0 + deg_to_rad(off)
			var dir := Vector2(cos(ang), sin(ang))
			var r := ray_outline(dir, outline)
			if r <= 0.0: continue
			var hp := c + dir * maxf(r - inset, r * 0.5)
			var pos := Vector3(hp.x, cam.position.y + float(cnd[1]), hp.y)
			var room_t := c - dir * r * tf
			var tgt := Vector3(room_t.x, t0.y, room_t.y).lerp(Vector3(centroid.x, t0.y, centroid.z), float(pol.get("centroid_weight", 0.35)))
			var fov: float = fov0 + float(cnd[2])
			var score := float(pol.get("turn_cost", 1.0)) * absf(off) / maxf(max_turn, 1.0) + float(pol.get("fov_cost", 0.08)) * absf(float(cnd[2]))
			var parts := [0.0, 0.0, 0.0, 0.0]
			var rects := []
			for q in people:
				var qf: Vector3 = q.feet
				var feet := project(qf, pos, tgt, fov)
				var head := project(qf + Vector3(0, float(q.h), 0), pos, tgt, fov)
				if feet.z <= 0.0 or head.z <= 0.0:
					score += 6.0
					parts[0] += 6.0
					continue
				var half: float = float(q.r) / (feet.z * tan(deg_to_rad(fov) * 0.5) * 4.0 / 3.0)
				var size: float = (head.y - feet.y) * 0.5
				if absf(feet.x) > 0.9 or feet.y < -0.97 or head.y > 0.97:
					score += 3.0
					parts[0] += 3.0
				if size > float(pol.get("max_size", 0.42)):
					score += (size - float(pol.get("max_size", 0.42))) * float(pol.get("size_cost", 12.0))
					parts[1] += (size - float(pol.get("max_size", 0.42))) * float(pol.get("size_cost", 12.0))
				rects.append([feet.x - half, feet.x + half, feet.y, head.y, feet.z, q.human])
			for i in rects.size():
				for j in range(i + 1, rects.size()):
					var ra: Array = rects[i]
					var rb: Array = rects[j]
					var ov: float = minf(ra[1], rb[1]) - maxf(ra[0], rb[0])
					var vov: float = minf(ra[3], rb[3]) - maxf(ra[2], rb[2])
					if ov > 0.0 and vov > 0.0 and absf(float(ra[4]) - float(rb[4])) > 0.6:
						var wgt := float(pol.get("stack_human", 1.0)) if (ra[5] and rb[5]) else (float(pol.get("stack_animal", 0.35)) if (ra[5] or rb[5]) else 0.1)
						var sc_: float = wgt * float(pol.get("stack_cost", 6.0)) * minf(1.0, ov / maxf(0.01, minf(float(ra[1]) - float(ra[0]), float(rb[1]) - float(rb[0]))))
						score += sc_
						parts[2] += sc_
			for a in occluders:
				var lo := Vector2(INF, INF)
				var hi := Vector2(-INF, -INF)
				var near := INF
				for k in 8:
					var q := project(a.get_endpoint(k), pos, tgt, fov)
					if q.z <= 0.05: continue
					near = minf(near, q.z)
					lo = lo.min(Vector2(q.x, q.y))
					hi = hi.max(Vector2(q.x, q.y))
				if near == INF or near > float(pol.get("occluder_near", 3.2)): continue
				var cov := maxf(0.0, minf(hi.x, 1.0) - maxf(lo.x, -1.0)) * maxf(0.0, minf(hi.y, 1.0) - maxf(lo.y, -1.0)) / 4.0
				score += float(pol.get("occluder_cost", 8.0)) * maxf(0.0, cov - float(pol.get("occluder_free", 0.03)))
				parts[3] += float(pol.get("occluder_cost", 8.0)) * maxf(0.0, cov - float(pol.get("occluder_free", 0.03)))
			trace.append([off, cnd[1], cnd[2], snappedf(score, 0.01), snappedf(parts[0], 0.01), snappedf(parts[1], 0.01), snappedf(parts[2], 0.01), snappedf(parts[3], 0.01)])
			if score < best_score - 0.0001:
				best_score = score
				best_pos = pos
				best_tgt = tgt
				best_fov = fov
		cam.set_meta("framing", {"people": people.size(), "occluders": occluders.size(), "scores": trace})
		if best_pos.distance_to(cam.position) > 0.01 or best_tgt.distance_to(t0) > 0.01 or absf(best_fov - fov0) > 0.01:
			cam.position = best_pos
			entry.target = best_tgt
			cam.fov = best_fov
			cam.set_meta("people_framed", snappedf(best_score, 0.01))

## Camera-space projection without a viewport (x, y in -1..1 of the 4:3 frame, z = depth; z < 0 behind).
static func project(p: Vector3, cam: Vector3, tgt: Vector3, fov: float) -> Vector3:
	var f := (tgt - cam).normalized()
	var r := f.cross(Vector3.UP).normalized()
	var u := r.cross(f)
	var v := p - cam
	var z := v.dot(f)
	if z <= 0.05: return Vector3(0, 0, -1)
	var ty := tan(deg_to_rad(fov) * 0.5)
	return Vector3(v.dot(r) / (z * ty * 4.0 / 3.0), v.dot(u) / (z * ty), z)

static func packed(outline: Array) -> PackedVector2Array:
	var out := PackedVector2Array()
	for q in outline: out.append(Vector2(float(q[0]), float(q[1])))
	return out

## Distance from the plan centre to its outline along dir (outline in glTF x/z relative to the centre).
static func ray_outline(dir: Vector2, outline: Array) -> float:
	var best := -1.0
	for i in outline.size():
		var a := Vector2(float(outline[i][0]), float(outline[i][1]))
		var b := Vector2(float(outline[(i + 1) % outline.size()][0]), float(outline[(i + 1) % outline.size()][1]))
		var hit = Geometry2D.segment_intersects_segment(Vector2.ZERO, dir * 1000.0, a, b)
		if hit != null:
			var t: float = (hit as Vector2).length()
			if best < 0.0 or t < best: best = t
	return best

static func is_warm(c: Color) -> bool:
	return c.s >= 0.3 and c.h * 360.0 >= 8.0 and c.h * 360.0 <= 62.0

## Pack accent rule (look.accent_fallback): every interior shows at least one warm practical light. When no placed
## asset is a warm emitter, the pack's fallback lamp goes to the free spot on the far side of the room (seen by
## the fixed camera), away from doors, props and actors. Deterministic; no effect when the room already has one.
func ensure_accent() -> void:
	var fb: Dictionary = theme.get("look", {}).get("accent_fallback", {})
	var emitters: Dictionary = theme.get("look", {}).get("emitters", {})
	if fb.is_empty() or presentation.get("exterior", false) or not is_inside_tree(): return
	var w := float(data.grid_size[0])
	var d := float(data.grid_size[1])
	var c := Vector2(w / 2, d / 2)
	# the fixed camera actually used for the room (first anchor): accents must sit inside its horizontal view
	var cam_pos := Vector2(w * 1.1, d * 1.3)
	var cam_fwd := (c - cam_pos).normalized()
	var half_fov := deg_to_rad(30.0)
	if not camera_nodes.is_empty():
		var cn: Camera3D = camera_nodes[0].node
		var tgt: Vector3 = camera_nodes[0].target
		cam_pos = Vector2(cn.position.x, cn.position.z)
		cam_fwd = (Vector2(tgt.x, tgt.z) - cam_pos).normalized()
		half_fov = atan(tan(deg_to_rad(cn.fov) * 0.5) * 4.0 / 3.0) * 0.8
	var in_view := func(q: Vector2) -> bool:
		var to_q := q - cam_pos
		return to_q.length() >= 1.5 and abs(cam_fwd.angle_to(to_q.normalized())) <= half_fov
	var obstacles := []
	for n in find_children("*", "Node3D", true, false):
		var kind := str(n.get_meta("placed", ""))
		var flat := Vector2(n.global_position.x, n.global_position.z)
		if n.has_meta("asset_ref"):
			var e = emitters.get(str(n.get_meta("asset_ref")), emitters.get(str(n.get_meta("kit_id", "")), null))
			if e is Dictionary and is_warm(Color.from_string(str(e.get("color", "#ffffff")), Color.WHITE)) and in_view.call(flat): return
		if kind in ["prop", "piece", "collectible", "actor", "door", "dressing"]:
			obstacles.append(flat)
	for door in data.get("doors", []):
		var p := float(door.get("position", 0)) + 0.5
		obstacles.append({"north": Vector2(p, 0), "south": Vector2(p, d), "west": Vector2(0, p), "east": Vector2(w, p)}.get(door.wall, Vector2(w / 2, d / 2)))
	var outline: Array = shell_info.get("meta", {}).get("walkable_outline_gltf", [])
	var inset := float(fb.get("inset", 0.9))
	var best := Vector2(-1, -1)
	var best_score := -INF
	for k in 16:
		var dir := Vector2(cos(TAU * (k + 0.5) / 16.0), sin(TAU * (k + 0.5) / 16.0))
		var reach := ray_outline(dir, outline) if outline.size() >= 3 else minf(abs(w / 2 / dir.x) if abs(dir.x) > 0.01 else INF, abs(d / 2 / dir.y) if abs(dir.y) > 0.01 else INF)
		if reach <= inset + 0.3: continue
		var q := c + dir * (reach - inset)
		if not in_view.call(q): continue
		var clear := INF
		for o in obstacles: clear = minf(clear, q.distance_to(o))
		var score := minf(clear, 3.0) + 0.15 * minf((q - cam_pos).length(), 8.0)
		if clear > float(fb.get("clearance", 0.9)) and score > best_score:
			best_score = score
			best = q
	if best.x < 0: return
	var sc := float(fb.get("scale", 1.0))
	var lamp := piece(str(fb.asset), Vector3(best.x, 0, best.y), Vector3(sc, sc, sc), 0.0, "prop")
	lamp.set_meta("accent_fallback", true)
	lamp.set_meta("emitter_scale", float(fb.get("intensity_scale", 0.5)))  # an accent, not a new key light

## Look profile for this room: presentation override, then pack kit_ref mapping, then interior/exterior.
func profile_name() -> String:
	if presentation.has("look_profile"): return str(presentation.look_profile)
	var by_ref: Dictionary = theme.get("look", {}).get("profile_by_kit_ref", {})
	for ref in data.get("kit_refs", []):
		if by_ref.has(ref): return str(by_ref[ref])
	return "exterior" if presentation.get("exterior", false) else "interior"

## Point lights from pack emitter data (look.emitters keyed by asset ref or kit id), strongest first.
func gather_lights() -> void:
	var emitters: Dictionary = theme.get("look", {}).get("emitters", {})
	if emitters.is_empty(): return
	var found := []
	for n in find_children("*", "Node3D", true, false):
		if not n.has_meta("asset_ref"): continue
		var e = emitters.get(str(n.get_meta("asset_ref")), emitters.get(str(n.get_meta("kit_id", "")), null))
		if not e is Dictionary: continue
		var off: Array = e.get("offset", [0, 1.2, 0])
		var pos: Vector3 = n.global_transform * Vector3(float(off[0]), float(off[1]), float(off[2]))
		var lc := Color.from_string(str(e.get("color", "#ffffff")), Color.WHITE)
		var es := float(n.get_meta("emitter_scale", 1.0))
		found.append({"pos": pos, "color": lc, "intensity": float(e.get("intensity", 1.0)) * es, "radius": float(e.get("radius", 4.0)) * (0.5 + 0.5 * es), "source": str(n.name)})
		# N64 look convention (theme "n64".lighting): painted floor pools and small lamp sprites, never bloom-sized
		var cl: Dictionary = theme.get("n64", {}).get("lighting", {})
		if e.has("pool") and not n.has_meta("glow_done"):
			var pool: Array = e.pool
			var ps := float(pool[1])
			if cl.get("lamp_pool", {}).has("max_strength"): ps = minf(ps, float(cl.lamp_pool.max_strength))
			# pool_color: the painted pool's own tint (a pale warm pool stays warm-white on a cool floor instead of
			# drifting to lavender); defaults to the light colour
			var pc := Color.from_string(str(e.get("pool_color", e.get("color", "#ffffff"))), lc)
			glow_card(Vector3(pos.x, 0.03, pos.z), float(pool[0]), pc, ps, 0)
		if e.has("halo") and not n.has_meta("glow_done"):
			var halo: Array = e.halo
			var hsize := float(halo[0])
			var hstr := float(halo[1])
			if cl.get("halo", {}).has("max_size_m"): hsize = minf(hsize, float(cl.halo.max_size_m))
			if cl.get("halo", {}).has("max_strength"): hstr = minf(hstr, float(cl.halo.max_strength))
			# halo_color: an additive glow over the cool room shifts toward magenta; a yellower halo reads amber
			var hc := Color.from_string(str(e.get("halo_color", e.get("color", "#ffffff"))), lc)
			if str(e.get("halo_mode", "add")) == "mix":
				var hm := halo_card(pos, hsize * float(n.get_meta("emitter_halo", 1.0)), hc, hstr, float(e.get("halo_softness", 1.3)))
				(hm.material_override as ShaderMaterial).set_shader_parameter("pull", float(e.get("halo_pull", 0.35)))
			else: glow_card(pos, hsize, hc, hstr, 1)
		if e.has("tint_roles") and not n.has_meta("glow_done"): tint_roles(n, e.tint_roles)
		n.set_meta("glow_done", true)
	for extra in presentation.get("lights", []):
		found.append({"pos": vector(extra.position), "color": Color.from_string(str(extra.get("color", "#ffffff")), Color.WHITE), "intensity": float(extra.get("intensity", 1.0)), "radius": float(extra.get("radius", 4.0)), "source": "presentation"})
	found.sort_custom(func(a, b): return a.intensity * a.radius > b.intensity * b.radius)
	lights = found.slice(0, 4)

## Per-instance surface tint for emitters (e.g. a lamp's "light" role glows warm); materials are duplicated so
## other instances of the same kit piece keep the pack default.
func tint_roles(n: Node, roles: Dictionary) -> void:
	for mi in n.find_children("*", "MeshInstance3D", true, false) + ([n] if n is MeshInstance3D else []):
		for i in mi.mesh.get_surface_count():
			var m = mi.get_surface_override_material(i)
			if m is ShaderMaterial and roles.has(str(m.get_meta("role", ""))):
				var mm: ShaderMaterial = m.duplicate()
				mm.set_shader_parameter("tint", Color.from_string(str(roles[m.get_meta("role")]), Color.WHITE))
				mi.set_surface_override_material(i, mm)

## Additive glow sprite: mode 0 = light pool lying on the floor, 1 = camera-facing halo.
func glow_card(pos: Vector3, size: float, c: Color, strength: float, mode: int) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = preload("res://shaders/n64_glow.gdshader")
	m.set_shader_parameter("color", c)
	m.set_shader_parameter("strength", strength)
	m.set_shader_parameter("mode", mode)
	mi.material_override = m
	mi.position = pos
	if mode == 0: mi.rotation_degrees.x = -90.0
	mi.name = "glow_pool" if mode == 0 else "glow_halo"
	mi.set_meta("placed", "light")
	add_child(mi)
	return mi

## Mixed (not additive) camera-facing halo: keeps a warm lamp warm over a cool room.
func halo_card(pos: Vector3, size: float, c: Color, strength: float, softness := 1.3) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = preload("res://shaders/n64_halo.gdshader")
	m.set_shader_parameter("color", c)
	m.set_shader_parameter("strength", strength)
	m.set_shader_parameter("softness", softness)
	mi.material_override = m
	mi.position = pos
	mi.name = "glow_halo"
	mi.set_meta("placed", "light")
	add_child(mi)
	return mi

## Blob shadows (look.shadows): a soft dark disc under every floor-standing prop/furniture piece, after settle().
## Actors are excluded (their presentation belongs to the character seam).
func blob_shadows() -> void:
	var cfg: Dictionary = theme.get("look", {}).get("shadows", {})
	if cfg.is_empty() or not is_inside_tree(): return
	var kinds: Array = cfg.get("kinds", ["prop", "piece", "collectible", "dressing"])
	var col := Color.from_string(str(cfg.get("color", "#04050c")), Color.BLACK)
	for n in find_children("*", "Node3D", true, false):
		if not n.has_meta("placed") or not str(n.get_meta("placed")) in kinds or n.has_meta("shadowed"): continue
		var a := world_aabb(n)
		if a.size == Vector3.ZERO or a.position.y > float(cfg.get("max_lift", 0.08)): continue
		var sz := clampf(maxf(a.size.x, a.size.z) * float(cfg.get("scale", 1.25)), float(cfg.get("min", 0.4)), float(cfg.get("max", 3.0)))
		var c := a.get_center()
		disc_card(Vector3(c.x, maxf(a.position.y, 0.0) + 0.012, c.z), sz, col, float(cfg.get("strength", 0.5)), "blob_shadow")
		n.set_meta("shadowed", true)

## Soft blended floor disc (blob shadow / painted light pool), local to the room.
func disc_card(pos: Vector3, size: float, col: Color, strength: float, label: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	var q := QuadMesh.new()
	q.size = Vector2(size, size)
	mi.mesh = q
	var m := ShaderMaterial.new()
	m.shader = preload("res://shaders/n64_shadow.gdshader")
	m.set_shader_parameter("color", col)
	m.set_shader_parameter("strength", strength)
	mi.material_override = m
	mi.name = label
	mi.set_meta("placed", "light")
	add_child(mi)
	mi.position = pos
	mi.rotation_degrees.x = -90.0
	return mi

## World AABB of every mesh below node (empty AABB when there is no geometry).
static func world_aabb(node: Node) -> AABB:
	var out := AABB()
	var first := true
	var stack: Array = [node]
	while not stack.is_empty():
		var n = stack.pop_back()
		if n is MeshInstance3D and n.mesh != null and n.visible:
			var box: AABB = n.global_transform * n.get_aabb()
			if first: out = box
			else: out = out.merge(box)
			first = false
		for c in n.get_children(): stack.append(c)
	return out

## Geometry audit for the style gate: floating pieces, uncut doors, camera placement.
## Structural kinds (floor/wall/shell/window/door) are mounted by definition; everything else must rest
## on the floor, on another piece, or be mounted against the room boundary.
func audit(cam: Camera3D = null) -> Dictionary:
	var w: float = data.grid_size[0]
	var d: float = data.grid_size[1]
	var rows := []
	for n in find_children("*", "Node3D", true, false):
		if n.has_meta("placed"): rows.append({"node": n, "kind": str(n.get_meta("placed")), "box": world_aabb(n)})
	var floating := []
	var structural := ["floor", "wall", "shell", "window", "door", "backdrop", "light", "yard", "landmark", "vista", "sky", "particles"]
	for r in rows:
		if r.kind in structural or r.kind == "actor": continue
		var a: AABB = r.box
		if a.size == Vector3.ZERO: continue
		var bottom := a.position.y
		if bottom <= 0.06: continue
		if r.node.get_meta("mounted", false): continue
		var near_wall: bool = a.position.x < 0.35 or a.end.x > w - 0.35 or a.position.z < 0.35 or a.end.z > d - 0.35
		if near_wall and r.kind in ["dressing", "piece"] and a.size.y > 0.0 and r.node.get_meta("wall_ok", false): continue
		var supported := false
		var cx := a.get_center().x
		var cz := a.get_center().z
		for s in rows:
			if s == r or s.kind in ["actor", "shell", "backdrop", "light", "yard", "vista", "particles"]: continue
			var b: AABB = s.box
			if b.size == Vector3.ZERO: continue
			if cx < b.position.x - 0.05 or cx > b.end.x + 0.05 or cz < b.position.z - 0.05 or cz > b.end.z + 0.05: continue
			if b.end.y >= bottom - 0.15 and b.position.y <= bottom + 0.05:
				supported = true
				break
		if not supported:
			floating.append({"name": str(r.node.name), "kind": r.kind, "bottom": snappedf(bottom, 0.01), "center": [snappedf(cx, 0.01), snappedf(a.get_center().y, 0.01), snappedf(cz, 0.01)]})
	var doors := []
	for r in rows:
		if r.kind == "door": doors.append({"name": str(r.node.name), "cut": bool(r.node.get_meta("opening_cut", false))})
	var landmarks := []
	for r in rows:
		if r.kind == "landmark" and r.box.size != Vector3.ZERO:
			landmarks.append({"name": str(r.node.name), "in_view": cam != null and cam.is_position_in_frustum(r.box.get_center()),
				"distance": snappedf(cam.global_position.distance_to(r.box.get_center()), 0.1) if cam != null else 0.0})
	var cam_info := {}
	if cam != null:
		var p := cam.global_position
		cam_info = {"position": [snappedf(p.x, 0.01), snappedf(p.y, 0.01), snappedf(p.z, 0.01)], "inside_bounds": p.x > 0.0 and p.x < w and p.z > 0.0 and p.z < d and p.y < float(presentation.get("wall_height", 3.2)), "framing": cam.get_meta("framing", {})}
	return {"landmarks": landmarks, "landmarks_in_view": landmarks.filter(func(x): return x.in_view).size(), "look_profile": str(get_meta("look_profile", "")), "fog_color": "#" + str(get_meta("fog_color", "")) if has_meta("fog_color") else "", "lights": lights.map(func(l): return {"source": l.source, "intensity": l.intensity}), "floating": floating, "doors": doors, "uncut_doors": doors.filter(func(x): return not x.cut).size(), "camera": cam_info, "exterior": bool(presentation.get("exterior", false)), "placed": rows.size(), "marks": {"trail": find_children("trail*", "", false, false).size(), "drift": find_children("drift*", "", false, false).size(), "path": get_meta("trail", {})}}

static func door_position(door: Dictionary, grid: Array) -> Vector3:
	var p: float = door.position + 0.5
	match door.wall:
		"north": return Vector3(p, 0, 0.4)
		"south": return Vector3(p, 0, grid[1] - 0.4)
		"east": return Vector3(grid[0] - 0.4, 0, p)
	return Vector3(0.4, 0, p)
