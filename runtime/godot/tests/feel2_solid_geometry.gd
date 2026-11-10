extends SceneTree
const Solids = preload("res://view/solid_footprints.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var checks := 0

func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok: failures.append(label); printerr("FAIL ",label)

func _initialize() -> void:
	var row: Dictionary = Solids.definition("desk","furn.table",Transform3D.IDENTITY,{"meta":{"bbox_size_m":[2,4,1]}})
	check(row.box.size.is_equal_approx(Vector3(2,1,4)),"kit bbox metadata converts Blender x/y/z into glTF x/y/z")
	row = Solids.definition("socket","dgn.pillar",Transform3D.IDENTITY,{"meta":{"sockets":[{"footprint_m":1.2,"pos_gltf":[0.5,0,0]}],"bbox_size_m":[4,4,2]}})
	check(is_equal_approx(row.box.size.x,1.2) and is_equal_approx(row.box.get_center().x,0.5),"socket footprint takes precedence over conservative bbox")
	row = Solids.definition("actual_socket","dgn.pillar",Transform3D.IDENTITY,{"meta":{"sockets":[{"type":"pillar","footprint_m":1.15,"position":[1.5,0,-0.5],"facing":"up"}],"bbox_size_m":[4,4,2]}})
	check(row.box.get_center().distance_to(Vector3(1.5,1,-0.5))<0.001,"existing dungeon socket schema uses glTF position, not an invented field")
	row = Solids.definition("hollow","furn.pod",Transform3D.IDENTITY,{"meta":{"bbox_size_m":[4,4,1],"walkable_inner_radius_m":1.0}})
	check(not Solids.contains_point(row,Vector3.ZERO) and Solids.contains_point(row,Vector3(1.7,0,0)),"existing walkable inner footprint metadata preserves a hollow seat's clear centre and solid rim")
	row = Solids.definition("polygon","kit-shaped",Transform3D.IDENTITY,{"meta":{"bbox_size_m":[4,4,1],"footprint_gltf":[[-1,-0.2],[1,-0.2],[1,0.2],[-1,0.2]]}})
	check(not Solids.contains_point(row,Vector3(0.8,0,0.7)) and Solids.contains_point(row,Vector3(0.8,0,0.1)),"explicit footprint outline takes precedence over a much larger bbox")
	row = Solids.definition("multi","kit-supports",Transform3D.IDENTITY,{"meta":{"bbox_size_m":[6,6,2],"sockets":[{"footprint_m":0.6,"pos_gltf":[-2,0,0]},{"footprint_m":0.6,"pos_gltf":[2,0,0]}]}})
	check(Solids.contains_point(row,Vector3(-2,0,0)) and Solids.contains_point(row,Vector3(2,0,0)) and not Solids.contains_point(row,Vector3.ZERO),"every declared footprint socket is solid without filling the passage between supports")
	for ref in ["arch.door","nature.grass","soft.rug","arch.floor_module"]:
		check(Solids.definition("walk",ref,Transform3D.IDENTITY,{"kit_id":ref}).is_empty(),"explicit walkthrough policy: " + ref)
	check(Solids.definition("take","prop.key",Transform3D.IDENTITY,{"pickup":true}).is_empty(),"pickups are walkthrough even when their exported art includes a table")
	var game_bindings: Dictionary = Wire.read_json("res://bindings.json")
	var binding: Dictionary = game_bindings.assets["furn.table"]
	check(Solids.kit_metadata(binding).has("bbox_size_m"),"portable runtime carries the existing exact-SHA kit footprint metadata")
	row = Solids.definition("native_table","furn.table",Transform3D.IDENTITY,binding)
	check(row.source != "fallback" and row.box.size.distance_to(Vector3(0.9,0.72,0.9)) < 0.02,"real production binding uses kit metadata / immutable glTF bounds, not a magic prop size")
	var scaled := Transform3D(Basis(Vector3.UP,PI/2).scaled(Vector3(2,1,0.5)),Vector3(3,0,4))
	row = Solids.definition("scaled","crate",scaled,{"meta":{"bbox_size_m":[2,4,1]}})
	var body := Solids.body_for(row)
	check(body.transform.basis.get_scale().is_equal_approx(Vector3.ONE),"native mirror never nonuniform-scales a physics body")
	body.free()
	var below: Dictionary=Solids.definition("water","terrain.water",Transform3D(Basis.IDENTITY,Vector3(0,-0.2,0)),{"meta":{"bbox_size_m":[18,18,0.1]}})
	var npc: Dictionary=Solids.definition("npc","character:npc",Transform3D.IDENTITY,{"actor":true})
	var edge: Vector3=Solids.target_point([npc,below],Vector3.ZERO,Vector3(0,0.001,4))
	check(edge.distance_to(Vector3.ZERO)<0.8,"sub-floor water cannot move an NPC edge prompt outside the entire room")
	print("FEEL2_GEOMETRY ",JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
