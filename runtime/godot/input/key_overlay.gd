extends Control
## UI5 key overlay: the pause menu (every game) and, for games whose metadata.hud opts in (/hermes64 new
## sets it), the keycap interact prompt and the corner controls hint. Drawn in the window canvas at an
## INTEGER number of physical pixels per UI pixel (Keycaps.ui_scale), above the low-resolution world frame,
## so the world's own upscale filter never touches its 1-pixel strokes. Data: res://input/keyhud.json.
## Presentation only: it reads the presenter and never writes simulation, replay or save state.
const Keycaps = preload("res://input/keycaps.gd")
const PixelFont = preload("res://look/pixel_font.gd")
const ROW := Keycaps.KEYCAP_H + 2
const PAD := 8
const COL_GAP := 12
const GAP := 4
const HEADER := Keycaps.ICON + 6

var view
var font
var data := {}
var prompt_mode := "legacy"     # legacy: input/hud.gd keeps the old low-resolution prompt (old golden games)
var hint_mode := "off"          # corner: keycap strip at start / resume / first-relevant moments
var hint := {"moment": "", "actions": [], "left": 0.0, "alpha": 0.0, "until": "", "shown": {}}
var prompt := {"alpha": 0.0, "id": "", "icon": "", "at": Vector3.ZERO, "distance": 0.0}
var was_paused := false
var was_menu := false
var override_window := Vector2.ZERO   # tests: pretend the window is this many physical pixels
var last := {}                        # what the last frame laid out (tests and proof captures read it)

func setup(presenter) -> void:
	view = presenter
	font = PixelFont.get_font()
	var parsed = JSON.parse_string(FileAccess.get_file_as_string("res://input/keyhud.json")) if FileAccess.file_exists("res://input/keyhud.json") else null
	data = parsed if parsed is Dictionary else {}
	var meta = view.runtime.game.get("metadata", {})
	var hud = meta.get("hud", {}) if meta is Dictionary else {}
	if not hud is Dictionary: hud = {}
	prompt_mode = str(view.options.get("ui_prompt", hud.get("interact_prompt", "legacy")))
	hint_mode = str(view.options.get("ui_hint", hud.get("controls_hint", "off")))
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	set_anchors_preset(Control.PRESET_FULL_RECT)
	if hint_mode == "corner": show_moment("start")

func colors() -> Dictionary:
	var lamp: Color = view.n64_ui.C_LAMP if view.n64_ui != null else Color("f2d58a")
	var ink: Color = view.n64_ui.C_INK if view.n64_ui != null else Color("0b0d12")
	return {"lamp": lamp, "ink": ink, "panel": Color(0.03, 0.04, 0.06, 1.0), "cap": Color(0.03, 0.04, 0.06, 1.0)}

func window_px() -> Vector2:
	if override_window != Vector2.ZERO: return override_window
	return Vector2(get_window().size) if is_inside_tree() else Vector2(1280, 720)

func metrics(scale := 0) -> Dictionary:
	var win := window_px()
	var canvas: Vector2 = win if override_window != Vector2.ZERO or not is_inside_tree() else get_viewport().get_visible_rect().size
	var p := scale if scale > 0 else Keycaps.ui_scale(win)
	var ui := (win / float(p)).floor()
	return {"window": win, "canvas": canvas, "s": win.y / maxf(canvas.y, 1.0), "p": p, "ui": ui,
		"origin": ((win - ui * float(p)) / 2.0).floor()}

# ---------------- pause menu ----------------
func pause_rows() -> Dictionary:
	var a = view.actions
	var pause: Dictionary = data.get("pause", {})
	var left := []
	for row in pause.get("controls", []):
		var act: String = str(row.get("action", ""))
		if act == "run" and not a.profile.bindings.has("run"): continue
		var l: Dictionary = Keycaps.move_label(a) if act == "move" else Keycaps.label(a, act)
		if l.get("unbound", false): continue
		left.append({"key": l, "icon": str(row.get("icon", "look")), "word": str(row.get("word", "")), "action": act})
	var right := []
	var res: Dictionary = pause.get("resume", {})
	if not res.is_empty():
		right.append({"key": Keycaps.label(a, str(res.action)), "icon": str(res.icon), "word": str(res.word), "action": str(res.action)})
	for row in pause.get("settings", []):
		var act: String = str(row.get("action", ""))
		if act == "run" and not a.profile.bindings.has("run"): act = str(row.get("legacy_action", "walk"))
		var l: Dictionary = Keycaps.label(a, act)
		if l.get("unbound", false): continue
		var option: String = str(row.get("option", ""))
		var value = a.profile.get(option, "") if option == "preset" else a.profile.options.get(option, "")
		var words: Dictionary = row.get("words", {})
		var key := str(value).to_lower()
		right.append({"key": l, "icon": str(row.get("icon", "settings")).replace("PRESET", str(a.profile.get("preset", "left"))),
			"word": str(words.get(key, value)), "known": words.has(key), "action": act, "setting": option})
	return {"left": left, "right": right}

