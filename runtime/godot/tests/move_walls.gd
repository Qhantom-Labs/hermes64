extends SceneTree
## MOVE wall-probe bot. For every room of the staged game, walk (Actions.submit_frame,
## no position assignment while walking) into every segment of the room's AUTHORED
## floor outline (shell/yard kit walkable outline, else the grid rectangle) and
## assert the capsule never leaves the room. The outline is derived here, from
## bindings/game data, independently of the runtime, so the same script measures
## the cam-lane control (no boundary) and the MOVE build.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const TOLERANCE := 0.03
var view
var failures := []
var rooms := []
var output := ""
var exits := 0
var probes := 0
var max_excursion := 0.0

func _initialize() -> void: call_deferred("run")

func outline_for(room_id: String, w: float, d: float) -> Dictionary:
	var assets: Dictionary = Wire.read_json("res://bindings.json").get("assets",{})
	var pres: Dictionary = view.runtime.game.metadata.get("presentation",{}).get("rooms",{}).get(room_id,{})
	var row = null
	var source := "grid_rect"
	if not pres.get("exterior",false) and assets.has("shell/"+room_id): row = assets["shell/"+room_id]; source = "shell_outline"
	elif pres.get("exterior",false) and assets.has("yard/"+room_id): row = assets["yard/"+room_id]; source = "yard_outline"
	var rect := PackedVector2Array([Vector2(0,0),Vector2(w,0),Vector2(w,d),Vector2(0,d)])
	var raw := PackedVector2Array()
	if row is Dictionary:
		for p in row.get("meta",{}).get("walkable_outline_gltf",[]): raw.append(Vector2(w/2+float(p[0]),d/2+float(p[1])))
	if raw.size() < 3: return {"poly":rect,"source":"grid_rect"}
	var best := PackedVector2Array(); var best_area := 0.0
	for poly in Geometry2D.intersect_polygons(raw,rect):
		var a := 0.0
		for i in poly.size(): a += poly[i].cross(poly[(i+1)%poly.size()])
		if absf(a) > best_area: best_area = absf(a); best = poly
	if best.size() < 3: return {"poly":rect,"source":"grid_rect"}
	return {"poly":best,"source":source}

## Signed distance from p to the outline: positive inside.
func signed_distance(p: Vector2, poly: PackedVector2Array) -> float:
	var nearest := INF
	for i in poly.size():
		nearest = minf(nearest,p.distance_to(Geometry2D.get_closest_point_to_segment(p,poly[i],poly[(i+1)%poly.size()])))
	return nearest if Geometry2D.is_point_in_polygon(p,poly) else -nearest

func input_toward(direction: Vector2) -> Vector2:
	var basis: Basis = view.player.camera_basis
	var best := Vector2.ZERO; var score := -INF
	for x in [-1,0,1]:
		for y in [-1,0,1]:
			if x == 0 and y == 0: continue
			var world: Vector2 = (Vector2(basis.x.x,basis.x.z).normalized()*x + Vector2(basis.z.x,basis.z.z).normalized()*y).normalized()
			if world.dot(direction) > score: score = world.dot(direction); best = Vector2(x,y)
	return best

