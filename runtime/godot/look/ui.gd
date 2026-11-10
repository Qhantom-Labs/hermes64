extends Control
# All UI is drawn by hand at 320x240 inside the low-res viewport (so it is as chunky as the world):
# dialogue box + name tab + choices, interact prompt glyph, inventory strip, fades, ending card.
# No HUD is visible while exploring except the interact glyph when something is in reach.

const PixelFont = preload("res://look/pixel_font.gd")
const Pack = preload("res://look/pack.gd")

var W := 320 # expands with the low-resolution world; vertical pixel density is unchanged
const H := 240

func set_width(width: int) -> void:
	W = width
	size = Vector2(W,H)
	queue_redraw()
const CPS := 42.0   # typewriter characters per second
# Theme colours come from the pack's "ui" block (defaults = harbor_dusk).
var C_INK := Color("0b0d12")
var C_FILL := Color(0.043, 0.051, 0.071, 0.84)
var C_BONE := Color("bdb19c")
var C_TEXT := Color("e8e0cc")
var C_DIM := Color("a3acb8")
var C_LAMP := Color("f2d58a")

var font
var location_text := ""
var counter_text := ""
var t := 0.0

# dialogue
var dlg_on := false
var dlg_name := ""
var dlg_name_col := Color.WHITE
var dlg_text := ""
var dlg_lines := PackedStringArray()
var dlg_shown := 0.0
var dlg_total := 0
var dlg_choices: Array = []
var dlg_sel := 0
# prompt
var prompt_on := false
var prompt_pos := Vector2.ZERO
var prompt_icon := "look"
# inventory
var inv_items: Array = []      # [{id, name, icon}]
var inv_open := false
var inv_sel := 0
var inv_show := 0.0
var inv_flash_id := ""
var inv_slide := 0.0
# overlays
var fade := 0.0
var flash := 0.0
var ending_title := ""
var ending_text := ""
var ending_a := 0.0

var icons := {}
var item_icons := {}

const ICON_BITMAPS := {
	"talk": [".#####.", "#######", "#######", "#######", ".#####.", "..##...", ".#....."],
	"take": ["...#...", "...#...", "..###..", "#######", "..###..", "...#...", "...#..."],
	"door": ["...#...", "..###..", ".#####.", "#######", "..###..", "..###..", "..###.."],
	"save": ["...#...", "..##...", "..###..", ".####..", ".#####.", ".#####.", "..###.."],
	"look": [".......", "..###..", ".#...#.", "#..#..#", ".#...#.", "..###..", "......."],
}

# 12x12 item icons: k outline, a main, b highlight, c shade
const ITEM_BITMAPS := {
	"oil": {"px": [
		"............",
		"........kk..",
		".......kbbk.",
		"...kkkkkbk..",
		"..kaaaaak...",
		"..kabaaack..",
		"..kabaaack..",
		"..kaaaaack..",
		"..kaaaaack..",
		"..kaaaaack..",
		"..kkkkkkkk..",
		"............"], "a": "b5652a", "b": "f2d58a", "c": "7a2e22"},
	"gear": {"px": [
		"....kkkk....",
		"..kkkaakkk..",
		".kaakaakaak.",
		".kaaaaaaaak.",
		"kkaabbbbaakk",
		"kaaabkkbaaak",
		"kaaabkkbaaak",
		"kkaabccbaakk",
		".kaaaaaaaak.",
		".kaakaakaak.",
		"..kkkaakkk..",
		"....kkkk...."], "a": "e0a347", "b": "f2d58a", "c": "85613c"},
	"lens": {"px": [
		".....kk.....",
		"....kbbk....",
		"...kbaabk...",
		"..kbaaaabk..",
		".kbaaaaaack.",
		"kbaaaaaaacck",
		"kaaaaaaaccck",
		".kaaaaaccck.",
		"..kaaacccck.",
		"...kacccck..",
		"....kcck....",
		".....kk....."], "a": "a3acb8", "b": "e8e0cc", "c": "4f6f88"},
}

func apply_theme() -> void:
	C_INK = Pack.ui("ink", "#0b0d12")
	C_FILL = Pack.ui("fill", "#0b0d12d6")
	C_BONE = Pack.ui("frame", "#bdb19c")
	C_TEXT = Pack.ui("text", "#e8e0cc")
	C_DIM = Pack.ui("dim", "#a3acb8")
	C_LAMP = Pack.ui("accent", "#f2d58a")

func _ready() -> void:
	apply_theme()
	font = PixelFont.get_font()
	size = Vector2(W, H)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	for k in ICON_BITMAPS:
		icons[k] = _bitmap_tex(ICON_BITMAPS[k], {"#": Color.WHITE})
	for k in ITEM_BITMAPS:
		var d: Dictionary = ITEM_BITMAPS[k]
		item_icons[k] = _bitmap_tex(d.px, {"k": C_INK, "a": Color(d.a), "b": Color(d.b), "c": Color(d.c)})

