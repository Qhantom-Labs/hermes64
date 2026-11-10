extends Control
## Glyphs/numerals only during play; placeholder annotation is an evidence label.
## COMBAT lane: positions are unprojected through the camera actually drawing the frame (the combat camera while it
## is blended in); the "safe to dodge now" glyph (a small diamond, no text) sits over a telegraphing enemy while a roll
## pressed now would keep its i-frames over the hit; a hurt shows a thin frame-edge flash; a boss shows one pixel bar.
var host
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
func view_camera() -> Camera3D:
	if host.combat_camera != null:
		var c = host.combat_camera.current()
		if c != null and is_instance_valid(c): return c
	return host.presenter.camera
func on_screen(cam: Camera3D, at: Vector3):
	if cam == null or cam.is_position_behind(at): return null
	return cam.unproject_position(at)
func _draw() -> void:
	if host == null: return
	var font = preload("res://look/pixel_font.gd").get_font()
	var ui = host.presenter.n64_ui
	var cam := view_camera()
	if host.combat != null:
		# Dialogue/menu location and counters use rows 8 and 18. Keep health on a
		# separate row while that panel is up, at every aspect ratio.
		var health_y := 30 if ui.dlg_on else 8
		for i in host.combat.max_health:
			if host.combat.modern():
				draw_rect(Rect2(7 + i * 11, health_y - 1, 10, 10), Color("151822"))
				draw_rect(Rect2(8 + i * 11, health_y, 8, 8), ui.C_LAMP if i < host.combat.health else ui.C_DIM)
			else: draw_rect(Rect2(8 + i * 5, health_y, 3, 6), ui.C_LAMP if i < host.combat.health else ui.C_DIM)
		if host.animation.placeholder: font.draw(self, Vector2(8,health_y+12), "POSE TEST", ui.C_LAMP)
		var enemy = host.combat.find_target(host.combat.target)
		if enemy != null:
			if host.combat.modern(): focus_ring(cam, enemy, ui.C_LAMP)
			var at = on_screen(cam, enemy.body.position + Vector3.UP * 1.5 * (enemy.visual.scale.y if enemy.visual != null and is_instance_valid(enemy.visual) else 1.0))
			if at != null:
				draw_line(at + Vector2(-4,-2), at + Vector2(0,2), ui.C_LAMP, 1)
				draw_line(at + Vector2(0,2), at + Vector2(4,-2), ui.C_LAMP, 1)
		boss_bar(ui)
	if host.stage != null:
		var glyph_col: Color = Color.from_string(str(host.stage.profile.get("telegraph", {}).get("glyph_color", "#e6f0f8")), Color(0.9, 0.94, 0.97))
		for g in host.stage.glyphs:
			var at = on_screen(cam, g.at)
			if at != null: dodge_glyph(Vector2(roundf(at.x) + 7, roundf(at.y) - 2), glyph_col)
	if host.course != null:
		var c = host.course
		var ticks: int = c.countdown if c.countdown > 0 else c.elapsed
		var edge: float = get_viewport_rect().size.x
		font.draw(self, Vector2(edge-78,8), "%02d:%02d" % [ticks / 60, (ticks % 60) * 100 / 60], ui.C_LAMP)
		font.draw(self, Vector2(edge-52,20), "%d/%d" % [c.history.size(), c.track.checkpoints.size()], ui.C_TEXT)
		font.draw(self, Vector2(edge-78,32), "/%02d:%02d" % [c.track.par_ticks / 60, (c.track.par_ticks % 60)*100/60], ui.C_DIM)
	if host.run.enabled: run_clock(font, ui)
	if host.retry_ticks > 0:
		if host.run.enabled: draw_rect(Rect2(0,0,get_viewport_rect().size.x,240), Color(0,0,0,0.33))
		draw_texture_rect(ui.icons.save, Rect2((get_viewport_rect().size.x-16)/2,104,16,16), false, ui.C_LAMP)
	edge_flash()
	if not host.pending.is_empty(): draw_rect(Rect2(0,0,get_viewport_rect().size.x,240), Color(0,0,0,0.55))
