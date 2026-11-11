extends "res://view/presenter.gd"
var args := {}
const ROOM_TRIS_CEILING := 8000   # kits/core/style_bible.json budget_profiles: the largest room_tris any profile may name
func _ready() -> void:
	var user_args := OS.get_cmdline_user_args()
	var i := 0
	while i < user_args.size():
		var parts := user_args[i].split("=", true, 1)
		var value := parts[1] if parts.size()>1 else "1"
		if parts.size()==1 and i+1<user_args.size() and not user_args[i+1].begins_with("--"):
			i += 1; value = user_args[i]
		args[parts[0].trim_prefix("--")] = value
		i += 1
	var data = Wire.read_json(args.get("game", "res://game.json"))
	if not data is Dictionary:
		print("BOOT ERROR: supply --game=/path/to/compiled/game.json")
		await quit_cleanly(2)
		return
	var opts := args.duplicate()
	if args.has("asset_map"): opts.asset_map = Wire.read_json(args.asset_map)
	var result := boot(data, opts)
	if not result.ok:
		print("BOOT ERROR: ", result)
		await quit_cleanly(2)
		return
	print("BOOT game=%s version=%s rooms=%d godot=%s display=%s renderer=%s adapter=%s" % [data.id, data.contract_version, data.rooms.size(), Engine.get_version_info().string, DisplayServer.get_name(), RenderingServer.get_current_rendering_method(), RenderingServer.get_video_adapter_name()])
	if args.has("observe"):
		var observer = preload("res://view/input_observer.gd").new()
		add_child(observer)
		observer.attach(self,args.observe)
	if args.has("replay"):
		# GAPS2 G14: --capture_scenes=<folder> keeps the replay running past its final hash and saves scene/results frames.
		var capturing := args.has("capture_scenes")
		var playback: Dictionary = replay.load_movie(args.replay,not capturing)
		if not playback.ok: print("MOVIE REFUSED ",playback); await quit_cleanly(2)
		elif capturing:
			var capture_node = preload("res://view/scene_capture.gd").new()
			add_child(capture_node)
			capture_node.attach(self,str(args.capture_scenes),float(args.get("capture_tail","90")))
		return
	if args.has("record"): replay.start_record(args.record,int(args.get("seed","7")))
	if args.has("screens"):
		# GAPS2 (G12 sibling): room coverage frames (style audit, open screenshots) show the rooms, never a start/enter
		# scene card drawn over them. Set before the first await, so no start scene begins.
		if scene_cards != null: scene_cards.enabled = false
		await capture_all(args.screens)
	elif args.has("bot"):
		var bot = preload("res://view/bot.gd").new()
		add_child(bot)
		bot.run(self, args.bot, args.get("shots", ProjectSettings.globalize_path("res://../evidence/shots")))
	elif args.has("quit_after"):
		await get_tree().create_timer(float(args.quit_after)).timeout
		await quit_cleanly()