func _bitmap_tex(rows: Array, cmap: Dictionary) -> ImageTexture:
	var img := Image.create(rows[0].length(), rows.size(), false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	for y in rows.size():
		for x in rows[y].length():
			var ch: String = rows[y][x]
			if cmap.has(ch):
				img.set_pixel(x, y, cmap[ch])
	return ImageTexture.create_from_image(img)

# ---------------- API ----------------
func show_line(speaker: String, speaker_col: Color, text: String, choices: Array) -> void:
	dlg_on = true
	dlg_name = speaker
	dlg_name_col = speaker_col
	dlg_text = text
	dlg_lines = font.wrap(text, W-36)
	dlg_total = 0
	for l in dlg_lines:
		dlg_total += l.length()
	dlg_shown = 0.0
	dlg_choices = choices
	dlg_sel = 0
	queue_redraw()

func hide_dialog() -> void:
	dlg_on = false
	dlg_choices = []
	queue_redraw()

func is_typing() -> bool:
	return dlg_on and int(dlg_shown) < dlg_total

func skip_typing() -> void:
	dlg_shown = float(dlg_total)

func has_choices() -> bool:
	return dlg_on and not dlg_choices.is_empty() and not is_typing()

func move_choice(d: int) -> void:
	if dlg_choices.is_empty():
		return
	dlg_sel = posmod(dlg_sel + d, dlg_choices.size())

func set_prompt(on: bool, pos := Vector2.ZERO, icon := "look") -> void:
	prompt_on = on
	prompt_pos = pos
	prompt_icon = icon

func inv_set(items: Array) -> void:
	inv_items = items
	inv_sel = clampi(inv_sel, 0, maxi(items.size() - 1, 0))

func inv_flash(id: String) -> void:
	inv_flash_id = id
	inv_show = 2.4
	for i in inv_items.size():
		if inv_items[i].id == id:
			inv_sel = i

func inv_toggle() -> void:
	inv_open = not inv_open

func flash_once() -> void:
	flash = 1.0

func fade_to(target: float, dur: float) -> void:
	var tw := create_tween()
	tw.tween_property(self, "fade", target, dur)
	await tw.finished

func show_ending(title: String, text: String) -> void:
	ending_title = title
	ending_text = text
	ending_a = 0.0
	var tw := create_tween()
	tw.tween_property(self, "ending_a", 1.0, 1.2)

func dialog_visible() -> bool:
	return dlg_on

# ---------------- frame ----------------
func _process(delta: float) -> void:
	t += delta
	if dlg_on and dlg_shown < dlg_total:
		dlg_shown = minf(dlg_shown + CPS * delta, dlg_total)
	if inv_show > 0.0:
		inv_show -= delta
	var want := 1.0 if (inv_open or inv_show > 0.0) else 0.0
	inv_slide = move_toward(inv_slide, want, delta * 6.0)
	flash = maxf(flash - delta * 4.0, 0.0)
	queue_redraw()

func _frame(r: Rect2i) -> void:
	# fill + double border (dark outer, bone inner) with chamfered corners
	draw_rect(Rect2(r.position + Vector2i(1, 1), r.size - Vector2i(2, 2)), C_FILL)
	var x0 := r.position.x
	var y0 := r.position.y
	var x1 := r.end.x - 1
	var y1 := r.end.y - 1
	draw_rect(Rect2(x0 + 2, y0, x1 - x0 - 3, 1), C_INK)
	draw_rect(Rect2(x0 + 2, y1, x1 - x0 - 3, 1), C_INK)
	draw_rect(Rect2(x0, y0 + 2, 1, y1 - y0 - 3), C_INK)
	draw_rect(Rect2(x1, y0 + 2, 1, y1 - y0 - 3), C_INK)
	draw_rect(Rect2(x0 + 2, y0 + 1, x1 - x0 - 3, 1), C_BONE)
	draw_rect(Rect2(x0 + 2, y1 - 1, x1 - x0 - 3, 1), C_BONE)
	draw_rect(Rect2(x0 + 1, y0 + 2, 1, y1 - y0 - 3), C_BONE)
	draw_rect(Rect2(x1 - 1, y0 + 2, 1, y1 - y0 - 3), C_BONE)

func _draw() -> void:
	if font != null and dlg_on:
		font.draw(self,Vector2(8,8),location_text,C_TEXT,C_INK)
		font.draw(self,Vector2(8,18),counter_text,C_DIM,C_INK)
	if prompt_on and not dlg_on and fade < 0.5:
		var bob := 1 if fmod(t, 0.8) < 0.4 else 0
		var tex: Texture2D = icons.get(prompt_icon, icons.look)
		var p := Vector2(roundi(prompt_pos.x) - 3, roundi(prompt_pos.y) - 7 - bob)
		for o in [Vector2(-1, 0), Vector2(1, 0), Vector2(0, -1), Vector2(0, 1)]:
			draw_texture(tex, p + o, C_INK)
		draw_texture(tex, p, C_LAMP)
	if inv_slide > 0.0 and not inv_items.is_empty():
		_draw_inventory()
	if dlg_on:
		_draw_dialog()
	if flash > 0.0:
		draw_rect(Rect2(0, 0, W, H), Color(1, 0.97, 0.88, flash * 0.35))
	if fade > 0.0:
		draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, fade))
	if ending_a > 0.0:
		_draw_ending()