func column(rows: Array, word_max: int, settings_from := -1) -> Dictionary:
	var key_w := 0
	var word_w := 0
	for r in rows:
		key_w = maxi(key_w, Keycaps.keycap_width(font, r.key))
		word_w = maxi(word_w, mini(Keycaps.measure(font, r.word), word_max))
	var h := rows.size() * ROW - 2
	if settings_from >= 0 and settings_from < rows.size(): h += HEADER
	return {"rows": rows, "key_w": key_w, "word_w": word_w, "w": key_w + GAP + Keycaps.ICON + GAP + word_w, "h": maxi(h, 0), "settings_from": settings_from}

func pause_layout(m: Dictionary) -> Dictionary:
	var rows := pause_rows()
	var word_max := int(data.get("pause", {}).get("word_max_px", 44))
	var a := column(rows.left, word_max)
	var b := column(rows.right, word_max, 1)
	var ui: Vector2 = m.ui
	var wide := Vector2(PAD * 2 + a.w + COL_GAP + b.w, PAD * 2 + HEADER + maxi(a.h, b.h))
	var tall := Vector2(PAD * 2 + maxi(a.w, b.w), PAD * 2 + HEADER + a.h + PAD + b.h)
	var mode := "columns"
	var stack := false
	if wide.x > ui.x or wide.y > ui.y:
		mode = "stacked" if tall.x <= ui.x and tall.y <= ui.y else "clipped"
		stack = mode == "stacked" or wide.x > ui.x
	var size: Vector2 = tall if stack else wide
	size = Vector2(minf(size.x, ui.x), minf(size.y, ui.y))
	var panel := Rect2(((ui - size) / 2.0).floor(), size)
	var out := {"panel": panel, "mode": mode, "fits": mode != "clipped", "rows": [], "clipped_rows": 0, "overflow": [], "missing": [], "unknown_values": []}
	var origins := [panel.position + Vector2(PAD, PAD + HEADER), panel.position + Vector2(PAD + a.w + COL_GAP, PAD + HEADER)]
	if stack: origins[1] = panel.position + Vector2(PAD, PAD + HEADER + a.h + PAD)
	var cols := [a, b]
	for c in 2:
		var col: Dictionary = cols[c]
		var y: float = origins[c].y
		for i in col.rows.size():
			if i == col.settings_from: y += HEADER
			var r: Dictionary = col.rows[i]
			var key_rect := Rect2(origins[c].x, y, Keycaps.keycap_width(font, r.key), Keycaps.KEYCAP_H)
			var fitted: Dictionary = Keycaps.fit(font, r.word, word_max)
			var row := {"action": r.action, "column": c, "key": r.key, "key_rect": key_rect, "icon": r.icon,
				"icon_at": Vector2(origins[c].x + col.key_w + GAP, y + 2), "word": fitted.text, "word_full": r.word,
				"word_at": Vector2(origins[c].x + col.key_w + GAP + Keycaps.ICON + GAP, y + 2), "word_overflow": fitted.overflow,
				"key_check": Keycaps.fit(font, r.key.get("text", ""), Keycaps.MAX_LABEL_W)}
			if c == 1 and i == col.settings_from: row["header_at"] = Vector2(origins[c].x, y - HEADER)
			if key_rect.end.y > panel.end.y or key_rect.end.x > panel.end.x or row.word_at.x + fitted.width > panel.end.x:
				out.clipped_rows += 1
				y += ROW
				continue
			if fitted.overflow: out.overflow.append(r.word)
			if row.key_check.overflow: out.overflow.append(r.key.get("text", ""))
			for g in fitted.missing + row.key_check.missing: out.missing.append(g)
			if r.has("known") and not r.known: out.unknown_values.append(r.word)
			out.rows.append(row)
			y += ROW
	if out.clipped_rows > 0: out.fits = false
	return out

func fit_pause(m: Dictionary) -> Array:
	## The pause panel steps down one whole pixel scale at a time until it fits (portrait/small windows);
	## only at 1 physical px per UI px may rows be clipped (reported in the layout).
	var lay := pause_layout(m)
	while not lay.fits and int(m.p) > 1:
		m = metrics(int(m.p) - 1)
		lay = pause_layout(m)
	return [m, lay]

