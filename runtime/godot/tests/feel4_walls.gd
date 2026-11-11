extends SceneTree
## FEEL4 physical wall probe. For every room of the staged game, walk the player (Actions.submit_frame only; no
## position writes while walking) into every wall/edge at 5 points per side and into every corner, and measure the
## capsule against the VISIBLE room structure: the triangles of the placed shell/wall/yard meshes (light/glow cards
## "kit_card_*" excluded), copied into a ray-only helper shape on its own layer (the player never collides with it).
## The structure is measured from rendered geometry, independently of the runtime boundary data, so the same script
## measures a build without the fix (known-bad) and a fixed build with --control=grid_rect (known-bad control).
## Per walk, every tick:
##   crossed      the capsule centre's path segment (3 body heights) crossed a wall triangle   -> fail
##   overlap_m    capsule radius minus the nearest wall distance (16 rays x 3 heights)        -> fail above 3 cm
##   off_floor    no visible floor under the capsule centre (roof edge, street end)           -> fail
##   out_of_grid  centre outside the room grid                                                -> fail
##   cam_behind   follow camera behind a wall (interiors; reported, not a gate)
##   --output=<json>   --control=grid_rect
## Also runs inside an exported build (the shipped binary with its .pck, script passed by absolute path): the harness
## wrapper res://playtest/view.gd is not exported, so ShippedView repeats it (main.gd without its command-line boot).
const VIEW_PATH := "res://playtest/view.gd"
const Wire = preload("res://core/wire.gd")
class ShippedView extends "res://actors/main.gd":
	func _ready() -> void:
		pass
const TOLERANCE := 0.03
const HEIGHTS := [0.3, 0.75, 1.05]
const STRUCT := ["shell", "wall", "yard"]
const FLOOR := ["shell", "wall", "yard", "floor"]
const SAMPLES := [0.12, 0.3, 0.5, 0.7, 0.88]
const WALK_TICKS := 150
const PROBE_LAYER := 1 << 19
var view
var output := ""
var control := ""
var failures := []
var rooms := []
var probes := 0
var floor_tris := PackedVector3Array()
var helper: StaticBody3D

func _initialize() -> void: call_deferred("run")

func tris_for(kinds: Array, walls_only: bool) -> PackedVector3Array:
	var out := PackedVector3Array()
	for n in view.room_root.get_children():
		if not str(n.get_meta("placed", "")) in kinds: continue
		var stack: Array = [n]
		while not stack.is_empty():
			var m = stack.pop_back()
			if m is MeshInstance3D and m.mesh != null and m.is_visible_in_tree() and not (walls_only and str(m.name).begins_with("kit_card")):
				var xf: Transform3D = m.global_transform
				var faces: PackedVector3Array = m.mesh.get_faces()
				for i in range(0, faces.size(), 3):
					var a: Vector3 = xf * faces[i]; var b: Vector3 = xf * faces[i + 1]; var c: Vector3 = xf * faces[i + 2]
					if walls_only and absf((b - a).cross(c - a).normalized().y) > 0.7: continue   # floors/ceilings: not walls
					out.append(a); out.append(b); out.append(c)
			for c in m.get_children(): stack.append(c)
	return out

func build_helper(tris: PackedVector3Array) -> void:
	if helper != null: helper.free()
	helper = StaticBody3D.new()
	helper.collision_layer = PROBE_LAYER
	helper.collision_mask = 0
	var shape := ConcavePolygonShape3D.new()
	shape.backface_collision = true
	shape.set_faces(tris)
	var cs := CollisionShape3D.new(); cs.shape = shape
	helper.add_child(cs)
	view.room_root.add_child(helper)

func hit(from: Vector3, to: Vector3) -> float:
	if from.distance_to(to) < 0.0001: return INF
	var q := PhysicsRayQueryParameters3D.create(from, to, PROBE_LAYER)
	q.hit_back_faces = true
	var r: Dictionary = view.world.get_world_3d().direct_space_state.intersect_ray(q)
	return INF if r.is_empty() else from.distance_to(r.position)

