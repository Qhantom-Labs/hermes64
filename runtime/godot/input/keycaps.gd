extends RefCounted
## UI5 shared keycap / prompt component. Original geometric glyphs authored for this project (CC0-1.0);
## no controller or keyboard brand artwork. One system for every key glyph on screen: the pause menu,
## the interact prompt and the corner controls hint (input/key_overlay.gd), and any module/arena hint
## that wants keycaps (Keycaps.label() + Keycaps.draw_keycap(); see docs/UI5-HUNKS.md).
##
## Callers draw this pixel art at an INTEGER number of physical pixels per UI pixel (ui_scale), outside
## the low-resolution world frame, so the N64 bilinear world upscale never smears a 1-pixel stroke.
const PixelFont = preload("res://look/pixel_font.gd")

const KEYCAP_H := 11          # 7 px cap height + 2 px above + 2 px below, as the old keycap
const KEYCAP_PAD := 2         # text inset left/right/top
const MAX_LABEL_W := 28       # widest keycap text in UI px ("Space"); longer labels are cut and reported
const ICON := 7               # icons are 7x7 UI px
const MIN_UI_ROWS := 240      # vertical UI pixels the layouts are authored for

## OS.get_keycode_string names -> short keycap text (every character exists in the pixel font or SYMBOLS).
const KEY_NAMES := {"Escape":"Esc","Shift":"Shift","Option":"Alt","Alt":"Alt","Space":"Space","Enter":"Enter",
	"Kp Enter":"Enter","Control":"Ctrl","Ctrl":"Ctrl","Command":"Cmd","Meta":"Cmd","Backspace":"Bksp","Tab":"Tab",
	"CapsLock":"Caps","Delete":"Del","Insert":"Ins","Home":"Home","End":"End","PageUp":"PgUp","PageDown":"PgDn",
	"Period":".","Comma":",","Slash":"/","Minus":"-","Equal":"=","Semicolon":";","Apostrophe":"'",
	"BracketLeft":"[","BracketRight":"]","Backslash":"\\","QuoteLeft":"`","Up":"^U","Down":"^D","Left":"^L","Right":"^R"}

## 5x7 symbols the shared pixel font does not carry. "^U" etc. are arrow tokens (one glyph each).
const SYMBOLS := {
	"[": ["###","#..","#..","#..","#..","#..","###"],
	"]": ["###","..#","..#","..#","..#","..#","###"],
	"\\": ["#....",".#...",".#...","..#..","...#.","...#.","....#"],
	"`": ["#.",".#"],
	"#": [".#.#.","#####",".#.#.",".#.#.",".#.#.","#####",".#.#."],
	"^U": ["..#..",".###.","#.#.#","..#..","..#..","..#..","..#.."],
	"^D": ["..#..","..#..","..#..","..#..","#.#.#",".###.","..#.."],
	"^L": [".......","..#....",".#.....","#######",".#.....","..#....","......."],
	"^R": [".......","....#..",".....#.","#######",".....#.","....#..","......."],
}