func draw_pause(m: Dictionary, col: Dictionary) -> void:
	var fitted := fit_pause(m)
	m = fitted[0]
	var lay: Dictionary = fitted[1]
	lay["p"] = m.p
	last["pause"] = lay
	draw_set_transform(m.origin / m.s, 0.0, Vector2.ONE * (float(m.p) / m.s))
	draw_rect(lay.panel, col.panel)
	Keycaps.draw_icon(self, Vector2(lay.panel.position.x + floorf((lay.panel.size.x - Keycaps.ICON) / 2.0), lay.panel.position.y + PAD), "pause", col.lamp)
	for row in lay.rows:
		if row.has("header_at"): Keycaps.draw_icon(self, row.header_at, "settings", col.lamp)
		Keycaps.draw_keycap(self, font, row.key_rect.position, row.key, col.lamp, col.panel)
		Keycaps.draw_icon(self, row.icon_at, row.icon, col.lamp)
		Keycaps.draw_text(self, font, row.word_at, row.word, col.lamp)

# ---------------- interact prompt ----------------
func covered() -> bool:
	## The low-res frame is fading or showing the ending card: draw nothing over it.
	return view.n64_ui.fade > 0.5 or view.n64_ui.ending_a > 0.0

func prompt_visible_context() -> bool:
	return not view.belt.settings_open and not view.menu_open and not view.dialogue_active() and not view.n64_ui.inv_open and not covered()

func update_prompt(delta: float) -> void:
	if prompt_mode != "keycap": prompt.alpha = 0.0; return
	var cfg: Dictionary = data.get("prompt", {})
	var c: Dictionary = view.current_candidate
	var target := 0.0
	if not c.is_empty() and prompt_visible_context():
		var acquire := float(view.actions.profile.tuning.get("focus_acquire_m", 2.2))
		var full := float(cfg.get("full_alpha_m", 1.6))
		prompt.id = c.id; prompt.at = c.position; prompt.distance = float(c.get("distance", 0.0))
		prompt.icon = str(cfg.get("icons", {}).get(str(c.get("kind", "")), cfg.get("default_icon", "look")))
		# Never below half strength while E would act; fades to nothing only once out of reach.
		target = 1.0 - 0.5 * clampf((prompt.distance - full) / maxf(acquire - full, 0.01), 0.0, 1.0)
	var rate := 1.0 / maxf(float(cfg.get("fade_in_s" if target > prompt.alpha else "fade_out_s", 0.2)), 0.001)
	prompt.alpha = move_toward(prompt.alpha, target, rate * delta)
	if not prompt_visible_context(): prompt.alpha = 0.0

func prompt_layout(m: Dictionary) -> Dictionary:
	var cfg: Dictionary = data.get("prompt", {})
	var cam: Camera3D = view.drawing_camera()
	if prompt.alpha <= 0.001 or cam == null or prompt.id == "" or cam.is_position_behind(prompt.at): return {}
	var low: Vector2 = cam.unproject_position(prompt.at + Vector3(0, float(cfg.get("lift_m", 0.9)), 0))
	var vp := Vector2(view.viewport.size)
	var point: Vector2 = (low * (m.window / vp) - m.origin) / float(m.p)
	var key := Keycaps.label(view.actions, "primary")
	var kw := Keycaps.keycap_width(font, key)
	var w := kw + 2 + Keycaps.ICON + (2 + Keycaps.ICON if view.focus_id != "" else 0)
	var margin := float(cfg.get("margin_px", 8))
	var at := Vector2(roundf(point.x - w / 2.0), roundf(point.y - Keycaps.KEYCAP_H))
	at = at.clamp(Vector2(margin, margin), m.ui - Vector2(w + margin, Keycaps.KEYCAP_H + margin))
	return {"at": at, "key": key, "key_w": kw, "icon": prompt.icon, "alpha": prompt.alpha, "width": w, "target": prompt.id,
		"point": point, "focus": view.focus_id != ""}

func outlined_icon(at: Vector2, id: String, color: Color, ink: Color) -> void:
	for o in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]: Keycaps.draw_icon(self, at + o, id, ink)
	Keycaps.draw_icon(self, at, id, color)

