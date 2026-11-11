extends SceneTree
## UI5 key overlay checks (headless): pause layout at three window sizes, keycap prompt and corner hint
## timing, pad glyphs, and known-bad controls (missing glyph, label longer than its column, window too small).
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Keycaps = preload("res://input/keycaps.gd")
var view
var checks := 0
var failures := []
var report := {}

func check(ok: bool, what: String) -> void:
	checks += 1
	if not ok: failures.append(what)

func _initialize() -> void: call_deferred("run")

func frame(digital := []) -> void:
	view.actions.submit_frame({"digital": digital})
	await physics_frame
	await process_frame

func inside(r: Rect2, outer: Rect2) -> bool:
	return r.position.x >= outer.position.x and r.position.y >= outer.position.y and r.end.x <= outer.end.x and r.end.y <= outer.end.y

func layout_ok(lay: Dictionary, ui: Vector2) -> bool:
	if not inside(lay.panel, Rect2(Vector2.ZERO, ui)): return false
	for row in lay.rows:
		if not inside(row.key_rect, lay.panel): return false
		if row.word_at.x + Keycaps.measure(view.key_overlay.font, row.word) > lay.panel.end.x: return false
	return true

func run() -> void:
	var opts := {"pack": "res://theme.json", "bindings": "res://bindings.json", "test": true}
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--ui_prompt="): opts["ui_prompt"] = a.get_slice("=", 1)
		if a.begins_with("--ui_hint="): opts["ui_hint"] = a.get_slice("=", 1)
	view = View.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(Wire.read_json("res://game.json"), opts)
	check(booted.ok, "boot " + str(booted))
	view.actions.set_source("bot")
	view.n64_ui.hide_dialog()
	var ov = view.key_overlay
	check(ov != null and ov.get_parent() is CanvasLayer, "overlay sits on its own canvas layer above the world surface")
	var meta = view.runtime.game.metadata.get("hud", {})
	report["metadata_hud"] = meta
	report["prompt_mode"] = ov.prompt_mode
	report["hint_mode"] = ov.hint_mode
	# ---- pause layout at three window sizes (physical px) ----
	view.belt.settings_open = true
	var sizes := {}
	for s in [Vector2(1280, 720), Vector2(1920, 1080), Vector2(3024, 1964)]:
		ov.override_window = s
		var m: Dictionary = ov.metrics()
		var lay: Dictionary = ov.pause_layout(m)
		var last_bottom := 0.0
		for row in lay.rows: last_bottom = maxf(last_bottom, row.key_rect.end.y)
		sizes["%dx%d" % [s.x, s.y]] = {"p": m.p, "ui": [m.ui.x, m.ui.y], "mode": lay.mode, "rows": lay.rows.size(),
			"panel": [lay.panel.position.x, lay.panel.position.y, lay.panel.size.x, lay.panel.size.y],
			"bottom_margin_ui_px": lay.panel.end.y - last_bottom, "overflow": lay.overflow, "missing": lay.missing,
			"glyph_cap_px": 7 * m.p, "stroke_px": m.p}
		check(m.p == int(s.y / 240.0), "integer UI scale %s -> %d" % [str(s), m.p])
		check(lay.fits and lay.mode == "columns", "pause fits in two columns at " + str(s))
		check(layout_ok(lay, m.ui), "every keycap and word inside the panel at " + str(s))
		check(lay.overflow.is_empty() and lay.missing.is_empty(), "default labels: no overflow, no missing glyph at " + str(s))
		check(lay.panel.end.y - last_bottom >= 8, "last row keeps >= 8 UI px padding at " + str(s))
		var words := []
		for row in lay.rows: words.append(row.word)
		check(words.all(func(w): return w.split(" ").size() == 1), "one plain word per row")
		check(not ("precision" in words) and not ("off" in words), "no unexplained legacy values")
	report["pause"] = sizes
	# settings words follow the live profile
	ov.override_window = Vector2(1280, 720)
	var lay0: Dictionary = ov.pause_layout(ov.metrics())
	var settings_words := []
	for row in lay0.rows:
		if row.column == 1: settings_words.append(row.word)
	report["right_column"] = settings_words
	check(settings_words.size() >= 5 and settings_words[0] == "Resume", "right column: Resume then settings")
	# ---- known-bad: missing glyph and label longer than its column ----
	var font = ov.font
	check(Keycaps.missing(font, "Esc").is_empty() and Keycaps.missing(font, "F9").is_empty() and Keycaps.missing(font, "Alt").is_empty(), "Esc/F9/Alt fully covered")
	check(Keycaps.missing(font, "§") == ["§"], "known-bad: missing glyph detected")
	var long_fit: Dictionary = Keycaps.fit(font, "Interactiveness", 44)
	check(long_fit.overflow and long_fit.width <= 44, "known-bad: long word cut to its column")
	var bad_rows: Dictionary = ov.pause_rows()
	bad_rows.left[0] = {"key": {"text": "§x", "icon": ""}, "icon": "move", "word": "Interactiveness", "action": "bad"}
	bad_rows.left[1] = {"key": {"text": "Backspacebar", "icon": ""}, "icon": "use", "word": "Use", "action": "bad2"}
	var saved: Dictionary = ov.data.pause.duplicate(true)
	var bad_data := saved.duplicate(true)
	bad_data.controls[0] = {"action": "move", "icon": "move", "word": "Interactiveness"}
	ov.data.pause = bad_data
	var bad: Dictionary = ov.pause_layout(ov.metrics())
	check("Interactiveness" in bad.overflow, "known-bad: long pause word reported as overflow")
	check(layout_ok(bad, ov.metrics().ui), "known-bad: long pause word still drawn inside the panel")
	ov.data.pause = saved
	var cap: Dictionary = {"text": "Backspacebar", "icon": ""}
	check(Keycaps.keycap_width(font, cap) <= Keycaps.MAX_LABEL_W + 2 * Keycaps.KEYCAP_PAD, "known-bad: long key label bounded")
	check(Keycaps.fit(font, cap.text, Keycaps.MAX_LABEL_W).overflow, "known-bad: long key label reported")
	report["known_bad"] = {"missing_glyph": Keycaps.missing(font, "§"), "long_word_cut_to": long_fit.text, "long_key_cut_to": Keycaps.fit(font, cap.text, Keycaps.MAX_LABEL_W).text}
	# ---- known-bad: window too small ----
	ov.override_window = Vector2(200, 150)
	var tiny_m: Dictionary = ov.metrics()
	var tiny: Dictionary = ov.pause_layout(tiny_m)
	report["too_small"] = {"p": tiny_m.p, "ui": [tiny_m.ui.x, tiny_m.ui.y], "mode": tiny.mode, "fits": tiny.fits, "clipped_rows": tiny.clipped_rows, "drawn_rows": tiny.rows.size()}
	check(tiny_m.p == 1 and not tiny.fits and tiny.mode == "clipped" and tiny.clipped_rows > 0, "known-bad: too-small window reported, rows clipped")
	check(layout_ok(tiny, tiny_m.ui), "known-bad: too-small window draws nothing outside the window")
	ov.override_window = Vector2(900, 1600)
	var tall_fit: Array = ov.fit_pause(ov.metrics())
	report["portrait"] = {"p_default": ov.metrics().p, "p_used": tall_fit[0].p, "mode": tall_fit[1].mode}
	check(tall_fit[1].mode == "stacked" and tall_fit[1].fits and layout_ok(tall_fit[1], tall_fit[0].ui), "portrait window: columns stack, scale steps down a whole pixel until it fits")
	ov.override_window = Vector2.ZERO
	# ---- known-bad: data file missing (empty data): no script error, nothing drawn outside the window ----
	var saved_data: Dictionary = ov.data
	ov.data = {}
	var empty_fit: Array = ov.fit_pause(ov.metrics())
	var empty_hint: bool = ov.show_moment("start")
	ov.data = saved_data
	report["missing_data"] = {"rows": empty_fit[1].rows.size(), "hint_shown": empty_hint}
	check(empty_fit[1].rows.is_empty() and layout_ok(empty_fit[1], empty_fit[0].ui) and not empty_hint, "known-bad: missing keyhud data draws no rows and no hint, without errors")
	view.belt.settings_open = false
	# ---- pad glyphs ----
	view.actions.active_device = "pad"
	var pad_primary: Dictionary = Keycaps.label(view.actions, "primary")
	var pad_menu: Dictionary = Keycaps.label(view.actions, "menu")
	var pad_save: Dictionary = Keycaps.label(view.actions, "quick_save")
	report["pad"] = {"primary": pad_primary, "menu": pad_menu, "quick_save": pad_save, "move": Keycaps.move_label(view.actions)}
	check(pad_primary.icon.begins_with("pad_face_"), "pad primary shows a face-button glyph")
	check(pad_menu.icon == "pad_start", "pad pause shows the start glyph")
	check(pad_save.has("chord"), "pad quick save shows its chord")
	view.actions.active_device = "key"
	# ---- corner hint timing ----
	if ov.hint_mode == "corner":
		check(ov.hint.moment == "start" and is_equal_approx(float(ov.hint.left), 8.0), "hint shown at start for 8 s")
		for i in 9: ov.update_hint(1.0)
		check(ov.hint.alpha < 0.001 and ov.hint.left <= 0.0, "hint gone after 8 s without input")
		view.belt.settings_open = true; ov.update_hint(0.016)
		view.belt.settings_open = false; ov.update_hint(0.016)
		check(ov.hint.moment == "resume" and ov.hint.left > 0.0, "hint reappears when Esc pause closes")
		view.n64_ui.dlg_on = true
		ov.update_hint(0.5); ov.update_hint(0.5)
		check(ov.hint.alpha < 0.001 and is_equal_approx(float(ov.hint.left), 4.0), "hint waits (clock stopped) while a text box is up")
		view.n64_ui.dlg_on = false
		ov.update_hint(0.5)
		check(ov.hint.alpha >= 0.5, "hint shows once the text box closes")
		for i in 3: await frame()
		for i in 5: await frame(["move_up"])
		ov.update_hint(0.016)
		check(ov.hint.left <= 0.0, "first movement dismisses the hint")
		for i in 5: await frame()
		check(ov.show_moment("challenge_started") and not ov.show_moment("challenge_started"), "a 'first matters' moment shows once")
		ov.show_moment("resume"); ov.update_hint(0.5)
		view.n64_ui.ending_a = 0.5
		for i in 3: ov.update_hint(0.5)
		check(ov.hint.alpha < 0.001, "nothing drawn over the ending card")
		view.n64_ui.ending_a = 0.0
		var keep_alpha: float = ov.hint.alpha
		ov.hint.alpha = 1.0
		ov.override_window = Vector2(1280, 720)
		ov.show_moment("start")
		report["hint_items"] = ov.hint_layout(ov.metrics()).get("items", []).map(func(it): return [it.action, it.key.text, it.icon])
		ov.override_window = Vector2.ZERO
		ov.hint.alpha = keep_alpha
		check(report.hint_items.size() >= 2, "hint strip lists bound keys as keycap + icon")
	# ---- keycap interact prompt ----
	if ov.prompt_mode == "keycap":
		var door_id := ""
		for id in view.room_root.target_positions:
			if str(id).begins_with("move:" + view.runtime.state.location + ":"): door_id = id
		check(door_id != "", "room has a door target")
		if door_id != "":
			var at: Vector3 = view.room_root.target_positions[door_id]
			var centre := Vector3(view.runtime.rooms[view.runtime.state.location].grid_size[0] / 2.0, at.y, view.runtime.rooms[view.runtime.state.location].grid_size[1] / 2.0)
			view.player.position = Vector3(at.x, view.player.position.y, at.z) + (centre - at).normalized() * 1.0
			for i in 20: await frame()
			ov.update_prompt(0.5)
			report["prompt_door"] = {"candidate": view.current_candidate.get("id", ""), "kind": view.current_candidate.get("kind", ""), "icon": ov.prompt.icon, "alpha": ov.prompt.alpha}
			check(view.current_candidate.get("kind", "") == "move" and ov.prompt.icon == "door" and ov.prompt.alpha > 0.49, "door prompt: keycap + door icon visible near the door")
			view.player.position = centre + (centre - at).normalized() * 0.5
			for i in 10: await frame()
			for i in 4: ov.update_prompt(0.1)
			report["prompt_away_alpha"] = ov.prompt.alpha
			check(view.current_candidate.is_empty() == (ov.prompt.alpha < 0.001) or ov.prompt.alpha < 0.6, "prompt fades when walking away")
	report["ok"] = failures.is_empty()
	report["checks"] = checks
	report["failures"] = failures
	print("UI5 OVERLAY ", JSON.stringify(report))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
