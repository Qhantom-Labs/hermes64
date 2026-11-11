extends Control
## Original geometric glyphs, authored for this project. CC0-1.0; no controller art.
var presenter
const OVERLAY_ACTIONS := ["move_up","move_left","move_down","move_right","walk","primary","secondary","focus","dodge","run"]
const Glyphs := {
	"door":["#####","#...#","#..##","#...#","#####"],
	"talk":["#####","#...#","#####",".#...","#...."],
	"take":["..#..",".###.","#####","..#..","..#.."],
	"look":[".....",".###.","#.#.#",".###.","....."],
	"use":["#...#",".#.#.","..#..",".#.#.","#...#"],
	"climb":["#.#..","###..","#.#..","###..","#.#.."],
	"attack":["....#","...#.","#.#..",".##..","#..#."],
	"save":["#####","##.##","#...#","#.###","#####"],
	"pause":["##.##","##.##","##.##","##.##","##.##"],
	"play":["#....","###..","#####","###..","#...."],
	"focus":["##.##","#...#","..#..","#...#","##.##"],
	"walk":[".#...",".##..","..#..",".#.#.","#...#"],
	"run":["...#.",".###.","..#..","##.#.","...##"],
	"load":["..#..","..#..","#####",".###.","..#.."],
	"motion":["#.#.#",".....","#.#.#",".....","#.#.#"]
}
func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	size = Vector2(320,240)
func glyph(at: Vector2, kind: String, color: Color) -> void:
	var rows: Array = Glyphs.get(kind,Glyphs.look)
	for y in rows.size():
		for x in rows[y].length():
			if rows[y][x] == "#": draw_rect(Rect2(at+Vector2(x,y),Vector2.ONE),color)
func key(at: Vector2, text: String, color: Color) -> void:
	var font = presenter.n64_ui.font
	var width: float = font.measure(text)+4
	draw_rect(Rect2(at-Vector2(2,2),Vector2(width,11)),Color(0.03,0.04,0.06,0.85*color.a))
	draw_rect(Rect2(at-Vector2(2,2),Vector2(width,11)),color,false)
	font.draw(self,at,text,color,Color.TRANSPARENT)
func _draw() -> void:
	if presenter == null or presenter.n64_ui == null: return
	var view = presenter
	var W: int = view.viewport.size.x
	size = view.viewport.size
	var color: Color = view.n64_ui.C_LAMP
	var font = view.n64_ui.font
	if view.belt.settings_open:
		pass # UI5: the pause menu is drawn by input/key_overlay.gd at an integer pixel scale (rows: keyhud.json).
	elif not view.menu_open and not view.dialogue_active() and not view.n64_ui.inv_open and (view.key_overlay == null or view.key_overlay.prompt_mode == "legacy"):
		var c: Dictionary = view.current_candidate
		var cam: Camera3D = view.drawing_camera()
		if not c.is_empty() and cam != null and not cam.is_position_behind(c.position):
			var at: Vector2 = cam.unproject_position(c.position+Vector3(0,0.9,0))
			draw_set_transform(Vector2.ZERO)
			at = at.clamp(Vector2(18,16),Vector2(W-40,222)).round()
			var tint := Color(color,view.contextual.alpha)
			key(at,view.actions.binding_glyph("primary"),tint)
			glyph(at+Vector2(25,1),c.icon,tint)
			if view.focus_id != "": glyph(at+Vector2(34,1),"focus",color)
	draw_set_transform(Vector2.ZERO)
	if view.belt.checkpoint_ticks > 0: glyph(Vector2(W-18,10),"save",color)
	if view.belt.enabled and view.belt.input_overlay:
		var x := 8.0
		for action in OVERLAY_ACTIONS:
			if view.actions.is_pressed(action):
				key(Vector2(x,220),view.actions.binding_glyph(action),color); x += 26
	if view.belt.enabled and view.belt.perf_overlay:
		font.draw(self,Vector2(8,8),"%d fps / %d draw" % [Engine.get_frames_per_second(),Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)],color,Color.BLACK)
		font.draw(self,Vector2(8,18),"%d tick / %.2f ms" % [view.belt.sim_tick,Performance.get_monitor(Performance.TIME_PHYSICS_PROCESS)*1000.0],color,Color.BLACK)
