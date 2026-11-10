extends SceneTree
## MERGE2 performance-fix equivalence checks on a real prepared runtime (real kits/characters):
## cached character instances are structurally identical to freshly parsed ones and never share
## materials; stored-length triangle counts equal the GPU-readback reference in every room.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var checks := 0

func expect(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)
		print("FAIL ", label)

func _initialize() -> void:
	call_deferred("run")

func census(n: Node, out: Dictionary) -> void:
	var key := n.get_class()
	out[key] = int(out.get(key, 0)) + 1
	for c in n.get_children(): census(c, out)

func describe(actor) -> Dictionary:
	var d := {"census":{}}
	census(actor, d.census)
	d["bones"] = actor.skeleton.get_bone_count() if actor.skeleton != null else -1
	d["clips"] = Array(actor.animation.get_animation_list()) if actor.animation != null else []
	var clip_modes := []
	if actor.animation != null:
		for clip in actor.animation.get_animation_list():
			var a: Animation = actor.animation.get_animation(clip)
			var interp := []
			for i in a.get_track_count(): interp.append(a.track_get_interpolation_type(i))
			clip_modes.append([clip, a.loop_mode, a.length, interp])
	d["clip_modes"] = clip_modes
	d["materials"] = actor.materials.size()
	d["faces"] = actor.faces.size()
	d["kinds"] = actor.materials.map(func(m): return str(m.get_meta("kind", "")))
	var meshes := []
	for mi in actor.find_children("*", "MeshInstance3D", true, false):
		meshes.append([str(mi.name), mi.mesh.get_surface_count() if mi.mesh != null else 0])
	d["meshes"] = meshes
	return d

## Parallel deep walk: every property the simulation or presentation can observe
## (transforms, visibility, AABBs, skeleton poses, animation player state, owners).
func deep(n: Node, out: Array, path := "") -> void:
	var row := [path, n.get_class()]
	if n is Node3D:
		row.append_array([n.transform, n.visible])
	if n is VisualInstance3D:
		row.append(n.get_aabb())
	if n is MeshInstance3D:
		row.append_array([n.mesh.get_aabb() if n.mesh != null else null, n.mesh.get_surface_count() if n.mesh != null else 0, n.skeleton, n.skin != null, n.get_surface_override_material_count()])
	if n is Skeleton3D:
		var bones := []
		for b in n.get_bone_count(): bones.append([n.get_bone_name(b), n.get_bone_rest(b), n.get_bone_pose(b)])
		row.append(bones)
	if n is AnimationPlayer:
		row.append_array([n.current_animation, n.assigned_animation, n.autoplay, n.is_playing(), n.callback_mode_process, n.root_node, n.active, n.speed_scale])
	row.append(n.owner != null)
	out.append(var_to_str(row))
	for c in n.get_children(): deep(c, out, path + "/" + str(c.name))

func compare_deep(label: String, a: Node, b: Node) -> void:
	var da := []
	var db := []
	deep(a, da)
	deep(b, db)
	var diffs := []
	for i in mini(da.size(), db.size()):
		if da[i] != db[i] and diffs.size() < 4:
			diffs.append("\n    fresh=%s\n    cache=%s" % [da[i], db[i]])
	if da.size() != db.size(): diffs.append(" node counts %d vs %d" % [da.size(), db.size()])
	expect(diffs.is_empty(), "deep identical " + label + "".join(diffs))

func run() -> void:
	var view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), {"pack":"res://theme.json", "bindings":"res://bindings.json", "save":"user://merge2-assets.json", "test":true})
	expect(booted.ok, "boot")
	if not booted.ok:
		await view.quit_cleanly(1)
		return
	var rt = view.runtime
	var tested := 0
	# Every bound character row (the frozen manifest set), not only this story's cast.
	var subjects := []
	for row in view.resolver.characters:
		subjects.append({"id":str(row.get("character_id", "")), "body_id":row.get("body_id", ""), "base_rig_id":row.get("base_rig_id", ""), "params":row.get("params", {})})
	for c in subjects:
		var cid: String = c.id
		view.resolver.character_cache.clear() # a = fresh glTF parse, b = cached instance
		var a = view.resolver.character(c)
		if a == null: continue
		if not a.get_meta("real_character", false):
			a.free()
			continue
		var b = view.resolver.character(c)
		expect(b != null and b.get_meta("real_character", false), "cached instance is a real character: " + str(cid))
		if b != null:
			expect(JSON.stringify(describe(a)) == JSON.stringify(describe(b)), "cached instance structure identical: " + str(cid))
			compare_deep(cid + " (detached)", a, b)
			view.world.add_child(a)
			view.world.add_child(b)
			compare_deep(cid + " (in tree)", a, b)
			var wa: AABB = preload("res://view/room.gd").world_aabb(a)
			var wb: AABB = preload("res://view/room.gd").world_aabb(b)
			expect(wa.is_equal_approx(wb) and wa == wb, "world_aabb identical %s: %s vs %s" % [cid, wa, wb])
			view.world.remove_child(a)
			view.world.remove_child(b)
			var shared := false
			for m in a.materials:
				if b.materials.has(m): shared = true
			expect(not shared, "instances never share ShaderMaterials: " + str(cid))
			if not a.faces.is_empty() and int(a.faces[0].cols) * int(a.faces[0].rows) >= 2:
				a.expression(1)
				b.expression(0)
				expect(a.faces[0].material.get_shader_parameter("uv_offset") != b.faces[0].material.get_shader_parameter("uv_offset"), "expressions stay per actor: " + str(cid))
			b.free()
		a.free()
		tested += 1
	expect(tested > 0, "at least one real character exercised")
	for room in rt.game.rooms:
		rt.state.location = room.id
		view.enter_room("")
		var fast: int = view.room_root.triangle_count() + view.room_root.triangle_count(view.player)
		var slow: int = view.room_root.triangle_count_readback() + view.room_root.triangle_count_readback(view.player)
		expect(fast == slow and fast > 0, "triangle count equal in %s (%d vs %d)" % [room.id, fast, slow])
	print("MERGE2_ASSETS characters=%d checks=%d failures=%d" % [tested, checks, failures.size()])
	await view.quit_cleanly(0 if failures.is_empty() else 1)