func on_floor(p: Vector3) -> bool:
	var from := Vector3(p.x, 0.45, p.z)
	for i in range(0, floor_tris.size(), 3):
		if Geometry3D.ray_intersects_triangle(from, Vector3.DOWN, floor_tris[i], floor_tris[i + 1], floor_tris[i + 2]) != null: return true
	return false

func nearest_wall(p: Vector3, reach: float) -> float:
	var best := INF
	for h in HEIGHTS:
		var c := Vector3(p.x, h, p.z)
		for k in 16:
			var a := TAU * k / 16.0
			best = minf(best, hit(c, c + Vector3(cos(a), 0, sin(a)) * reach))
	return best

func keys_toward(world_dir: Vector2) -> Array:
	var basis: Basis = view.player.camera_basis
	var right := Vector2(basis.x.x, basis.x.z).normalized()
	var back := Vector2(basis.z.x, basis.z.z).normalized()
	var best := Vector2.ZERO
	var score := -INF
	for x in [-1, 0, 1]:
		for y in [-1, 0, 1]:
			if x == 0 and y == 0: continue
			var d: Vector2 = (right * x + back * y).normalized()
			if d.dot(world_dir) > score: score = d.dot(world_dir); best = Vector2(x, y)
	var out := ["run"]
	if best.x < 0: out.append("move_left")
	if best.x > 0: out.append("move_right")
	if best.y < 0: out.append("move_up")
	if best.y > 0: out.append("move_down")
	return out

func frame(digital: Array) -> void:
	view.actions.submit_frame({"digital": digital})
	await physics_frame
	await process_frame

func force_control(w: float, d: float) -> void:
	if control != "grid_rect": return
	view.room_root.boundary_outline = PackedVector2Array([Vector2(0, 0), Vector2(w, 0), Vector2(w, d), Vector2(0, d)])

## Place at the first clear start (stepping back from the wall, then sideways) and walk toward dir.
func walk(id: String, start: Vector2, dir: Vector2, w: float, d: float, interior: bool) -> Dictionary:
	var radius: float = float(view.player.tuning.capsule_radius_m)
	var side := Vector2(-dir.y, dir.x)
	var p0 := Vector2.INF
	var why := []
	for offset in [Vector2.ZERO, -dir * 0.6, -dir * 1.2, -dir * 1.8, side * 0.6, -side * 0.6, -dir * 1.2 + side * 0.6, -dir * 1.2 - side * 0.6]:
		var s: Vector2 = start + offset
		view.player.position = Vector3(s.x, 0.1, s.y)
		view.player.velocity = Vector3.ZERO
		force_control(w, d)
		var placed: Dictionary = view.player.place_in_room(view.room_root)
		if not placed.get("ok", false): why.append("%s:no_spawn" % str(s)); continue
		var at := Vector2(view.player.position.x, view.player.position.z)
		var near_wall := nearest_wall(view.player.position, radius + 0.1)
		if at.distance_to(s) <= 0.3 and near_wall > radius: p0 = at; break
		why.append("%s:moved=%.2f,wall=%.2f" % [str(s), at.distance_to(s), near_wall])
	if p0 == Vector2.INF: return {"skipped": "no clear start near the probe line", "why": why.slice(0, 3)}
	for k in 4: await frame([])
	var held := keys_toward(dir)
	var crossed := 0
	var worst_overlap := -INF
	var off_floor := 0
	var out_grid := 0
	var cam_behind := 0
	var deepest := p0
	var prev: Vector3 = view.player.position
	var travelled := 0.0
	for t in WALK_TICKS:
		await frame(held)
		if view.runtime.state.location != id: break
		var now: Vector3 = view.player.position
		travelled += Vector2(now.x - prev.x, now.z - prev.z).length()
		for h in HEIGHTS:
			if hit(Vector3(prev.x, h, prev.z), Vector3(now.x, h, now.z)) < INF: crossed += 1; break
		var overlap := radius - nearest_wall(now, radius + 0.2)
		if overlap > worst_overlap: worst_overlap = overlap; deepest = Vector2(now.x, now.z)
		if not on_floor(now): off_floor += 1
		if now.x < 0.0 or now.z < 0.0 or now.x > w or now.z > d: out_grid += 1
		if interior and view.follow_camera != null and view.follow_camera.render_camera != null:
			var head := now + Vector3.UP * 1.2
			var eye: Vector3 = view.follow_camera.render_camera.global_position
			if hit(head, eye) < INF: cam_behind += 1
		prev = now
	for k in 4: await frame([])
	return {"start": [snappedf(p0.x, 0.01), snappedf(p0.y, 0.01)], "deepest": [snappedf(deepest.x, 0.001), snappedf(deepest.y, 0.001)],
		"travelled_m": snappedf(travelled, 0.01), "crossed_ticks": crossed, "overlap_m": snappedf(worst_overlap, 0.001),
		"off_floor_ticks": off_floor, "out_of_grid_ticks": out_grid, "camera_behind_wall_ticks": cam_behind}

