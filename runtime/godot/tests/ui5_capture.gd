extends SceneTree
## UI5 proof captures (needs a real window): pause menu, interact prompt near a door and near an item,
## corner hint at game start, per window size (physical px). Writes PNGs and capture.json into --output.
## Also runs on the pre-UI5 runtime (no key_overlay): it then records the old pause layout analytically.
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var view
var out := ""
var rows := []

func _initialize() -> void: call_deferred("run")

func arg(name: String, fallback: String) -> String:
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--" + name + "="): return a.get_slice("=", 1)
	return fallback

func frame(digital := []) -> void:
	view.actions.submit_frame({"digital": digital})
	await physics_frame
	await process_frame

func plain(v: Variant) -> Variant:
	if v is Rect2: return [v.position.x, v.position.y, v.size.x, v.size.y]
	if v is Vector2 or v is Vector2i: return [v.x, v.y]
	if v is Vector3: return [v.x, v.y, v.z]
	if v is Dictionary:
		var d := {}
		for k in v: d[str(k)] = plain(v[k])
		return d
	if v is Array: return v.map(func(x): return plain(x))
	return v

func legacy_pause() -> Dictionary:
	## The pre-UI5 input/hud.gd pause layout (constants copied from that file), low-res frame pixels.
	var W: int = view.viewport.size.x
	var ox := (W - 320) / 2.0
	var font = view.n64_ui.font
	var keys := ["menu", "primary", "run" if view.actions.profile.bindings.has("run") else "walk", "secondary", "action_menu", "quick_save", "quick_load"]
	var boxes := []
	for i in keys.size():
		var label: String = view.actions.binding_glyph(keys[i])
		boxes.append({"label": label, "box": [ox + 81, 60 + i * 18, font.measure(label) + 4, 11]})
	if view.actions.profile.bindings.has("run"):
		var l: String = view.actions.binding_glyph("walk")
		boxes.append({"label": l, "box": [ox + 81, 185, font.measure(l) + 4, 11]})
	return {"panel": [ox + 52, 36, 216, 164], "panel_alpha": 0.94, "rows": boxes,
		"values": ["", view.actions.profile.options.focus_mode, view.actions.profile.options.run_mode,
			"on" if view.actions.profile.options.reduced_motion else "off", view.actions.profile.preset, "", "", "precision"]}

func shot(name: String, extra := {}) -> void:
	for i in 2: await process_frame
	await RenderingServer.frame_post_draw
	var img: Image = root.get_texture().get_image()
	img.save_png(out.path_join(name + ".png"))
	var low: Image = view.viewport.get_texture().get_image()
	low.save_png(out.path_join(name + "-low.png"))
	var win := DisplayServer.window_get_size()
	var row := {"name": name, "window": [win.x, win.y], "image": [img.get_width(), img.get_height()],
		"canvas": plain(root.get_visible_rect().size), "low": [view.viewport.size.x, view.viewport.size.y],
		"scale_x": float(img.get_width()) / view.viewport.size.x, "scale_y": float(img.get_height()) / view.viewport.size.y,
		"upscale_filter": "bilinear" if view.surface.texture_filter == CanvasItem.TEXTURE_FILTER_LINEAR else "nearest",
		"location": view.runtime.state.location, "candidate": view.current_candidate.get("id", ""),
		"candidate_kind": view.current_candidate.get("kind", ""), "player": plain(view.player.position)}
	if view.get("key_overlay") != null:
		row["overlay"] = plain(view.key_overlay.last)
		row["prompt_mode"] = view.key_overlay.prompt_mode
		row["hint_mode"] = view.key_overlay.hint_mode
	else:
		row["legacy_pause"] = legacy_pause()
	row.merge(extra)
	rows.append(row)
	print("UI5 SHOT ", name, " ", win)

func goto_room(id: String) -> void:
	if view.runtime.state.location == id: return
	view.runtime.state.location = id
	view.enter_room("")
	view.refresh()
	view.n64_ui.hide_dialog()
	for i in 10: await frame()

func near(target_id: String) -> bool:
	var at = view.room_root.target_positions.get(target_id)
	if at == null: return false
	var room: Dictionary = view.runtime.rooms[view.runtime.state.location]
	var centre := Vector3(room.grid_size[0] / 2.0, at.y, room.grid_size[1] / 2.0)
	var dir: Vector3 = (centre - at)
	dir.y = 0
	view.player.position = Vector3(at.x, view.player.position.y, at.z) + dir.normalized() * 1.0
	for i in 40: await frame()
	return view.current_candidate.get("id", "") == target_id

func find_target(prefixes: Array) -> Array:
	for room in view.runtime.game.rooms:
		await goto_room(room.id)
		for id in view.room_root.target_positions:
			for p in prefixes:
				if str(id).begins_with(p): return [room.id, str(id)]
	return []

func run() -> void:
	out = arg("output", ProjectSettings.globalize_path("res://../ui5-captures"))
	DirAccess.make_dir_recursive_absolute(out)
	var sizes: Array = Array(arg("sizes", "1280x720,1920x1080,3024x1964").split(",")).map(func(s): return Vector2i(int(s.get_slice("x", 0)), int(s.get_slice("x", 1))))
	var shots := arg("shots", "hint,pause,door,item").split(",")
	var opts := {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true}
	if arg("ui_prompt", "") != "": opts["ui_prompt"] = arg("ui_prompt", "")
	if arg("ui_hint", "") != "": opts["ui_hint"] = arg("ui_hint", "")
	DisplayServer.window_set_size(sizes[0])
	view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), opts)
	if not booted.ok:
		printerr("UI5 CAPTURE boot failed ", booted)
		quit(2)
		return
	view.actions.set_source("bot")
	view.n64_ui.hide_dialog()
	var start_room: String = view.runtime.state.location
	var first := true
	for size in sizes:
		DisplayServer.window_set_size(size)
		for i in 12: await frame()
		# presenter.resize_screen() re-runs sync_n64_ui(), which re-opens the room-description box (existing
		# behaviour); close it as at boot so every size is captured in the same state.
		view.n64_ui.hide_dialog()
		for i in 2: await frame()
		if "hint" in shots:
			if not first and view.get("key_overlay") != null: view.key_overlay.show_moment("start")
			for i in 30: await frame()
			await shot("hint-start-%dx%d" % [size.x, size.y], {"seconds_since_boot": Time.get_ticks_msec() / 1000.0})
		first = false
		if "pause" in shots:
			await frame(["menu"])
			for i in 4: await frame()
			await shot("pause-%dx%d" % [size.x, size.y])
			await frame(["menu"])
			for i in 4: await frame()
		if "door" in shots:
			var door: Array = await find_target(["move:"])
			if not door.is_empty():
				await goto_room(door[0])
				var ok := await near(door[1])
				await shot("prompt-door-%dx%d" % [size.x, size.y], {"target": door[1], "in_reach": ok})
		if "item" in shots:
			var item: Array = await find_target(["collect:", "interact:"])
			if not item.is_empty():
				await goto_room(item[0])
				var ok2 := await near(item[1])
				await shot("prompt-item-%dx%d" % [size.x, size.y], {"target": item[1], "in_reach": ok2})
		await goto_room(start_room)
	var f := FileAccess.open(out.path_join("capture.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify({"rows": rows, "godot": Engine.get_version_info().string, "screen_scale": DisplayServer.screen_get_scale()}, "  "))
	f.close()
	print("UI5 CAPTURE done ", rows.size())
	await view.quit_cleanly(0)
