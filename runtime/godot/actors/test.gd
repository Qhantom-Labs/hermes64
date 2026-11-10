extends SceneTree
## Runs on the same copied runtime as the game; no editor import caches.
var failures := []
var checks := 0
func check(ok: bool, label: String) -> void:
	checks += 1
	if not ok:
		failures.append(label)
		print("CHARACTER FAIL ", label)
func _initialize() -> void:
	call_deferred("run")
func pose(s: Skeleton3D) -> Array:
	var result := []
	for i in s.get_bone_count(): result.append(s.get_bone_pose(i))
	return result
func run() -> void:
	var wire = load("res://core/wire.gd")
	var bindings: Dictionary = wire.read_json("res://bindings.json")
	var theme: Dictionary = wire.read_json("res://theme.json")
	check(ResourceLoader.exists("res://actors/assets.gd"), "actor resolver exists")
	if not failures.is_empty():
		quit(1)
		return
	var resolver = load("res://actors/assets.gd").new()
	resolver.configure(bindings, theme)
	var rows := []
	for row in bindings.characters:
		var c := {"id":row.authored_variant, "body_id":row.body_id,"base_rig_id":row.base_rig_id,"params":row.params}
		var actor = resolver.character(c)
		check(actor != null and actor.get_meta("real_character", false), row.character_id + " real actor")
		if actor == null: continue
		root.add_child(actor)
		check(actor.skeleton != null and actor.skeleton.get_bone_count() == 16, "16 bones")
		check(actor.animation != null, "AnimationPlayer")
		check(actor.has_node("shadow_blob"), "shadow blob")
		var shadow_arrays: Array = actor.get_node("shadow_blob").mesh.surface_get_arrays(0)
		check(shadow_arrays[Mesh.ARRAY_INDEX].size() / 3 <= 12, "blob budget <=12 tris")
		check(actor.pose_fps == 15, "15 fps held clock")
		check(actor.ground_offset >= -0.1 and actor.ground_offset <= 0.1, "sane grounding correction")
		var start: Vector3 = actor.position
		actor.play_clip("idle")
		actor.advance_pose(0.02)
		var first := pose(actor.skeleton)
		actor.advance_pose(0.02)
		check(first == pose(actor.skeleton), "held between ticks")
		actor.play_clip("walk")
		actor.advance_pose(0.2)
		var walking := pose(actor.skeleton)
		actor.advance_pose(0.4)
		check(walking != pose(actor.skeleton), "walk deforms over time")
		check(actor.position == start, "animation cannot move world root")
		check(is_equal_approx(actor.sample_time * 15.0, round(actor.sample_time * 15.0)), "quantized sample time")
		actor.face_velocity(Vector3(1,0,0))
		check((actor.basis * Vector3(0,0,1)).dot(Vector3.RIGHT) > 0.99, "glTF +Z faces velocity")
		if row.animations.has("talk"):
			actor.play_clip("talk")
			actor.advance_pose(0.2)
			check(actor.clip == "talk", "talk hookup")
		for m in actor.materials:
			check(m.shader.code.contains("filter_nearest") and not m.shader.code.contains("filter_linear_mipmap"), "nearest shader")
			check(m.get_shader_parameter("vcolor_is_linear") == true, "linear glTF vertex colour")
			var texture = m.get_shader_parameter("tex_nearest")
			if texture != null: check(not texture.get_image().has_mipmaps(), "mipmaps disabled")
			if m.get_meta("kind", "") == "chrome_env":
				check(m.get_shader_parameter("surface_mode") == 1, "chrome sphere shader")
				check(m.get_shader_parameter("env_tex") != null, "chrome env texture present")
		if not actor.faces.is_empty():
			actor.expression(0)
			var zero = actor.faces[0].material.get_shader_parameter("uv_offset")
			actor.expression(1)
			check(actor.faces[0].material.get_shader_parameter("uv_offset") != zero, "expression atlas swaps")
		rows.append({"character":row.character_id,"selector":row.authored_variant,"sample_time":actor.sample_time,"ground_offset":actor.ground_offset,"materials":actor.materials.size()})
		actor.free()
	# Observe completed native controller steps and actual simulated time under load.
	var driver = load("res://actors/motion_test.gd").new()
	root.add_child(driver)
	driver.position = Vector3(2,1,2)
	driver.bounds = Vector2(30,30)
	# Preserve the original 2.4 m/s oracle as an explicit profile fixture; the
	# shipped controls default is now 3.2 with a finite acceleration ramp.
	driver.actions.configure({"version":1,"options":{"run_mode":"auto"},"tuning":{"run_speed_mps":2.4}})
	driver.tuning = driver.actions.profile.tuning.duplicate()
	var source: Dictionary = bindings.characters[0]
	var visual = resolver.character({"id":"motion","body_id":source.body_id,"base_rig_id":source.base_rig_id,"params":source.params})
	driver.add_child(visual)
	var event := InputEventKey.new()
	event.physical_keycode = KEY_D
	event.pressed = true
	Input.parse_input_event(event)
	Input.flush_buffered_events()
	for warmup in 30: await driver.stepped
	var motion := []
	for fps in [15.0,5.0]:
		visual.pose_fps = fps
		visual.play_clip("walk")
		if OS.get_cmdline_user_args().has("--character-bad-clock"):
			driver.tuning.run_speed_mps = 2.4 * fps / 15.0
		var before: float = driver.position.x
		var seconds: float = driver.seconds
		var steps: int = driver.steps
		for frame in 60: await driver.stepped
		var elapsed: float = driver.seconds - seconds
		motion.append({"pose_fps":fps,"steps":driver.steps-steps,"seconds":elapsed,"distance":driver.position.x-before,"speed":(driver.position.x-before)/elapsed})
		check(driver.steps-steps == 60, "60 completed physics steps")
	event.pressed = false
	Input.parse_input_event(event)
	check(absf(motion[0].speed-motion[1].speed) < 0.05, "movement independent of pose fps")
	check(absf(motion[0].speed-2.4) < 0.1 and absf(motion[1].speed-2.4) < 0.1, "real controller speed 2.4 m/s")
	driver.queue_free()
	await process_frame
	# Explicit missing-real-GLB fallback; a hash mismatch must NOT silently downgrade.
	var bad := bindings.duplicate(true)
	bad.characters[0].path += ".missing"
	var fallback_resolver = load("res://actors/assets.gd").new()
	fallback_resolver.configure(bad,theme)
	var r: Dictionary = bad.characters[0]
	var fallback = fallback_resolver.character({"id":"fallback","body_id":r.body_id,"base_rig_id":r.base_rig_id,"params":r.params})
	check(fallback != null and fallback.get_meta("placeholder", false), "missing optional model falls back")
	if fallback != null: fallback.free()
	var result := {"status":"passed" if failures.is_empty() else "failed", "bound_instances":rows.size(),"checks":checks,"failures":failures.size(),"errors":failures,"rows":rows,"motion":motion}
	var f := FileAccess.open("res://actor-test.json",FileAccess.WRITE)
	f.store_string(JSON.stringify(result,"\t"))
	f.close()
	print("CHARACTERS instances=%d checks=%d failures=%d" % [rows.size(),checks,failures.size()])
	quit(0 if failures.is_empty() else 1)
