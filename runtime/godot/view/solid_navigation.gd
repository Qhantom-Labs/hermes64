extends RefCounted
## Deterministic capsule-clear grid over the SAME immutable definitions mirrored by
## Room's native bodies. Fixed cell/order, swept segments, no obstacle exemptions.
const Solids = preload("res://view/solid_footprints.gd")
const CELL := 0.25
var rows := []
var bounds := Vector2.ZERO
var radius := 0.26
var height := 1.4
var margin := 0.4
var grid: AStarGrid2D
var free_cells := []

var outline := PackedVector2Array()

func configure(definitions: Array, size: Vector2, capsule_radius := 0.26, capsule_height := 1.4, bounds_margin := 0.4, floor_outline := PackedVector2Array()) -> void:
	rows = definitions.duplicate(true)
	outline = floor_outline
	rows.sort_custom(func(a,b): return str(a.id)<str(b.id))
	bounds = size; radius = capsule_radius; height = capsule_height; margin = bounds_margin
	grid = AStarGrid2D.new()
	grid.region = Rect2i(0,0,ceili(bounds.x/CELL),ceili(bounds.y/CELL))
	grid.cell_size = Vector2.ONE*CELL
	grid.offset = Vector2.ONE*CELL*0.5
	grid.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_ONLY_IF_NO_OBSTACLES
	grid.update()
	free_cells.clear()
	for x in grid.region.size.x:
		for z in grid.region.size.y:
			var cell := Vector2i(x,z)
			var p := point(cell)
			var blocked := not point_clear(p)
			grid.set_point_solid(cell,blocked)
			if not blocked: free_cells.append(cell)

func point(cell: Vector2i) -> Vector3:
	var p := grid.get_point_position(cell)
	return Vector3(p.x,0.001,p.y)

func point_clear(p: Vector3, clearance := -1.0) -> bool:
	var r := radius if clearance < 0.0 else clearance
	# Bounds live in the same float32 vector domain as player/door positions.
	# A double 9.0-0.4 is smaller than Vector3(...,8.6).z; do not mislabel
	# that exact authored boundary as an unreachable exit (or widen the margin).
	var lo := Vector2.ONE*margin
	var hi := bounds-Vector2.ONE*margin
	if p.x < lo.x or p.z < lo.y or p.x > hi.x or p.z > hi.y: return false
	# MOVE: the authored floor outline (room walls/cliffs) blocks like a solid.
	# A zero-clearance probe (prompt edge/target segment) tolerates 5 cm.
	if outline.size() >= 3 and not inside_outline(Vector2(p.x,p.z),r): return false
	for row in rows:
		var world: AABB = row.transform * row.box
		if world.end.y <= p.y or world.position.y >= p.y+height: continue
		if Solids.contains_point(row,p,r): return false
	return true

func inside_outline(p: Vector2, clearance: float) -> bool:
	var inside := Geometry2D.is_point_in_polygon(p,outline)
	var nearest := INF
	for i in outline.size():
		var q := Geometry2D.get_closest_point_to_segment(p,outline[i],outline[(i+1)%outline.size()])
		nearest = minf(nearest,p.distance_to(q))
	if clearance <= 0.0: return inside or nearest <= 0.05
	return inside and nearest >= clearance

func segment_clear(a: Vector3, b: Vector3, clearance := -1.0) -> bool:
	var steps := maxi(1,ceili(Vector2(a.x-b.x,a.z-b.z).length()/0.05))
	for i in range(steps+1):
		if not point_clear(a.lerp(b,float(i)/steps),clearance): return false
	return true

func cell_for(p: Vector3) -> Vector2i:
	return Vector2i(floori(p.x/CELL),floori(p.z/CELL))

func start_cell(start: Vector3) -> Vector2i:
	var found := Vector2i(-1,-1)
	var best := INF
	for cell in free_cells:
		var p := point(cell)
		var distance := Vector2(p.x-start.x,p.z-start.z).length_squared()
		if distance >= best or distance > CELL*CELL*4: continue
		if segment_clear(start,p): found = cell; best = distance
	return found

func safe_spawn(desired: Vector3, max_displacement := 2.0) -> Vector3:
	if point_clear(desired): return desired
	var best := INF
	var found := Vector3.INF
	for cell in free_cells:
		var p := point(cell)
		var distance := Vector2(p.x-desired.x,p.z-desired.z).length_squared()
		if distance > max_displacement*max_displacement or distance >= best: continue
		best = distance
		found = Vector3(p.x,desired.y,p.z)
	return found

func approach(p: Vector3, target: Vector3, edge: bool) -> Vector3:
	return Solids.target_point(rows,target,p) if edge else target

func route(start: Vector3, target: Vector3, reach := 1.0, edge := true) -> PackedVector3Array:
	var from := start_cell(start)
	if from == Vector2i(-1,-1): return PackedVector3Array()
	var goals := []
	for cell in free_cells:
		var p := point(cell)
		var at := approach(p,target,edge)
		if Vector2(p.x-at.x,p.z-at.z).length() > reach: continue
		if absf(at.y-p.y) > 1.8 or not segment_clear(p,at,0.0): continue
		goals.append(cell)
	goals.sort_custom(func(a,b):
		var da := point(a).distance_squared_to(start)
		var db := point(b).distance_squared_to(start)
		return a.x < b.x if is_equal_approx(da,db) and a.y == b.y else (a.y < b.y if is_equal_approx(da,db) else da < db))
	for goal in goals:
		var ids := grid.get_id_path(from,goal)
		if ids.is_empty(): continue
		var path := PackedVector3Array()
		var prior := start
		var valid := true
		for cell in ids:
			var p := point(cell)
			if not segment_clear(prior,p): valid = false; break
			path.append(p); prior = p
		if valid: return path
	return PackedVector3Array()

func report(start: Vector3, targets: Dictionary) -> Dictionary:
	var unreachable := []
	var checked := []
	var ids: Array = targets.keys(); ids.sort()
	for id in ids:
		var raw = targets[id]
		var target: Vector3 = raw.point if raw is Dictionary else raw
		var reach := float(raw.get("reach",1.0)) if raw is Dictionary else 1.0
		var edge := bool(raw.get("edge",true)) if raw is Dictionary else true
		var path := route(start,target,reach,edge)
		if path.is_empty(): unreachable.append(str(id))
		checked.append({"id":str(id),"reachable":not path.is_empty(),"path_points":path.size(),"reach":reach,"edge":edge})
	return {"ok":not checked.is_empty() and unreachable.is_empty(),"targets":checked,"unreachable":unreachable,"free_cells":free_cells.size(),"cell_m":CELL}