## 7x7 icons. talk/take/door/look are the established look/ui.gd prompt icons; the rest are new, same style.
const ICONS := {
	"talk": [".#####.","#######","#######","#######",".#####.","..##...",".#....."],
	"take": ["...#...","...#...","..###..","#######","..###..","...#...","...#..."],
	"door": ["...#...","..###..",".#####.","#######","..###..","..###..","..###.."],
	"look": [".......","..###..",".#...#.","#..#..#",".#...#.","..###..","......."],
	"use": ["......#",".....#.","....#..","...#...","..###..",".#####.","#######"],
	"move": ["...#...","..###..","#..#..#","#######","#..#..#","..###..","...#..."],
	"dodge": ["..###..",".#...#.","#.....#","....#.#","...##.#","..####.","...##.."],
	"run": ["....##.","..###..",".#.##..","...###.","..#..#.",".#....#","#......"],
	"walk": ["...##..","...##..","..###..",".#.#.#.","...#...","..#.#..","..#.#.."],
	"focus": ["##...##","#.....#","...#...","..###..","...#...","#.....#","##...##"],
	"back": ["..#....",".##....","######.",".##...#","..#...#",".....#.","..###.."],
	"actions": [".......","#.#####",".......","#.#####",".......","#.#####","......."],
	"items": ["..###..",".#...#.","#######","#.....#","#..#..#","#.....#","#######"],
	"save": ["######.","#.##..#","#.##..#","#.....#","#.###.#","#.###.#","#######"],
	"load": ["...#...","...#...",".#####.","..###..","...#...","#.....#","#######"],
	"retry": ["..###.#",".#...##","#...###","#......","#.....#",".#...#.","..###.."],
	"play": ["#......","###....","#####..","#######","#####..","###....","#......"],
	"pause": ["##...##","##...##","##...##","##...##","##...##","##...##","##...##"],
	"motion": ["..##...",".#..#.#","#....#.",".......","..##...",".#..#.#","#....#."],
	"hand": [".#.#.#.",".#.#.#.",".#####.","######.",".#####.","..####.","..###.."],
	"keys_left": ["#######","####..#","####..#","####..#","####..#","####..#","#######"],
	"keys_right": ["#######","#..####","#..####","#..####","#..####","#..####","#######"],
	"settings": ["...#...",".#####.",".##.##.","##...##",".##.##.",".#####.","...#..."],
	"attack": ["......#",".....#.","....#..","#..#...",".##....",".##....","#..#..."],
	"climb": ["#.....#","#######","#.....#","#######","#.....#","#######","#.....#"],
	"checkpoint": ["#####..","#####..","#......","#......","#......","#......","#......"],
	"block": [".#####.","#.....#","#.....#","#.....#",".#...#.","..#.#..","...#..."],
	"camera": ["..###..",".#...#.","#.....#","#..#..#","#.....#",".#...#.","..##..."],
	"pad_start": [".......",".#####.",".......",".#####.",".......",".#####.","......."],
	"pad_back": ["####...","#..#...","#..####","####..#","...#..#","...####","......."],
	"pad_stick": ["..###..",".#...#.","#.....#","#..#..#","#.....#",".#...#.","..###.."],
}

## Godot JoyButton -> device-neutral glyph (face diamond / d-pad position) or short keycap text.
const PAD_BUTTONS := {0:"pad_face_s",1:"pad_face_e",2:"pad_face_w",3:"pad_face_n",4:"pad_back",6:"pad_start",
	7:"L3",8:"R3",9:"L1",10:"R1",11:"pad_dpad_n",12:"pad_dpad_s",13:"pad_dpad_w",14:"pad_dpad_e"}

static func ui_scale(window_px: Vector2) -> int:
	## Physical pixels per UI pixel: the largest integer that still leaves >= 240 UI rows (1 when smaller).
	return maxi(1, floori(window_px.y / float(MIN_UI_ROWS)))

static func pad_icon(id: String) -> Array:
	## Generated pad glyphs: face diamond / d-pad cross with the bound position filled.
	var rows := []
	for y in ICON: rows.append(".".repeat(ICON))
	var put := func(x: int, y: int) -> void:
		if x >= 0 and y >= 0 and x < ICON and y < ICON: rows[y] = rows[y].substr(0, x) + "#" + rows[y].substr(x + 1)
	var dirs := {"n": Vector2i(3, 1), "w": Vector2i(1, 3), "e": Vector2i(5, 3), "s": Vector2i(3, 5)}
	if id.begins_with("pad_face_"):
		for d in dirs:
			var c: Vector2i = dirs[d]
			if d == id.substr(9):
				for oy in [-1, 0, 1]:
					for ox in [-1, 0, 1]: put.call(c.x + ox, c.y + oy)
			else: put.call(c.x, c.y)
		return rows
	if id.begins_with("pad_dpad_"):
		for i in ICON:
			put.call(3, i)
			put.call(i, 3)
		var c: Vector2i = dirs.get(id.substr(9), Vector2i(3, 3))
		for oy in [-1, 0, 1]:
			for ox in [-1, 0, 1]: put.call(c.x + ox, c.y + oy)
		return rows
	return ICONS.get(id, [])

static func key_text(keycode: int) -> String:
	var text := OS.get_keycode_string(keycode)
	return KEY_NAMES.get(text, text)

