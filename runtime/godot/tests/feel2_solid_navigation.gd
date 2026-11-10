extends SceneTree
const Room = preload("res://view/room.gd")
const Player = preload("res://view/player.gd")
const Solids = preload("res://view/solid_footprints.gd")
var failures := []
var checks := 0
func check(ok: bool,label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	check(FileAccess.file_exists("res://view/solid_navigation.gd"),"production geometry navigation API exists")
	if not FileAccess.file_exists("res://view/solid_navigation.gd"):
		print("FEEL2_NAVIGATION ",JSON.stringify({"checks":checks,"failures":failures})); quit(1); return
	var Nav = load("res://view/solid_navigation.gd")
	var wall: Dictionary = Solids.definition("divider","wall",Transform3D(Basis.IDENTITY,Vector3(6,0,6)),{"meta":{"bbox_size_m":[0.5,12,2]}})
	var nav = Nav.new()
	nav.configure([],Vector2(11,9),0.26,1.4,0.4)
	check(nav.point_clear(Vector3(5.5,0,8.6)),"authored south-door boundary is not rejected by float32/double roundoff")
	check(not nav.route(Vector3(5.5,0,6.3),Vector3(5.5,0,8.6),1.0,false).is_empty(),"Sun Hall south exit is reachable within the unchanged 0.4m margin")
	nav.configure([wall],Vector2(12,12),0.26,1.4,0.4)
	check(not nav.point_clear(Vector3(6,0,6)),"navigation uses solids instead of an obstacle-exempt grid")
	check(not nav.segment_clear(Vector3(4,0,6),Vector3(8,0,6)),"clear endpoints cannot hide a crossed-prop segment")
	check(nav.route(Vector3(2,0,6),Vector3(10,0,6),0.4).is_empty(),"known-bad partitioned room fails connectivity")
	var report: Dictionary = nav.report(Vector3(2,0,6),{"exit":Vector3(10,0,6)})
	check(not report.ok and report.unreachable.has("exit"),"known-bad unreachable exit is an explicit report failure")
	var box: Dictionary = Solids.definition("box","crate",Transform3D(Basis.IDENTITY,Vector3(6,0,6)),{"meta":{"bbox_size_m":[2,2,1]}})
	nav.configure([box],Vector2(12,12),0.26,1.4,0.4)
	var path: PackedVector3Array = nav.route(Vector3(3,0,6),Vector3(9,0,6),0.4)
	check(path.size()>2,"route genuinely detours around a solid prop")
	var prior := Vector3(3,0,6)
	var clean := true
	for p in path:
		clean = clean and nav.segment_clear(prior,p)
		prior = p
	check(clean,"every planned segment is capsule-clear; no corner cutting")
	check(nav.report(Vector3(3,0,6),{"table":Vector3(6,0,6)}).ok,"solid interaction target is reachable at an exposed edge")
	var nearest: Vector3 = nav.safe_spawn(Vector3(6,0.1,6))
	check(nearest != Vector3.INF and nav.point_clear(nearest),"overlapping spawn receives a deterministic nearby free point")
	check(nearest == nav.safe_spawn(Vector3(6,0.1,6)),"spawn tie-breaking is repeatable")
	var player = Player.new()
	root.add_child(player)
	player.set_physics_process(false)
	check(player.has_method("place_in_room"),"production player exposes room-entry placement contract")
	if player.has_method("place_in_room"):
		var room = Room.new()
		room.data = {"grid_size":[12,12]}
		room.solid_definitions = [box]
		player.position = Vector3(6,0.1,6)
		player.place_in_room(room)
		check(nav.point_clear(player.position),"room-entry placement fixes actual player simulation position")
		room.free()
	player.free()
	print("FEEL2_NAVIGATION ",JSON.stringify({"checks":checks,"failures":failures,"detour_points":path.size()}))
	await process_frame
	quit(0 if failures.is_empty() else 1)
