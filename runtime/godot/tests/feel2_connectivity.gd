extends SceneTree
## Room geometry audit on the ordinary shipped facade. Story conditions are NOT
## bypassed into a win: each room is enumerated as a geometry fixture, with every
## mandatory prompt/exit/module anchor checked against actual Room definitions.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Solids = preload("res://view/solid_footprints.gd")
const Nav = preload("res://view/solid_navigation.gd")
var view
var failures := []
var rooms := []
var controls := []
var out := ""
var puzzle_sidecar := {}

func _initialize() -> void: call_deferred("run")
func arg(name: String) -> String:
	for a in OS.get_cmdline_user_args():
		if str(a).begins_with(name+"="): return str(a).trim_prefix(name+"=")
	return ""
func vec(a: Array) -> Vector3: return Vector3(float(a[0]),float(a[1]),float(a[2]))
func coordinates(p: Vector3) -> Array: return [p.x,p.y,p.z]

## Grid-owned animation writes the avatar directly. Check EVERY potentially
## usable grid cell/adjacent segment against native room solids so that controller
## cannot make a logical pass by crossing a newly placed furniture/terrain body.
func puzzle_clearance(room, nav) -> Dictionary:
	var puzzle := {}
	for p in puzzle_sidecar.get("puzzles",[]):
		if str(p.room) == str(room.data.id): puzzle = p
	if puzzle.is_empty(): return {}
	var positions := {}
	var blocked := []
	for z in puzzle.layout.size():
		var line := str(puzzle.layout[z])
		for x in line.length():
			if line[x] == "#": continue
			var cell := Vector2i(x,z)
			var at := Vector3(x+0.5,0.02,z+0.5)
			positions[cell] = at
			if not nav.point_clear(at): blocked.append("cell:%d,%d" % [x,z])
	var segments := 0
	for cell in positions:
		for direction in [Vector2i(1,0),Vector2i(0,1)]:
			if not positions.has(cell+direction): continue
			segments += 1
			if not nav.segment_clear(positions[cell],positions[cell+direction]): blocked.append("segment:"+str(cell)+":"+str(direction))
	return {"ok":not positions.is_empty() and blocked.is_empty(),"puzzle":str(puzzle.id),"cells_checked":positions.size(),"segments_checked":segments,"elements":puzzle.elements.map(func(e): return str(e.id)),"exits":room.data.doors.map(func(d): return str(d.id)),"blocked":blocked}

func required_targets(room) -> Dictionary:
	var targets := {}
	var anchors: Dictionary = room.target_anchors
	for door in room.data.doors:
		var id := "move:"+str(room.data.id)+":"+str(door.id)
		if anchors.has(id): targets[id] = {"point":anchors[id],"reach":1.0,"edge":false}
		else: failures.append("missing exit anchor "+id)
	for action in view.runtime.game.interactions:
		if action.room != room.data.id: continue
		var id := "interact:"+str(action.id)
		var point = anchors.get(id,anchors.get(str(action.target),null))
		if point == null: failures.append("missing required target "+id)
		else: targets[id] = {"point":point,"reach":2.2,"edge":true}
	for c in view.runtime.game.get("collectibles",[]):
		if c.room != room.data.id or view.runtime.state.collected.has(c.id): continue
		var id := "collect:"+str(c.id)
		if not anchors.has(id): failures.append("missing collectible "+id)
		else: targets[id] = {"point":anchors[id],"reach":2.2,"edge":true}
	for id in room.data.character_ids:
		if id == view.runtime.game.metadata.get("protagonist","") or not anchors.has(id): continue
		targets["npc:"+str(id)] = {"point":anchors[id],"reach":2.2,"edge":true}
	if view.runtime.modules == null: return targets
	for cp in view.runtime.modules.checkpoints.values():
		if cp.room == room.data.id: targets["checkpoint:"+str(cp.id)] = {"point":vec(cp.position_m),"reach":0.45,"edge":false}
	for challenge in view.runtime.modules.challenges.values():
		if challenge.room != room.data.id: continue
		var at := Vector3.ZERO
		if challenge.kind == "course":
			at = vec(view.runtime.modules.entities("course","tracks")[challenge.subject].start_position_m)
		else:
			var arena: Dictionary = view.runtime.modules.entities("combat","encounters")[challenge.subject].arena
			at = Vector3((arena.min[0]+arena.max[0])*0.5,0,arena.min[2]+1.0)
		targets["challenge:start:"+str(challenge.id)] = {"point":at,"reach":0.9,"edge":false}
	for track in view.runtime.modules.entities("course","tracks").values():
		if track.room != room.data.id: continue
		targets["course:"+str(track.id)+":start"] = {"point":vec(track.start_position_m),"reach":0.4,"edge":false}
		for cp in track.checkpoints: targets["course:"+str(track.id)+":"+str(cp.id)] = {"point":vec(cp.position_m),"reach":float(cp.radius_m)*0.8,"edge":false}
	return targets

func negative_controls() -> void:
	var divider := Solids.definition("bad_divider","blocked-control",Transform3D(Basis.IDENTITY,Vector3(6,0,6)),{"meta":{"bbox_size_m":[0.5,12,2]}})
	var body := Solids.body_for(divider)
	view.world.add_child(body)
	var nav = Nav.new()
	nav.configure([divider],Vector2(12,12))
	var blocked: Dictionary = nav.report(Vector3(2,0.001,6),{"blocked_exit":{"point":Vector3(10,0.001,6),"edge":false,"reach":0.5}})
	var high: Dictionary = nav.report(Vector3(2,0.001,6),{"high_checkpoint":{"point":Vector3(2,8,6),"edge":false,"reach":0.4}})
	controls.append({"id":"full_room_partition","detected":not blocked.ok,"report":blocked})
	controls.append({"id":"high_required_checkpoint","detected":not high.ok,"report":high})
	body.free()
	for c in controls:
		if not c.detected: failures.append("known-bad control was accepted: "+str(c.id))