func capture_all(folder: String) -> void:
	# Authored-angle art audit, not the default follow-camera play view.
	if follow_camera != null: follow_camera.enabled = false
	DirAccess.make_dir_recursive_absolute(folder)
	var rows := []
	var ok := DisplayServer.get_name() != "headless"
	for room in runtime.game.rooms:
		# Visual-coverage harness only; never reported as reachability or playthrough.
		runtime.state.location = room.id
		enter_room("")
		if follow_camera != null: follow_camera.enabled = false
		last_text = boxed(room.description)   # GAPS2 G9: the audit frame shows what the player sees
		page_index = 0
		refresh()
		n64_ui.skip_typing()
		await get_tree().create_timer(0.25).timeout
		var path := folder.path_join(room.id+".png")
		var captured: bool = await capture(path)
		# Style-gate passes: the same frame without UI, then with a key-coloured clear colour so
		# uncovered background (cutaway void) can be measured exactly. Restored afterwards.
		n64_ui.visible = false
		await get_tree().process_frame
		var clean_ok: bool = await capture_low(folder.path_join(room.id+"-clean.png"))
		# screen-space rain is in the game view only: the key/depth/mask passes are read as exact colours
		var weather_layer = room_root.get_node_or_null("weather")
		if weather_layer != null: weather_layer.visible = false
		var env: Environment = world_environment().environment
		var clear: Color = env.background_color
		env.background_color = Color(1, 0, 1)
		# the key pass is read as exact colours too (uncovered background), so edges are not antialiased into it
		var key_msaa := viewport.msaa_3d
		viewport.msaa_3d = Viewport.MSAA_DISABLED
		await get_tree().process_frame
		var key_ok: bool = await capture_low(folder.path_join(room.id+"-key.png"))
		viewport.msaa_3d = key_msaa
		env.background_color = clear
		# N64-FIDELITY evidence passes (UI hidden, actors visible; not inputs of the defect gate): the same frame
		# without glow/halo cards, then with the non-N64 lighting features (per-pixel point lights, specular glints,
		# fresnel rims) switched off. The n64_fidelity gate section measures how much light each contributes.
		var glows := []
		for n in room_root.find_children("*", "MeshInstance3D", true, false):
			var gm = n.material_override
			if n.visible and gm is ShaderMaterial and gm.shader != null and (gm.shader.resource_path.ends_with("n64_glow.gdshader") or gm.shader.resource_path.ends_with("n64_halo.gdshader")):
				n.visible = false
				glows.append(n)
		await get_tree().process_frame
		var noglow_ok: bool = await capture_low(folder.path_join(room.id+"-noglow.png"))
		for n in glows: n.visible = true
		const RigLook = preload("res://look/rig.gd")
		RenderingServer.global_shader_parameter_set("n64_classic", Vector4(0, 0, 0, 0))
		await get_tree().process_frame
		var classic_ok: bool = await capture_low(folder.path_join(room.id+"-classic.png"))
		RenderingServer.global_shader_parameter_set("n64_classic", RigLook.classic)
		# Distance + region-mask passes for exterior depth bands and golden-diff regions. Placeholder actors
		# (owned by another lane) and additive glow cards are hidden; everything is restored afterwards.
		var hidden := []
		for n in room_root.find_children("*", "Node3D", true, false) + [player] + followers.values():
			if n.visible and (n == player or followers.values().has(n) or str(n.get_meta("placed", "")) == "actor"):
				n.visible = false
				hidden.append(n)
		# id/distance passes are read as exact colours: no edge antialiasing blends between regions
		var msaa := viewport.msaa_3d
		viewport.msaa_3d = Viewport.MSAA_DISABLED
		RenderingServer.global_shader_parameter_set("n64_debug", Vector4(1, 120, 0, 0))
		env.background_color = Color(1, 1, 1)
		await get_tree().process_frame
		var depth_ok: bool = await capture_low(folder.path_join(room.id+"-depth.png"))
		RenderingServer.global_shader_parameter_set("n64_debug", Vector4(2, 0, 0, 0))
		env.background_color = Color(0, 0, 0)
		await get_tree().process_frame
		var mask_ok: bool = await capture_low(folder.path_join(room.id+"-mask.png"))
		RenderingServer.global_shader_parameter_set("n64_debug", Vector4(0, 0, 0, 0))
		viewport.msaa_3d = msaa
		for n in hidden: n.visible = true
		if weather_layer != null: weather_layer.visible = true
		env.background_color = clear
		# Character close-up (evidence only, not a gate input): the tallest person in the room seen from the room
		# camera's side, UI hidden. The room camera is current again before the next room.
		var closeup: Dictionary = await capture_closeup(folder.path_join(room.id+"-closeup.png"))
		n64_ui.visible = true
		var tri: int = room_root.triangle_count() + room_root.triangle_count(player)
		# Room triangle cap: 6,000 unless the compiled room presentation names a larger budget profile (the style
		# bible's arena profile, written by the room compiler); never above ROOM_TRIS_CEILING.
		var cap: int = clampi(int(room_root.presentation.get("budget", {}).get("room_tris", 6000)), 1, ROOM_TRIS_CEILING)
		var good: bool = captured and clean_ok and key_ok and depth_ok and mask_ok and tri <= cap and room_root.real_piece_count > 0
		ok = ok and good
		rows.append({"id":room.id,"status":"passed" if good else "failed","screenshot":path.get_file(),"clean":room.id+"-clean.png","key":room.id+"-key.png","depth":room.id+"-depth.png","depth_scale_m":120,"mask":room.id+"-mask.png","triangles":tri,"room_tris_cap":cap,"triangles_split":room_root.triangle_split(player),"real_kit_pieces":room_root.real_piece_count,"camera":room_root.camera_nodes[camera_index].id,"audit":room_root.audit(room_root.camera_nodes[camera_index].node),"closeup":closeup,"noglow":room.id+"-noglow.png" if noglow_ok else "","classic":room.id+"-classic.png" if classic_ok else ""})
	ok = ok and resolver.missing.is_empty()
	var report := {"status":"passed" if ok else "failed","rooms":rows,"missing_assets":resolver.missing.keys(),"loaded_assets":resolver.loaded,"audio":sounds.report,"material_kinds":resolver.material_kinds,"placeholder_characters":resolver.placeholders,"renderer":RenderingServer.get_current_rendering_method(),"device":RenderingServer.get_video_adapter_name(),"engine":Engine.get_version_info().string,"display":DisplayServer.get_name(),"resolution":[viewport.size.x,viewport.size.y],"scope":"room visual coverage; teleported initial state, not a gameplay replay"}
	var file := FileAccess.open(folder.path_join("capture.json"),FileAccess.WRITE)
	file.store_string(JSON.stringify(report,"\t",true))
	file.close()
	print("CAPTURE status=%s rooms=%d missing=%d" % [report.status,rows.size(),resolver.missing.size()])
	await quit_cleanly(0 if ok else 1)