## A probe line must reach the wall: shift it along the side (0.5 m steps, up to 3 m) until the lane from the start to
## the grid edge is free of non-structure solids (props). Structure solids ("kit:" ids: a hut, facades) stay in the
## lane on purpose: walking into them is a wall test.
func lane_start(start: Vector2, dir: Vector2, half: float) -> Variant:
	const Solids = preload("res://view/solid_footprints.gd")
	var radius: float = float(view.player.tuning.capsule_radius_m)
	var side := Vector2(-dir.y, dir.x)
	for k in 13:
		var shift: float = 0.5 * ceil(k / 2.0) * (1.0 if k % 2 == 1 else -1.0)
		var s: Vector2 = start + side * shift
		# Inside the room, measured from geometry only: on the visible floor and reachable from the room centre
		# without crossing a wall surface (independent of the runtime boundary data under test).
		var centre := Vector3(view.runtime.rooms[view.runtime.state.location].grid_size[0] / 2.0, 0.75, view.runtime.rooms[view.runtime.state.location].grid_size[1] / 2.0)
		var clear := on_floor(Vector3(s.x, 0.0, s.y)) and hit(centre, Vector3(s.x, 0.75, s.y)) == INF
		clear = clear and nearest_wall(Vector3(s.x, 0.0, s.y), radius + 0.1) > radius + 0.05
		for row in view.room_root.solid_definitions:
			if clear and Solids.contains_point(row, Vector3(s.x, 0.1, s.y), radius + 0.05): clear = false
		var t := 0.0
		while clear and t <= 2.4 + 0.6:
			var p: Vector2 = s + dir * t
			for row in view.room_root.solid_definitions:
				if str(row.id).begins_with("kit:"): continue
				var box: AABB = row.transform * row.box
				if box.end.y <= 0.05 or box.position.y >= 1.4: continue
				if Solids.contains_point(row, Vector3(p.x, 0.1, p.y), radius + 0.05): clear = false; break
			t += 0.1
		if clear: return s
	return null