static func label_for_binding(binding: Dictionary, physical_labels := true) -> Dictionary:
	## One binding -> {"text": keycap text, "icon": glyph id, "chord": [labels held with it]}.
	if binding.has("button"):
		var id: String = PAD_BUTTONS.get(int(binding.button), "B%d" % int(binding.button))
		var out := {"text": "", "icon": id} if id.begins_with("pad_") else {"text": id, "icon": ""}
		if binding.has("with"): out["chord"] = [label_for_binding({"button": int(binding.with)}, false)]
		return out
	if binding.has("axis"):
		var axis := int(binding.axis)
		var positive: bool = float(binding.get("sign", 1)) > 0
		if axis == JOY_AXIS_TRIGGER_LEFT: return {"text": "L2", "icon": ""}
		if axis == JOY_AXIS_TRIGGER_RIGHT: return {"text": "R2", "icon": ""}
		var stick := "L" if axis in [JOY_AXIS_LEFT_X, JOY_AXIS_LEFT_Y] else "R"
		if axis in [JOY_AXIS_LEFT_X, JOY_AXIS_RIGHT_X]: return {"text": stick + ("^R" if positive else "^L"), "icon": ""}
		return {"text": stick + ("^D" if positive else "^U"), "icon": ""}
	if binding.has("key"):
		var code := int(binding.key)
		if physical_labels and DisplayServer.get_name() != "headless" and not OS.has_feature("web"):
			var layout := DisplayServer.keyboard_get_label_from_physical(code)
			if layout != 0: code = layout
		return {"text": key_text(code), "icon": ""}
	return {"text": "?", "icon": ""}

static func device_is_pad(actions, device := "") -> bool:
	return (device if device != "" else str(actions.active_device)) == "pad"

static func label(actions, action: String, device := "") -> Dictionary:
	## Label for an action from the game's own input map (Actions.profile.bindings), for the active device.
	var bindings: Array = actions.profile.bindings.get(action, [])
	if device_is_pad(actions, device):
		for b in bindings:
			if b.has("button") or b.has("axis"): return label_for_binding(b, false)
	for b in bindings:
		if b.has("key"): return label_for_binding(b)
	for b in bindings:
		if b.has("button") or b.has("axis"): return label_for_binding(b, false)
	return {"text": "", "icon": "", "unbound": true}

static func move_label(actions, device := "") -> Dictionary:
	## Movement keycap: "WASD" when the four directions are single characters, else arrow tokens.
	if device_is_pad(actions, device):
		for b in actions.profile.bindings.get("move_up", []):
			if b.has("axis"): return {"text": "L" if int(b.axis) in [JOY_AXIS_LEFT_X, JOY_AXIS_LEFT_Y] else "R", "icon": "pad_stick"}
			if b.has("button"): return {"text": "", "icon": "pad_dpad_all"}
	var parts := []
	for d in ["move_up", "move_left", "move_down", "move_right"]:
		var l := label(actions, d, "key")
		if l.get("unbound", false) or l.get("icon", "") != "": return {"text": "", "icon": "move", "unbound": l.get("unbound", false)}
		parts.append(l.text)
	if parts.all(func(p): return tokens(p).size() == 1): return {"text": "".join(parts), "icon": ""}
	return {"text": "^U^L^D^R", "icon": ""}

static func tokens(text: String) -> Array:
	var out := []
	var i := 0
	while i < text.length():
		if text[i] == "^" and i + 1 < text.length() and text[i + 1] in "UDLR":
			out.append(text.substr(i, 2))
			i += 2
		else:
			out.append(text[i])
			i += 1
	return out

static func glyph_width(font, token: String) -> int:
	if token == " ": return PixelFont.SPACE_W
	if font.rects.has(token): return int(font.widths[token])
	if SYMBOLS.has(token): return SYMBOLS[token][0].length()
	return int(font.widths.get("?", 5))

static func missing(font, text: String) -> Array:
	## Characters with no glyph in the pixel font or SYMBOLS: they draw as "?" and are reported.
	var out := []
	for t in tokens(text):
		if t != " " and not font.rects.has(t) and not SYMBOLS.has(t): out.append(t)
	return out

static func measure(font, text: String) -> int:
	var w := 0
	for t in tokens(text): w += glyph_width(font, t) + PixelFont.TRACK
	return maxi(w - PixelFont.TRACK, 0)

static func fit(font, text: String, max_w: int) -> Dictionary:
	## Text cut to max_w UI px so it is never drawn past its column; reports overflow and missing glyphs.
	var miss := missing(font, text)
	var out := ""
	for t in tokens(text):
		if measure(font, out + t) > max_w: return {"text": out, "overflow": true, "missing": miss, "width": measure(font, out)}
		out += t
	return {"text": out, "overflow": false, "missing": miss, "width": measure(font, out)}

