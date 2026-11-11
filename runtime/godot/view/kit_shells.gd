extends RefCounted
## FEEL4: solid kit-shell rooms. A room assembled from kit pieces (presentation "kit_shell": true) whose structure is
## placed as pieces of kind "shell" had no boundary but the grid rectangle: players walked through shell walls, off
## roof parapets, into facades and through structures built into a shell (a roof hut). The walkable outline and the
## body-height obstacles of every kit SHELL/landmark GLB are measured offline (tools/feel4_shells.py ->
## view/shell_kit_metadata.json) and looked up here by the exact immutable GLB sha256 (never by an asset name).
##   container shell (walls around a floor): its inner-wall rectangle is walkable
##   floor shell (street, sidewalk, plaza):  its surface is walkable
##   the union of the placed walkable outlines, clipped to the grid, is the room boundary (room.gd build_boundary)
##   obstacles (a hut inside a shell, facade slabs, sign legs): solids, like props (view/solid_footprints.gd)
## Doors stay contextual portals: a door walk target outside the new boundary moves inside it, 0.7 m in from the wall
## (the pack-shell rule in room.gd place_openings). Rooms without measured kit-shell pieces are untouched.
const CATALOG := "res://view/shell_kit_metadata.json"
const DOOR_INSET_M := 0.7
const INWARD := {"north": Vector2(0, 1), "south": Vector2(0, -1), "west": Vector2(1, 0), "east": Vector2(-1, 0)}
static var catalog: Dictionary = {}
static var loaded := false

static func meta_for(binding: Dictionary) -> Dictionary:
	if not loaded:
		loaded = true
		if FileAccess.file_exists(CATALOG):
			var parsed = JSON.parse_string(FileAccess.get_file_as_string(CATALOG))
			if parsed is Dictionary: catalog = parsed.get("assets", {})
	return catalog.get(str(binding.get("sha256", "")), {}).get("meta", {})

static func room_polygon(points: Array, xf: Transform3D) -> PackedVector2Array:
	var out := PackedVector2Array()
	for p in points:
		var at: Vector3 = xf * Vector3(float(p[0]), 0.0, float(p[1]))
		out.append(Vector2(at.x, at.z))
	return out

static func area(poly: PackedVector2Array) -> float:
	var a := 0.0
	for i in poly.size(): a += poly[i].cross(poly[(i + 1) % poly.size()])
	return absf(a) * 0.5

## Called by room.gd for each placed presentation piece of a kit_shell room.
static func collect(room, ref: String, node: Node3D, kind: String, mounted: bool, w: float, d: float) -> void:
	var raw = room.asset_resolver.mapping.get(ref, {})
	if not raw is Dictionary: return
	var meta := meta_for(raw)
	if meta.is_empty(): return
	var at := node.position
	if kind == "shell":
		if meta.get("walkable_outline_gltf", []).size() >= 3:
			room.kit_outlines.append(room_polygon(meta.walkable_outline_gltf, node.transform))
	elif kind != "landmark" or mounted or absf(at.y) > 0.5 or at.x <= 0.0 or at.x >= w or at.z <= 0.0 or at.z >= d:
		return   # landmarks block only when they stand on this room's floor
	if not meta.get("obstacles_gltf", []).is_empty():
		room.register_solid("kit:%02d:%s" % [room.kit_outlines.size() * 100 + room.solid_sources.size(), ref], ref, node, {"kit_obstacles": meta.obstacles_gltf})

## Largest connected union of the walkable outlines (outer boundary). Neighbouring floor tiles share edges exactly,
## so each is grown by 5 mm before the union to make the shared edge an overlap.
static func union(polys: Array) -> PackedVector2Array:
	var pending := []
	for p in polys:
		if p.size() < 3: continue
		var grown := Geometry2D.offset_polygon(p, 0.005, Geometry2D.JOIN_MITER)
		pending.append(grown[0] if grown.size() == 1 else p)
	if pending.is_empty(): return PackedVector2Array()
	pending.sort_custom(func(a, b): return area(a) > area(b))
	var acc: PackedVector2Array = pending.pop_front()
	var merged := true
	while merged and not pending.is_empty():
		merged = false
		for i in pending.size():
			if Geometry2D.intersect_polygons(acc, pending[i]).is_empty(): continue
			var best := PackedVector2Array()
			for poly in Geometry2D.merge_polygons(acc, pending[i]):
				if area(poly) > area(best): best = poly
			acc = best
			pending.remove_at(i)
			merged = true
			break
	return acc

## Door walk targets outside the boundary move inside it (see header). Story ids and door visuals are unchanged.
static func doors_inside(room) -> void:
	var outline: PackedVector2Array = room.boundary_outline
	if outline.size() < 3: return
	for door in room.data.get("doors", []):
		var key := "move:%s:%s" % [room.data.id, door.id]
		if not room.target_positions.has(key): continue
		var at: Vector3 = room.target_positions[key]
		var p := Vector2(at.x, at.z)
		if Geometry2D.is_point_in_polygon(p, outline): continue
		var nearest := p
		var best := INF
		for i in outline.size():
			var q := Geometry2D.get_closest_point_to_segment(p, outline[i], outline[(i + 1) % outline.size()])
			if p.distance_squared_to(q) < best: best = p.distance_squared_to(q); nearest = q
		var inside: Vector2 = nearest + INWARD.get(str(door.wall), Vector2.ZERO) * DOOR_INSET_M
		if not Geometry2D.is_point_in_polygon(inside, outline): continue
		var moved := Vector3(inside.x, at.y, inside.y)
		room.target_positions[key] = moved
		room.target_anchors[key] = moved