func judge(row: Dictionary, probe: Dictionary, res: Dictionary) -> void:
	probe.merge(res)
	probes += 1
	if res.has("skipped"):
		if str(res.skipped).begins_with("props cover"): row.prop_covered += 1   # the wall is unreachable there
		else: row.skipped += 1
		row.probes.append(probe); return
	row.worst_overlap_m = maxf(row.worst_overlap_m, float(res.overlap_m))
	if res.crossed_ticks > 0: row.crossed += 1; probe["fail"] = "crossed a wall"
	elif float(res.overlap_m) > TOLERANCE: row.overlapped += 1; probe["fail"] = "capsule inside a wall"
	if res.off_floor_ticks > 0 or res.out_of_grid_ticks > 0: row.edge_failures += 1; probe["fail"] = "left the floor/room"
	row.camera_behind_wall_ticks += int(res.camera_behind_wall_ticks)
	row.probes.append(probe)

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		if str(arg).begins_with("--output="): output = str(arg).trim_prefix("--output=")
		if str(arg).begins_with("--control="): control = str(arg).trim_prefix("--control=")
	var view_script = load(VIEW_PATH) if ResourceLoader.exists(VIEW_PATH) else ShippedView
	view = view_script.new(); root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true, "scenes": "off", "save": "user://feel4-walls.json"})
	if not booted.ok: failures.append("boot failed " + str(booted)); await finish(); return
	view.actions.configure({"version": 1}); view.actions.set_source("bot")
	var ids: Array = view.runtime.rooms.keys(); ids.sort()
	for id in ids:
		view.runtime.state.location = id
		view.enter_room("")
		for k in 3: await frame([])
		var room: Dictionary = view.runtime.rooms[id]
		var w: float = room.grid_size[0]; var d: float = room.grid_size[1]
		var interior := not bool(view.room_root.presentation.get("exterior", false))
		var walls := tris_for(STRUCT, true)
		floor_tris = tris_for(FLOOR, false)
		build_helper(walls)
		await physics_frame
		var row := {"room": id, "grid": [w, d], "exterior": not interior, "boundary_source": str(view.room_root.get("boundary_source")),
			"wall_triangles": walls.size() / 3, "probes": [], "worst_overlap_m": -INF, "crossed": 0, "overlapped": 0, "edge_failures": 0, "skipped": 0, "prop_covered": 0, "camera_behind_wall_ticks": 0}
		var c := Vector2(w / 2.0, d / 2.0)
		var sides := {"north": Vector2(0, -1), "south": Vector2(0, 1), "west": Vector2(-1, 0), "east": Vector2(1, 0)}
		for side in sides:
			var dir: Vector2 = sides[side]
			for s in SAMPLES:
				var line := Vector2(s * w, c.y) if dir.x == 0 else Vector2(c.x, s * d)
				var half: float = c.y if dir.x == 0 else c.x
				var lane = lane_start(line + dir * (half - 2.4), dir, half)
				if lane == null: judge(row, {"side": side, "at": s}, {"skipped": "props cover every lane within 3 m"}); continue
				judge(row, {"side": side, "at": s, "lane": [snappedf(lane.x, 0.01), snappedf(lane.y, 0.01)]}, await walk(id, lane, dir, w, d, interior))
		for corner in [[Vector2(0, 0), "north_west"], [Vector2(w, 0), "north_east"], [Vector2(0, d), "south_west"], [Vector2(w, d), "south_east"]]:
			var target: Vector2 = corner[0]
			judge(row, {"side": corner[1], "at": "corner"}, await walk(id, target.lerp(c, 0.6), (target - c).normalized(), w, d, interior))
		if row.worst_overlap_m == -INF: row.worst_overlap_m = null
		rooms.append(row)
		print("FEEL4_WALL_ROOM %s source=%s probes=%d crossed=%d overlapped=%d edge=%d skipped=%d prop_covered=%d worst_overlap=%s cam_behind=%d" % [id, row.boundary_source, row.probes.size(), row.crossed, row.overlapped, row.edge_failures, row.skipped, row.prop_covered, str(row.worst_overlap_m), row.camera_behind_wall_ticks])
		for key in ["crossed", "overlapped", "edge_failures"]:
			if row[key] > 0: failures.append("%s: %d probes %s" % [id, row[key], {"crossed": "crossed a wall", "overlapped": "pushed the capsule > 3 cm into a wall", "edge_failures": "left the floor or the room grid"}[key]])
		if row.skipped > 0: failures.append("%s: %d probes found no clear start" % [id, row.skipped])
	await finish()

func finish() -> void:
	var result := {"ok": failures.is_empty() and probes > 0, "control": control, "probes": probes, "tolerance_m": TOLERANCE,
		"game": view.runtime.game.id if view.runtime != null else "", "rooms": rooms, "failures": failures,
		"scope": "bot walks into 5 points of every side and every corner of every room via submit_frame; walls = rendered shell/wall/yard triangles minus kit_card glow cards and near-horizontal faces; not a human-feel verdict"}
	if output != "":
		var f := FileAccess.open(output, FileAccess.WRITE); f.store_string(JSON.stringify(result, "  ", true)); f.close()
	print("FEEL4_WALLS ", JSON.stringify({"ok": result.ok, "probes": probes, "failures": failures}))
	await view.quit_cleanly(0 if result.ok else 3)
