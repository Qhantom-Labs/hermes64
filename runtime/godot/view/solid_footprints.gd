extends RefCounted
## Immutable simulation geometry. No MeshInstance, rendered pose or camera reads.
## The kit catalog is a compact copy of existing manifest metadata, keyed by the
## exact immutable asset SHA (never by a fuzzy asset name). Legacy bindings lacking
## footprint metadata fall back to glTF POSITION-accessor bounds, then 0.7 m boxes.
const WALKTHROUGH := ["arch.door","arch.window","arch.floor_module","arch.ceiling_module","arch.roof","arch.stairs","arch.bridge","arch.pier","nature.grass","nature.flower","soft.rug","soft.blanket","terrain.patch","sky.backdrop"]
static var bounds_cache := {}
static var catalog: Dictionary = {}
static var catalog_loaded := false

static func vec(a: Array) -> Vector3:
	return Vector3(float(a[0]),float(a[1]),float(a[2]))

static func kit_metadata(binding: Dictionary) -> Dictionary:
	if not catalog_loaded:
		catalog_loaded = true
		if FileAccess.file_exists("res://view/solid_kit_metadata.json"):
			var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://view/solid_kit_metadata.json"))
			if parsed is Dictionary: catalog = parsed.get("assets",{})
	var out: Dictionary = catalog.get(str(binding.get("sha256","")),{}).get("meta",{}).duplicate(true)
	out.merge(binding.get("meta",{}),true)
	return out

static func node_transform(row: Dictionary) -> Transform3D:
	if row.has("matrix"):
		var m: Array = row.matrix
		return Transform3D(Basis(Vector3(m[0],m[1],m[2]),Vector3(m[4],m[5],m[6]),Vector3(m[8],m[9],m[10])),Vector3(m[12],m[13],m[14]))
	var q: Array = row.get("rotation",[0,0,0,1])
	var b := Basis(Quaternion(float(q[0]),float(q[1]),float(q[2]),float(q[3])))
	return Transform3D(b.scaled_local(vec(row.get("scale",[1,1,1]))),vec(row.get("translation",[0,0,0])))

static func gltf_bounds(doc: Dictionary) -> AABB:
	var nodes: Array = doc.get("nodes",[])
	var todo := []
	var scenes: Array = doc.get("scenes",[])
	if not scenes.is_empty():
		for i in scenes[int(doc.get("scene",0))].get("nodes",[]): todo.append([int(i),Transform3D.IDENTITY])
	else:
		var children := {}
		for n in nodes:
			for i in n.get("children",[]): children[int(i)] = true
		for i in nodes.size():
			if not children.has(i): todo.append([i,Transform3D.IDENTITY])
	var box := AABB()
	var found := false
	while not todo.is_empty():
		var entry: Array = todo.pop_back()
		var n: Dictionary = nodes[entry[0]]
		var at: Transform3D = entry[1] * node_transform(n)
		if n.has("mesh"):
			for primitive in doc.get("meshes",[])[int(n.mesh)].get("primitives",[]):
				if not primitive.get("attributes",{}).has("POSITION"): continue
				var a: Dictionary = doc.get("accessors",[])[int(primitive.attributes.POSITION)]
				if not a.has("min") or not a.has("max"): continue
				var part: AABB = at * AABB(vec(a.min),vec(a.max)-vec(a.min))
				box = box.merge(part) if found else part
				found = true
		for i in n.get("children",[]): todo.append([int(i),at])
	return box

static func asset_bounds(binding: Dictionary) -> AABB:
	var path := str(binding.get("path",""))
	var key := path + ":" + str(binding.get("sha256",""))
	if bounds_cache.has(key): return bounds_cache[key]
	var box := AABB()
	if path != "" and FileAccess.file_exists(path):
		var file := FileAccess.open(path,FileAccess.READ)
		if file != null and file.get_length() >= 20 and file.get_32() == 0x46546c67:
			var version := file.get_32()
			file.get_32()
			var length := file.get_32()
			var chunk := file.get_32()
			if version == 2 and chunk == 0x4e4f534a and length <= file.get_length()-20:
				var parsed = JSON.parse_string(file.get_buffer(length).get_string_from_utf8())
				if parsed is Dictionary: box = gltf_bounds(parsed)
	bounds_cache[key] = box
	return box