## 320x240 close-up of the room's tallest person (actor, else the protagonist), from the room camera's side.
func capture_closeup(path: String) -> Dictionary:
	if room_root.camera_nodes.is_empty(): return {}
	var subject: Node3D = null
	var best := 0.0
	for n in room_root.get_children():
		if str(n.get_meta("placed", "")) != "actor" or not n.visible: continue
		var a: AABB = Room.world_aabb(n)
		if a.size.y > best:
			best = a.size.y
			subject = n
	if best < 1.0 and player != null and player.has_node("visual"):
		var pa: AABB = Room.world_aabb(player)
		if pa.size.y > best:
			best = pa.size.y
			subject = player
	if subject == null or best <= 0.05: return {}
	var box: AABB = Room.world_aabb(subject)
	var head := box.get_center() + Vector3(0, box.size.y * 0.2, 0)
	var main_cam: Camera3D = room_root.camera_nodes[camera_index].node
	var flat := main_cam.global_position - head
	flat.y = 0.0
	var dir := flat.normalized() if flat.length() > 0.01 else Vector3(0, 0, 1)
	var cam := Camera3D.new()
	cam.fov = 40.0
	cam.near = 0.05
	room_root.add_child(cam)
	cam.global_position = head + dir * clampf(box.size.y * 1.2, 0.9, 2.4) + Vector3(0, box.size.y * 0.06, 0)
	cam.look_at(head - Vector3(0, box.size.y * 0.12, 0))
	cam.current = true
	await get_tree().process_frame
	var ok: bool = await capture_low(path)
	main_cam.current = true
	room_root.remove_child(cam)
	cam.queue_free()
	if not ok: return {}
	return {"file": path.get_file(), "subject": str(subject.name), "height_m": snappedf(box.size.y, 0.01)}