func frame(move: Vector2) -> void:
	var digital := []
	for pair in [["move_left",move.x<0],["move_right",move.x>0],["move_up",move.y<0],["move_down",move.y>0]]:
		if pair[1]: digital.append(pair[0])
	view.actions.submit_frame({"digital":digital})
	await physics_frame

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		if str(arg).begins_with("--output="): output = str(arg).trim_prefix("--output=")
	view = View.new(); root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true,"save":"user://move-walls.json"})
	if not booted.ok: failures.append("boot failed "+str(booted)); await finish(); return
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	if view.follow_camera != null: view.follow_camera.enabled = false
	var radius: float = float(view.player.tuning.capsule_radius_m)
	var ids: Array = view.runtime.rooms.keys(); ids.sort()
	for id in ids:
		view.runtime.state.location = id
		view.enter_room("")
		if view.module_host != null and view.module_host.puzzle != null and view.module_host.puzzle.active:
			rooms.append({"room":id,"skipped":"puzzle-owned grid movement (checked by connectivity puzzle_clearance)"}); continue
		var room: Dictionary = view.runtime.rooms[id]
		var w: float = room.grid_size[0]; var d: float = room.grid_size[1]
		var o := outline_for(id,w,d)
		var poly: PackedVector2Array = o.poly
		var row := {"room":id,"source":o.source,"segments":poly.size(),"probes":0,"exits":0,"worst":INF,"bad":[]}
		var centroid := Vector2.ZERO
		for p in poly: centroid += p
		centroid /= poly.size()
		for i in poly.size():
			var a: Vector2 = poly[i]; var b: Vector2 = poly[(i+1)%poly.size()]
			if a.distance_to(b) < 0.3: continue
			var mid := (a+b)*0.5
			var normal := Vector2((b-a).y,-(b-a).x).normalized()
			if Geometry2D.is_point_in_polygon(mid+normal*0.01,poly): normal = -normal
			# Start 1.4 m inside the wall midpoint (or toward the centroid if that is outside).
			var start := mid - normal*1.4
			if signed_distance(start,poly) < radius + 0.1: start = mid.lerp(centroid,0.5)
			view.player.position = Vector3(start.x,0.1,start.y)
			view.player.velocity = Vector3.ZERO
			var placed: Dictionary = view.player.place_in_room(view.room_root)
			if not placed.get("ok",false): row.bad.append({"segment":i,"reason":"no safe start"}); continue
			for k in 4: await frame(Vector2.ZERO)
			var key := input_toward(normal)
			var worst := INF
			for t in 150:
				await frame(key)
				if view.actions.context != "gameplay" or view.runtime.state.location != id: break
				var p := Vector2(view.player.position.x,view.player.position.z)
				worst = minf(worst,signed_distance(p,poly))
			for k in 6: await frame(Vector2.ZERO)
			probes += 1; row.probes += 1
			row.worst = minf(row.worst,worst)
			# "Never exits the room": the capsule body stays inside the authored outline.
			if worst < radius - TOLERANCE:
				exits += 1; row.exits += 1
				max_excursion = maxf(max_excursion,radius-worst)
				if row.bad.size() < 4: row.bad.append({"segment":i,"mid":[mid.x,mid.y],"worst_signed_m":worst})
			if view.runtime.state.location != id:
				view.runtime.state.location = id; view.enter_room("")
		rooms.append(row)
		print("MOVE_WALL_ROOM ",id," ",o.source," probes=",row.probes," exits=",row.exits," worst=",row.worst)
		if row.exits > 0: failures.append("%s: %d/%d wall probes left the room (worst %.3f m signed)" % [id,row.exits,row.probes,row.worst])
	await finish()

func finish() -> void:
	# Puzzle Hall rooms are entirely puzzle-owned grid movement ('#' layout walls):
	# recorded as skipped, not as passing probes.
	var all_skipped := not rooms.is_empty() and rooms.all(func(r): return r.has("skipped"))
	var result := {"ok":failures.is_empty() and (probes > 0 or all_skipped),"all_rooms_puzzle_owned":all_skipped,"game":view.runtime.game.id if view.runtime != null else "","probes":probes,"exits":exits,"max_excursion_m":max_excursion,"rooms":rooms,"failures":failures,"scope":"bot walks into every authored outline segment of every room via submit_frame; asserts capsule stays inside; not a story or human-feel verdict"}
	if output != "":
		var f := FileAccess.open(output,FileAccess.WRITE); f.store_string(JSON.stringify(result,"  ",true)); f.close()
	print("MOVE_WALLS ",JSON.stringify({"ok":result.ok,"probes":probes,"exits":exits,"failures":failures}))
	await view.quit_cleanly(0 if result.ok else 3)