static func definition(id: String, ref: String, placement: Transform3D, binding: Dictionary = {}) -> Dictionary:
	var meta := kit_metadata(binding)
	var kit := str(binding.get("kit_id",ref))
	if bool(binding.get("pickup",false)) or bool(meta.get("walkthrough",false)) or kit in WALKTHROUGH: return {}
	if bool(binding.get("actor",false)):
		var radius := 0.23 if bool(binding.get("animal",false)) else 0.3
		var height := 0.65 if bool(binding.get("animal",false)) else 1.55
		return {"id":id,"ref":ref,"box":AABB(Vector3(-radius,0,-radius),Vector3(radius*2,height,radius*2)),"transform":Transform3D(Basis.IDENTITY,placement.origin),"source":"actor_capsule","radius":radius}
	var box := asset_bounds(binding)
	var source := "gltf_bounds"
	if box.size == Vector3.ZERO:
		box = AABB(Vector3(-0.35,0,-0.35),Vector3(0.7,0.7,0.7))
		source = "fallback"
	if meta.has("bbox_size_m"):
		var size: Array = meta.bbox_size_m # kit generator convention: Blender Z up
		var sz := Vector3(float(size[0]),float(size[2]),float(size[1]))
		box = AABB(Vector3(-sz.x/2,0,-sz.z/2),sz) if source == "fallback" else AABB(box.get_center()-sz/2,sz)
		source = "kit_bbox"
	var polygons := []
	for socket in meta.get("sockets",[]):
		if not socket.has("footprint_m"): continue
		var footprint = socket.footprint_m
		var size := Vector2(float(footprint[0]),float(footprint[1])) if footprint is Array else Vector2.ONE*float(footprint)
		var at := vec(socket.get("position",socket.get("pos_gltf",[0,0,0])))
		polygons.append(PackedVector2Array([Vector2(at.x-size.x/2,at.z-size.y/2),Vector2(at.x+size.x/2,at.z-size.y/2),Vector2(at.x+size.x/2,at.z+size.y/2),Vector2(at.x-size.x/2,at.z+size.y/2)]))
		source = "socket"
	if meta.get("footprint_gltf",[]).size() >= 3:
		var outline := PackedVector2Array()
		for p in meta.footprint_gltf: outline.append(Vector2(float(p[0]),float(p[1])))
		polygons.clear()
		# Triangulation preserves concave passages; a convex hull would fill them.
		var triangles := Geometry2D.triangulate_polygon(outline)
		for i in range(0,triangles.size(),3): polygons.append(PackedVector2Array([outline[triangles[i]],outline[triangles[i+1]],outline[triangles[i+2]]]))
		source = "footprint"
	elif meta.has("walkable_inner_radius_m"):
		polygons.clear()
		var inner := float(meta.walkable_inner_radius_m)
		var outer := Vector2(box.size.x,box.size.z)*0.5/cos(PI/16.0)
		for i in 16:
			var a := Vector2(cos(TAU*i/16.0),sin(TAU*i/16.0))
			var b := Vector2(cos(TAU*(i+1)/16.0),sin(TAU*(i+1)/16.0))
			polygons.append(PackedVector2Array([a*outer,b*outer,b*inner,a*inner]))
		var params: Dictionary = catalog.get(str(binding.get("sha256","")),{}).get("params",{}).duplicate(true)
		params.merge(binding.get("params",{}),true)
		if bool(params.get("table",false)):
			var table := PackedVector2Array()
			var r := minf(box.size.x,box.size.z)*0.17*1.02/cos(PI/16.0)
			for i in 16: table.append(Vector2(cos(TAU*i/16.0),sin(TAU*i/16.0))*r)
			polygons.append(table)
		source = "kit_hollow_footprint"
	if not binding.get("kit_obstacles", []).is_empty():   # FEEL4: measured body-height structure (view/kit_shells.gd)
		polygons.clear()
		for poly in binding.kit_obstacles:
			var points := PackedVector2Array()
			for p in poly: points.append(Vector2(float(p[0]), float(p[1])))
			polygons.append(points)
		source = "kit_obstacles"
	if not polygons.is_empty():
		var lo := Vector2(INF,INF); var hi := Vector2(-INF,-INF)
		for polygon in polygons:
			for p in polygon: lo = lo.min(p); hi = hi.max(p)
		box = AABB(Vector3(lo.x,box.position.y,lo.y),Vector3(hi.x-lo.x,box.size.y,hi.y-lo.y))
	# Bake scale into shape dimensions. Never nonuniform-scale a physics body.
	var scale := placement.basis.get_scale().abs()
	box = AABB(box.position * scale,box.size * scale)
	var at := Transform3D(placement.basis.orthonormalized(),placement.origin)
	var result := {"id":id,"ref":ref,"box":box,"transform":at,"source":source}
	if not polygons.is_empty():
		var scaled := []
		for polygon in polygons:
			var points := PackedVector2Array()
			for p in polygon: points.append(p*Vector2(scale.x,scale.z))
			scaled.append(points)
		result["polygons"] = scaled
	return result