func _draw_dialog() -> void:
	var lines_n := mini(dlg_lines.size(), 3)
	var ch_n := dlg_choices.size() if not is_typing() else 0
	var choice_rows := []
	var choice_height := 0
	for i in ch_n:
		var wrapped: PackedStringArray = font.wrap(str(dlg_choices[i]),W-56)
		choice_rows.append(wrapped)
		choice_height += maxi(1,wrapped.size())*10
	var h := 12 + lines_n * 10 + (choice_height + 3 if ch_n > 0 else 0)
	h = maxi(h, 32)
	var r := Rect2i(10, H - 8 - h, W-20, h)
	_frame(r)
	if dlg_name != "":
		var nw: int = font.measure(dlg_name) + 10
		var tr := Rect2i(r.position.x + 8, r.position.y - 9, nw, 12)
		_frame(tr)
		font.draw(self, Vector2(tr.position.x + 5, tr.position.y + 2), dlg_name, dlg_name_col, C_INK)
	# typewriter
	var left := int(dlg_shown)
	var y := r.position.y + 6
	for i in lines_n:
		var line: String = dlg_lines[i]
		var vis := line.substr(0, clampi(left, 0, line.length()))
		left -= line.length()
		font.draw(self, Vector2(r.position.x + 8, y), vis, C_TEXT, C_INK)
		y += 10
	if ch_n > 0:
		y += 3
		for i in ch_n:
			var sel := i == dlg_sel
			if sel:
				var bob := 1 if fmod(t, 0.5) < 0.25 else 0
				_tri_right(Vector2i(r.position.x + 10 + bob, y + 1), C_LAMP)
			for line in choice_rows[i]:
				font.draw(self, Vector2(r.position.x + 18, y), line, C_LAMP if sel else C_DIM, C_INK)
				y += 10
	elif not is_typing() and fmod(t, 0.7) < 0.45:
		_tri_down(Vector2i(r.end.x - 13, r.end.y - 9), C_LAMP)

func _tri_right(p: Vector2i, c: Color) -> void:
	for i in 4:
		draw_rect(Rect2(p.x + i, p.y + i, 1, 7 - 2 * i), c)

func _tri_down(p: Vector2i, c: Color) -> void:
	for i in 3:
		draw_rect(Rect2(p.x + i, p.y + i, 5 - 2 * i, 1), c)

func _draw_inventory() -> void:
	var n := inv_items.size()
	var slot := 18
	var gap := 2
	var total := n * slot + (n - 1) * gap
	var k := inv_slide * inv_slide * (3.0 - 2.0 * inv_slide)
	var y := int(lerpf(-slot - 4, 8, k))
	var x0 := (W - total) / 2
	for i in n:
		var it: Dictionary = inv_items[i]
		var r := Rect2i(x0 + i * (slot + gap), y, slot, slot)
		_frame(r)
		var hi: bool = (inv_open and i == inv_sel) or (it.id == inv_flash_id and inv_show > 1.2 and fmod(t, 0.3) < 0.18)
		if hi:
			draw_rect(Rect2(r.position.x + 1, r.position.y + 1, slot - 2, 1), C_LAMP)
			draw_rect(Rect2(r.position.x + 1, r.end.y - 2, slot - 2, 1), C_LAMP)
			draw_rect(Rect2(r.position.x + 1, r.position.y + 1, 1, slot - 2), C_LAMP)
			draw_rect(Rect2(r.end.x - 2, r.position.y + 1, 1, slot - 2), C_LAMP)
		var tex: Texture2D = item_icons.get(it.icon, null)
		if tex:
			draw_texture(tex, Vector2(r.position.x + 3, r.position.y + 3))
	if inv_open and inv_sel < n:
		var nm: String = inv_items[inv_sel].name
		font.draw(self, Vector2((W - font.measure(nm)) / 2, y + slot + 4), nm, C_TEXT, C_INK)
	elif inv_show > 0.0 and inv_flash_id != "":
		for it in inv_items:
			if it.id == inv_flash_id:
				font.draw(self, Vector2((W - font.measure(it.name)) / 2, y + slot + 4), it.name, C_TEXT, C_INK)

func _draw_ending() -> void:
	var a := ending_a
	draw_rect(Rect2(0, 0, W, H), Color(0, 0, 0, 1))
	var tw: int = font.measure(ending_title)
	font.draw(self, Vector2((W - tw) / 2, 92), ending_title, Color(C_LAMP, a), Color(0, 0, 0, 0))
	draw_rect(Rect2((W - tw) / 2, 104, tw, 1), Color(C_BONE, a * 0.6))
	var lines: PackedStringArray = font.wrap(ending_text, 236)
	var y := 114
	for l in lines:
		font.draw(self, Vector2((W - font.measure(l)) / 2, y), l, Color(C_TEXT, a), Color(0, 0, 0, 0))
		y += 11