func draw_prompt(m: Dictionary, col: Dictionary) -> void:
	var lay := prompt_layout(m)
	last["prompt"] = lay
	if lay.is_empty(): return
	var a: float = lay.alpha
	var lamp := Color(col.lamp, col.lamp.a * a)
	var ink := Color(col.ink, col.ink.a * a)
	Keycaps.draw_keycap(self, font, lay.at, lay.key, lamp, Color(col.cap, col.cap.a * a))
	outlined_icon(lay.at + Vector2(lay.key_w + 2, 2), lay.icon, lamp, ink)
	if lay.focus: outlined_icon(lay.at + Vector2(lay.key_w + 4 + Keycaps.ICON, 2), "focus", lamp, ink)

# ---------------- corner controls hint ----------------
func show_moment(moment: String) -> bool:
	if hint_mode != "corner": return false
	var m: Dictionary = data.get("hint", {}).get("moments", {}).get(moment, {})
	if m.is_empty() or (bool(m.get("once", false)) and hint.shown.has(moment)): return false
	hint.shown[moment] = true
	hint.moment = moment
	hint.actions = m.get("actions", [])
	hint.left = float(m.get("seconds", 6.0))
	hint.until = str(m.get("until", ""))
	return true

func on_event(kind: String) -> void:
	show_moment(kind)

func update_hint(delta: float) -> void:
	if hint_mode != "corner": hint.alpha = 0.0; return
	var paused: bool = view.belt.settings_open
	var menu: bool = view.menu_open
	if (was_paused and not paused) or (was_menu and not menu): show_moment("resume")
	was_paused = paused
	was_menu = menu
	# Waits while a text box is up (never overlaps it); its clock and dismissal count only once it can be seen.
	var gameplay: bool = view.actions.context == "gameplay" and not view.dialogue_active() and not view.n64_ui.dlg_on and not covered()
	if hint.left > 0.0 and gameplay and hint.alpha >= 0.5:
		hint.left -= delta
		if hint.until == "move" and view.actions.is_pressed("move"): hint.left = 0.0
		elif hint.until != "" and hint.until != "move" and view.actions.just_pressed(hint.until): hint.left = 0.0
	var target := 1.0 if hint.left > 0.0 and gameplay else 0.0
	hint.alpha = move_toward(hint.alpha, target, delta / maxf(float(data.get("hint", {}).get("fade_s", 0.4)), 0.001))

func hint_layout(m: Dictionary) -> Dictionary:
	if hint.alpha <= 0.001: return {}
	var cfg: Dictionary = data.get("hint", {})
	var margin := float(cfg.get("margin_px", 8))
	var icons: Dictionary = cfg.get("moments", {}).get(hint.moment, {}).get("icons", {})
	var items := []
	var x := margin
	var y: float = m.ui.y - margin - Keycaps.KEYCAP_H
	for act in hint.actions:
		var l: Dictionary = Keycaps.move_label(view.actions) if act == "move" else Keycaps.label(view.actions, str(act))
		if l.get("unbound", false): continue
		var kw := Keycaps.keycap_width(font, l)
		var icon := "move" if act == "move" else str(icons.get(str(act), _pause_icon(str(act))))
		if x + kw + 2 + Keycaps.ICON > m.ui.x - margin: break
		items.append({"action": act, "key": l, "at": Vector2(x, y), "key_w": kw, "icon": icon})
		x += kw + 2 + Keycaps.ICON + 6
	return {"items": items, "alpha": hint.alpha, "moment": hint.moment}

func _pause_icon(action: String) -> String:
	for row in data.get("pause", {}).get("controls", []):
		if str(row.get("action", "")) == action: return str(row.get("icon", "look"))
	return "look"

func draw_hint(m: Dictionary, col: Dictionary) -> void:
	var lay := hint_layout(m)
	last["hint"] = lay
	if lay.is_empty(): return
	var lamp := Color(col.lamp, col.lamp.a * lay.alpha)
	var ink := Color(col.ink, col.ink.a * lay.alpha)
	for it in lay.items:
		Keycaps.draw_keycap(self, font, it.at, it.key, lamp, Color(col.cap, col.cap.a * lay.alpha))
		outlined_icon(it.at + Vector2(it.key_w + 2, 2), it.icon, lamp, ink)

# ---------------- frame ----------------
func _process(delta: float) -> void:
	if view == null or view.runtime == null: return
	update_prompt(delta)
	update_hint(delta)
	queue_redraw()

func _draw() -> void:
	if view == null or view.runtime == null or font == null: return
	var m := metrics()
	last = {"metrics": m}
	draw_set_transform(m.origin / m.s, 0.0, Vector2.ONE * (float(m.p) / m.s))
	var col := colors()
	if view.belt.settings_open:
		draw_pause(m, col)
		return
	draw_prompt(m, col)
	draw_hint(m, col)