func run() -> void:
	out = arg("--output")
	view = View.new(); root.add_child(view)
	var game: Dictionary = Wire.read_json("res://game.json")
	var booted: Dictionary = view.boot(game,{"pack":"res://theme.json","bindings":"res://bindings.json","save":"user://feel2-solids-connectivity.json","test":true})
	if not booted.ok: failures.append("ordinary facade boot failed "+str(booted)); await finish(); return
	view.player.simulation_enabled = false
	view.actions.set_source("bot")
	view.set_physics_process(false)
	if FileAccess.file_exists("res://puzzle.json"): puzzle_sidecar = Wire.read_json("res://puzzle.json")
	var ids: Array = view.runtime.rooms.keys(); ids.sort()
	for phase in ["resident","collected"]:
		view.runtime.state.collected = [] if phase == "resident" else view.runtime.collections.keys()
		for id in ids:
			view.runtime.state.location = id
			view.enter_room("")
			view.player.simulation_enabled = false
			var room = view.room_root
			var raw: Vector3 = view.player.position
			var placed: Dictionary = view.player.place_in_room(room)
			if not placed.ok: failures.append(str(id)+":"+phase+" has no safe spawn")
			var nav = view.player.room_navigation
			var targets := required_targets(room)
			var report: Dictionary = nav.report(view.player.position,targets)
			var puzzle_report := puzzle_clearance(room,nav)
			if not puzzle_report.is_empty():
				if not puzzle_report.ok: failures.append(str(id)+":"+phase+" native solid blocks puzzle-owned movement "+str(puzzle_report.blocked))
				if phase == "resident":
					var bad: Array = room.solid_definitions.duplicate(true)
					var cell: Vector3 = Vector3.ZERO
					for p in puzzle_sidecar.puzzles:
						if p.room == id: cell = Vector3(p.start[0]+0.5,0,p.start[1]+0.5)
					bad.append(Solids.definition("bad_grid_blocker","blocked-puzzle-control",Transform3D(Basis.IDENTITY,cell),{"meta":{"bbox_size_m":[0.8,0.8,2]}}))
					var bad_nav = Nav.new(); bad_nav.configure(bad,nav.bounds)
					var rejected := puzzle_clearance(room,bad_nav)
					controls.append({"id":"native_puzzle_cell_blocked:"+str(id),"detected":not rejected.ok,"blocked":rejected.blocked})
			var arrivals := []
			var centre := Vector3(room.data.grid_size[0]/2.0,0.1,room.data.grid_size[1]/2.0)
			for door in room.data.doors:
				var action := "move:"+str(id)+":"+str(door.id)
				var desired: Vector3 = room.target_anchors[action]
				desired = Vector3(desired.x,0.1,desired.z).lerp(centre,0.17)
				var safe: Vector3 = nav.safe_spawn(desired)
				var linked: bool = safe != Vector3.INF and not nav.route(view.player.position,safe,0.3,false).is_empty()
				arrivals.append({"door":str(door.id),"desired":coordinates(desired),"safe":coordinates(safe) if safe != Vector3.INF else [],"linked":linked})
				if not linked: failures.append(str(id)+":"+phase+" unsafe/disconnected arrival "+str(door.id))
			for cp in view.runtime.modules.checkpoints.values() if view.runtime.modules != null else []:
				if cp.room != id: continue
				var desired := vec(cp.position_m)+Vector3.UP*0.02
				var safe: Vector3 = nav.safe_spawn(desired)
				var linked: bool = safe != Vector3.INF and not nav.route(view.player.position,safe,0.3,false).is_empty()
				arrivals.append({"checkpoint":str(cp.id),"desired":coordinates(desired),"safe":coordinates(safe) if safe != Vector3.INF else [],"linked":linked})
				if not linked: failures.append(str(id)+":"+phase+" unsafe/disconnected checkpoint "+str(cp.id))
			if not report.ok: failures.append(str(id)+":"+phase+" unreachable "+str(report.unreachable))
			var sources := {}
			for definition in room.solid_definitions: sources[definition.source] = int(sources.get(definition.source,0))+1
			rooms.append({"room":str(id),"phase":phase,"solids":room.solid_definitions.size(),"sources":sources,"raw_spawn":coordinates(raw),"spawn":coordinates(view.player.position),"adjusted":placed.get("adjusted",false),"arrivals":arrivals,"report":report,"puzzle_clearance":puzzle_report})
			print("ROOM_CONNECTIVITY ",id," ",phase," solids=",room.solid_definitions.size()," targets=",targets.size()," unreachable=",report.unreachable)
			await process_frame
	negative_controls()
	await finish()

func finish() -> void:
	var result := {"ok":failures.is_empty() and not rooms.is_empty(),"game":view.runtime.game.id if view.runtime != null else "","rooms":rooms,"controls":controls,"failures":failures,"scope":"production room geometry; resident and collected states; all required interaction/collectible/NPC/exit/module/course anchors plus reciprocal entry and checkpoint connectivity; not a story-completion or human-feel verdict"}
	if out != "":
		var file := FileAccess.open(out,FileAccess.WRITE)
		file.store_string(JSON.stringify(result,"  ",true)); file.close()
	print("FEEL2_CONNECTIVITY ",JSON.stringify({"ok":result.ok,"room_states":rooms.size(),"failures":failures}))
	await view.quit_cleanly(0 if result.ok else 1)
