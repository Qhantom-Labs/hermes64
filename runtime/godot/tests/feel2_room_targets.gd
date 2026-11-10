extends SceneTree
const Room = preload("res://view/room.gd")
const Runtime = preload("res://core/runtime.gd")
const Resolver = preload("res://view/assets.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var checks := 0
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var runtime = Runtime.new()
	runtime.configure(Wire.read_json("res://game.json"))
	var resolver = Resolver.new()
	var theme: Dictionary = Wire.read_json("res://theme.json")
	resolver.configure(Wire.read_json("res://bindings.json"),theme)
	var room = Room.new()
	room.theme = theme
	room.build(runtime.rooms.pod_bay,runtime,resolver)
	root.add_child(room)
	var ids: Array = room.solid_definitions.map(func(row): return str(row.id))
	check(ids.has("actor:tavi"),"production NPC has a simulation body, not animated mesh collision")
	check(ids.has("prop:pod_cluster"),"production furniture has a footprint")
	check(not ids.has("prop:sphere_01") and not ids.has("prop:cat_button"),"collectible proxy art stays walkthrough; resident cat is its own actor")
	var npc_hit := false
	await physics_frame
	var at: Vector3 = room.target_positions.tavi
	var query := PhysicsRayQueryParameters3D.create(at+Vector3(-1,0.5,0),at+Vector3(1,0.5,0))
	npc_hit = not root.world_3d.direct_space_state.intersect_ray(query).is_empty()
	check(npc_hit,"real room NPC blocks native physics")
	check(room.has_method("update_interaction_targets"),"room exposes target-edge caller contract")
	if room.has_method("update_interaction_targets"):
		var from := at + Vector3(-1,0,0)
		room.update_interaction_targets(from)
		var edge: Vector3 = room.target_positions.tavi
		check(edge.distance_to(at)>0.15 and edge.distance_to(from)<at.distance_to(from),"NPC prompt moves to its exposed near edge")
		query = PhysicsRayQueryParameters3D.create(from+Vector3.UP*0.8,Vector3(edge.x,0.8,edge.z))
		check(root.world_3d.direct_space_state.intersect_ray(query).is_empty(),"target collider never occludes its own contextual ray")
	room.free()
	var snow = Room.new()
	snow.theme = theme
	snow.build(runtime.rooms.snow_field,runtime,resolver)
	root.add_child(snow)
	check(snow.solid_definitions.any(func(row): return row.ref == "nature.rock"),"large placed terrain is solid")
	check(not snow.solid_definitions.any(func(row): return row.ref == "prop/dome_card" or row.ref == "kit/heated_path"),"take targets and ground paths explicitly remain walkthrough")
	var before := JSON.stringify(snow.solid_definitions)
	for entry in snow.camera_nodes: entry.node.position += Vector3(10,4,-5)
	check(before == JSON.stringify(snow.solid_definitions),"renderer camera changes cannot mutate simulation geometry")
	snow.free()
	print("FEEL2_ROOM_TARGETS ",JSON.stringify({"checks":checks,"failures":failures}))
	await process_frame
	quit(0 if failures.is_empty() else 1)