static func body_for(row: Dictionary) -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "solid_" + str(row.id).validate_node_name()
	body.set_meta("solid_id",row.id)
	body.collision_layer = 1
	body.collision_mask = 0
	if row.has("polygons"):
		for polygon in row.polygons:
			var shape := CollisionShape3D.new()
			var hull := ConvexPolygonShape3D.new()
			var points := PackedVector3Array()
			for p in polygon:
				points.append(Vector3(p.x,row.box.position.y,p.y))
				points.append(Vector3(p.x,row.box.end.y,p.y))
			hull.points = points
			shape.shape = hull
			body.add_child(shape)
		body.transform = row.transform
		return body
	var shape := CollisionShape3D.new()
	if row.has("radius"):
		var capsule := CapsuleShape3D.new()
		capsule.radius = float(row.radius)
		capsule.height = row.box.size.y
		shape.shape = capsule
	else:
		var box := BoxShape3D.new()
		box.size = row.box.size.max(Vector3.ONE*0.01)
		shape.shape = box
	shape.position = row.box.get_center()
	body.add_child(shape)
	body.transform = row.transform
	return body

static func contains_point(row: Dictionary, point: Vector3, padding := 0.0) -> bool:
	var local: Vector3 = row.transform.affine_inverse() * point
	if row.has("radius"):
		return Vector2(local.x,local.z).length() < float(row.radius)+padding
	if row.has("polygons"):
		var p := Vector2(local.x,local.z)
		for polygon in row.polygons:
			if Geometry2D.is_point_in_polygon(p,polygon): return true
			if padding <= 0.0: continue
			for i in polygon.size():
				var nearest := Geometry2D.get_closest_point_to_segment(p,polygon[i],polygon[(i+1)%polygon.size()])
				if p.distance_squared_to(nearest) < padding*padding: return true
		return false
	var b: AABB = row.box
	var nearest := Vector2(clampf(local.x,b.position.x,b.end.x),clampf(local.z,b.position.z,b.end.z))
	if padding <= 0.0:
		return local.x > b.position.x-padding and local.x < b.end.x+padding and local.z > b.position.z-padding and local.z < b.end.z+padding
	return Vector2(local.x,local.z).distance_squared_to(nearest) < padding*padding

static func near_edge(row: Dictionary, from: Vector3) -> Vector3:
	var p: Vector3 = row.transform.affine_inverse() * from
	var q := Vector3(p.x,0,p.z)
	if row.has("radius"):
		var direction := Vector2(p.x,p.z).normalized()
		if direction == Vector2.ZERO: direction = Vector2.LEFT
		q = Vector3(direction.x,0,direction.y)*(float(row.radius)+0.025)
	elif row.has("polygons"):
		var flat := Vector2(p.x,p.z)
		var best := INF
		for polygon in row.polygons:
			var inside := Geometry2D.is_point_in_polygon(flat,polygon)
			for i in polygon.size():
				var a: Vector2 = polygon[i]; var b: Vector2 = polygon[(i+1)%polygon.size()]
				var nearest := Geometry2D.get_closest_point_to_segment(flat,a,b)
				var distance := flat.distance_squared_to(nearest)
				if distance >= best: continue
				var normal := (flat-nearest).normalized()
				if inside or normal == Vector2.ZERO:
					normal = Vector2((b-a).y,-(b-a).x).normalized()
					if Geometry2D.is_point_in_polygon((a+b)*0.5+normal*0.01,polygon): normal = -normal
				var edge := nearest+normal*0.025
				var candidate := Vector3(edge.x,0,edge.y)
				if contains_point(row,row.transform*candidate): continue
				q = candidate; best = distance
	else:
		var b: AABB = row.box
		q.x = clampf(p.x,b.position.x,b.end.x)
		q.z = clampf(p.z,b.position.z,b.end.z)
		var n := Vector3(p.x-q.x,0,p.z-q.z).normalized()
		if n == Vector3.ZERO:
			var distances := [p.x-b.position.x,b.end.x-p.x,p.z-b.position.z,b.end.z-p.z]
			var side := distances.find(distances.min())
			n = [Vector3.LEFT,Vector3.RIGHT,Vector3.FORWARD,Vector3.BACK][side]
			if side == 0: q.x = b.position.x
			elif side == 1: q.x = b.end.x
			elif side == 2: q.z = b.position.z
			else: q.z = b.end.z
		q += n*0.025
	return row.transform * q

static func target_point(rows: Array, anchor: Vector3, from: Vector3) -> Vector3:
	var best := INF
	var result := anchor
	for row in rows:
		# Footprint containment is intentionally 2D for navigation. Prompt edges
		# must additionally ignore water/ground dressing wholly below both feet
		# and target; otherwise its huge plane swallows every actor's anchor.
		var world_box: AABB=row.transform*row.box
		if world_box.end.y < minf(anchor.y,from.y): continue
		if not contains_point(row,anchor): continue
		var edge := near_edge(row,from)
		edge.y = anchor.y
		var exposed := true
		for other in rows:
			var other_box: AABB=other.transform*other.box
			if other_box.end.y < minf(anchor.y,from.y): continue
			if contains_point(other,edge): exposed = false; break
		if not exposed: continue
		var score := edge.distance_squared_to(from)
		if score < best:
			best = score
			result = edge
	return result