static func draw_text(ci: CanvasItem, font, at: Vector2, text: String, color: Color) -> int:
	## Pixel-font text with SYMBOLS and a visible "?" for anything missing. Returns the drawn width.
	var x := int(at.x)
	var y := int(at.y)
	for t in tokens(text):
		if font.rects.has(t):
			var r: Rect2 = font.rects[t]
			ci.draw_texture_rect_region(font.atlas, Rect2(x, y, r.size.x, r.size.y), r, color)
		elif SYMBOLS.has(t):
			var rows: Array = SYMBOLS[t]
			for ry in rows.size():
				for rx in rows[ry].length():
					if rows[ry][rx] == "#": ci.draw_rect(Rect2(x + rx, y + ry, 1, 1), color)
		elif t != " ":
			var q: Rect2 = font.rects["?"]
			ci.draw_texture_rect_region(font.atlas, Rect2(x, y, q.size.x, q.size.y), q, color)
		x += glyph_width(font, t) + PixelFont.TRACK
	return maxi(x - int(at.x) - PixelFont.TRACK, 0)

static func draw_icon(ci: CanvasItem, at: Vector2, id: String, color: Color) -> void:
	var rows: Array = pad_icon(id) if id.begins_with("pad_") else ICONS.get(id, ICONS.look)
	for y in rows.size():
		for x in rows[y].length():
			if rows[y][x] == "#": ci.draw_rect(Rect2(at.x + x, at.y + y, 1, 1), color)

static func box(ci: CanvasItem, r: Rect2, fill: Color, edge: Color) -> void:
	## Filled box with a 1 UI-pixel edge drawn as rects (a thin line stays one physical pixel when scaled).
	ci.draw_rect(r, fill)
	ci.draw_rect(Rect2(r.position, Vector2(r.size.x, 1)), edge)
	ci.draw_rect(Rect2(r.position.x, r.end.y - 1, r.size.x, 1), edge)
	ci.draw_rect(Rect2(r.position.x, r.position.y + 1, 1, r.size.y - 2), edge)
	ci.draw_rect(Rect2(r.end.x - 1, r.position.y + 1, 1, r.size.y - 2), edge)

static func content_width(font, l: Dictionary) -> int:
	var tw := int(fit(font, str(l.get("text", "")), MAX_LABEL_W).width)
	var icon: bool = str(l.get("icon", "")) != ""
	return tw + ((1 + ICON) if tw > 0 and icon else (ICON if icon else 0))

static func keycap_width(font, l: Dictionary) -> int:
	var w := maxi(content_width(font, l), 5) + KEYCAP_PAD * 2
	for c in l.get("chord", []): w += keycap_width(font, c) + 2
	return w

static func draw_keycap(ci: CanvasItem, font, at: Vector2, l: Dictionary, color: Color, fill: Color) -> Dictionary:
	## Keycap: dark fill, 1 px edge, label inset 2 px. Returns {"width", "overflow", "missing"} for checks.
	var x := at.x
	var report := {"overflow": false, "missing": []}
	for c in l.get("chord", []):
		var sub := draw_keycap(ci, font, Vector2(x, at.y), c, color, fill)
		x += float(sub.width) + 2.0
		report.overflow = report.overflow or sub.overflow
		report.missing.append_array(sub.missing)
	var fitted := fit(font, str(l.get("text", "")), MAX_LABEL_W)
	report.overflow = report.overflow or fitted.overflow
	report.missing.append_array(fitted.missing)
	var cw := content_width(font, l)
	var inner := maxi(cw, 5)
	var w := inner + KEYCAP_PAD * 2
	box(ci, Rect2(x, at.y, w, KEYCAP_H), fill, color)
	var cx := x + KEYCAP_PAD + floorf((inner - cw) / 2.0)
	if fitted.text != "": cx += draw_text(ci, font, Vector2(cx, at.y + KEYCAP_PAD), fitted.text, color) + 1
	if str(l.get("icon", "")) != "": draw_icon(ci, Vector2(cx, at.y + 2), str(l.icon), color)
	report["width"] = x + w - at.x
	return report