## Diamond with a centre dot over a 1-px dark drop shadow (reads on bright and dark floors alike).
func dodge_glyph(at: Vector2, col: Color) -> void:
	var shade := Color(0.02, 0.03, 0.06, 0.8)
	for pass_i in 2:
		var o := Vector2(1, 1) if pass_i == 0 else Vector2.ZERO
		var c := shade if pass_i == 0 else col
		var pts := [at + o + Vector2(0, -4), at + o + Vector2(4, 0), at + o + Vector2(0, 4), at + o + Vector2(-4, 0)]
		for i in 4: draw_line(pts[i], pts[(i + 1) % 4], c, 1)
		draw_rect(Rect2(at + o + Vector2(-1, -1), Vector2(2, 2)), c)
## A hurt (player hit) flashes a thin frame edge for feedback.edge_flash_ticks ticks, fading; never full-screen.
func edge_flash() -> void:
	if host.stage == null or host.stage.edge_ticks <= 0: return
	var fb: Dictionary = host.stage.profile.get("feedback", {})
	var n := maxi(1, int(fb.get("edge_flash_ticks", 8)))
	var k := float(host.stage.edge_ticks) / float(n)
	var col := Color.from_string(str(fb.get("edge_color", "#c8582c")), Color(0.8, 0.35, 0.18))
	col.a = float(fb.get("edge_alpha", 0.55)) * k
	var px := float(fb.get("edge_px", 3))
	draw_rect(Rect2(0, 0, get_viewport_rect().size.x, px), col)
	draw_rect(Rect2(0, 240 - px, get_viewport_rect().size.x, px), col)
	draw_rect(Rect2(0, px, px, 240 - 2 * px), col)
	draw_rect(Rect2(get_viewport_rect().size.x - px, px, px, 240 - 2 * px), col)
## One pixel bar for a live boss (bottom centre): fill = health, notches = phase thresholds. No text.
func run_clock(font, ui) -> void:
	var r = host.run; var x := get_viewport_rect().size.x - 96
	font.draw(self, Vector2(x,8), "%02d:%02d.%02d" % [r.ticks / 3600, (r.ticks / 60) % 60, (r.ticks % 60) * 100 / 60], ui.C_LAMP if r.penalty_flash == 0 else ui.C_TEXT)
	if r.penalty_flash > 60:
		var ticks: int = r.rules.get("death_penalty_ticks", 0)
		font.draw(self, Vector2(x+24,21), "+%d.%02d" % [ticks / 60, (ticks % 60) * 100 / 60], ui.C_TEXT)
	if r.checkpoint_flash > 0 and (r.checkpoint_flash % 30) >= 15: dodge_glyph(Vector2(x-10,12), ui.C_LAMP)
func focus_ring(cam: Camera3D, enemy, col: Color) -> void:
	for i in 20:
		var a := float(i) * TAU / 20.0; var b := float(i+1) * TAU / 20.0
		var at: Vector3 = enemy.body.position + Vector3.UP * 0.03
		var p = on_screen(cam, at + Vector3(cos(a),0,sin(a)) * 0.65)
		var q = on_screen(cam, at + Vector3(cos(b),0,sin(b)) * 0.65)
		if p != null and q != null: draw_line(p,q,col,1)
func boss_bar(ui) -> void:
	if host.combat.modern():
		var ids: Array = host.combat.encounter.get("bosses", [host.combat.encounter.get("boss", "")])
		var colors := [ui.C_LAMP, Color("86b8d8"), Color("b398d0")]
		for i in ids.size():
			var e = host.combat.find_target(ids[i])
			var x := (get_viewport_rect().size.x-160.0)/2.0; var y := 212.0 + i*7
			draw_rect(Rect2(x-1,y-1,162,6),Color("151822"))
			draw_rect(Rect2(x,y,160,4),ui.C_DIM)
			if e != null: draw_rect(Rect2(x,y,roundf(160.0*e.hp/e.data.max_health),4),colors[i%3])
		return
	var boss = host.combat.boss() if host.combat.has_method("boss") else null
	if boss == null: return
	var x := (get_viewport_rect().size.x-160.0)/2.0
	var y := 224.0
	var w := 160.0
	draw_rect(Rect2(x - 1, y - 1, w + 2, 6), Color(0.02, 0.03, 0.06, 0.85))
	draw_rect(Rect2(x, y, w, 4), ui.C_DIM)
	var frac := clampf(float(boss.hp) / float(maxi(1, boss.data.max_health)), 0.0, 1.0)
	draw_rect(Rect2(x, y, roundf(w * frac), 4), ui.C_LAMP)
	for t in boss.phase_marks():
		var nx := roundf(x + w * float(t))
		draw_rect(Rect2(nx, y - 1, 1, 6), Color(0.02, 0.03, 0.06, 0.9))
