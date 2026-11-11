extends Node3D
## FEEL4 goal cue: the next place to go, shown without text. Presentation only: reads story/module state, writes
## nothing back, never touches physics or replay state.
##   goal   a startable challenge in this room (its start anchor), else the open door on the shortest door path to
##          the nearest room that still holds an uncompleted challenge. None while a challenge runs (enemies remain),
##          while its gate is shut, during scene cards, room transitions, menus, dialogue or pause.
##   look   one marker per room: a pulsing floor ring (the combat telegraph decal, shaders/n64_marker.gdshader) and a
##          soft vertical light beam at the goal, plus a short trail of floor dots along the navigation route from the
##          player (hidden near the goal). When a challenge completes the same marker blooms once at the new goal.
## Data: game.metadata.presentation.goal_cue = {"enabled": bool, "color": "#rrggbb"}. Default ON for arena_run_v1 /
## premise games, OFF for every other game (older games render exactly as before).
const MARKER = preload("res://shaders/n64_marker.gdshader")
const DEFAULT_COLOR := Color("ffd27a")
const RING_M := 1.25
const BEAM_HEIGHT_M := 7.0
const TRAIL_DOTS := 7
const TRAIL_STEP_M := 0.9
const TRAIL_HIDE_M := 2.6
const BLOOM_TICKS := 54
var view
var color := DEFAULT_COLOR
var goal := {}
var signature := ""
var completed_count := -1
var tick := 0
var bloom := 0
var ring: MeshInstance3D
var beam: MeshInstance3D
var dots := []
var route := PackedVector3Array()
var route_from := Vector3.INF
var route_room := ""
var shown := false
var log := []   # [tick, goal id] rows when the goal changes (probe evidence)

static func wanted(game: Dictionary) -> bool:
	var meta: Dictionary = game.get("metadata", {})
	var cfg = meta.get("presentation", {}).get("goal_cue", null)
	if cfg is bool: return cfg
	if cfg is Dictionary and cfg.has("enabled"): return bool(cfg.enabled)
	return str(meta.get("template", "")) == "arena_run_v1" or meta.has("premise")

static func install(presenter) -> Node:
	if not wanted(presenter.runtime.game): return null
	var cue = new()
	cue.name = "goal_cue"
	cue.view = presenter
	var cfg = presenter.runtime.game.metadata.get("presentation", {}).get("goal_cue", {})
	if cfg is Dictionary and cfg.has("color"): cue.color = Color(str(cfg.color))
	presenter.world.add_child(cue)
	if presenter.follow_camera != null and presenter.follow_camera.has_method("face_goal"): presenter.follow_camera.face_goal()
	return cue

func _ready() -> void:
	process_physics_priority = 60   # after locomotion, modules and the follow camera
	ring = MeshInstance3D.new()
	ring.name = "goal_ring"
	var quad := QuadMesh.new(); quad.size = Vector2.ONE * RING_M * 2.0; quad.orientation = PlaneMesh.FACE_Y
	ring.mesh = quad
	var m := ShaderMaterial.new(); m.shader = MARKER
	m.set_shader_parameter("shape", 1); m.set_shader_parameter("inner", 0.74); m.set_shader_parameter("progress", 1.0)
	m.set_shader_parameter("color", color); m.set_shader_parameter("edge", 0.1)
	ring.material_override = m
	ring.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(ring)
	beam = MeshInstance3D.new()
	beam.name = "goal_beam"
	var bq := QuadMesh.new(); bq.size = Vector2(0.9, BEAM_HEIGHT_M)
	beam.mesh = bq
	beam.material_override = beam_material()
	beam.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(beam)
	for i in TRAIL_DOTS:
		var dot := MeshInstance3D.new()
		dot.name = "goal_trail_%d" % i
		var dq := QuadMesh.new(); dq.size = Vector2.ONE * 0.34; dq.orientation = PlaneMesh.FACE_Y
		dot.mesh = dq
		var dm := ShaderMaterial.new(); dm.shader = MARKER
		dm.set_shader_parameter("shape", 0); dm.set_shader_parameter("progress", 1.0); dm.set_shader_parameter("color", color)
		dot.material_override = dm
		dot.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(dot)
		dots.append(dot)
	set_shown(false)

func beam_material() -> StandardMaterial3D:
	var g := Gradient.new()
	g.set_color(0, Color(color, 0.0)); g.set_color(1, Color(color, 0.0))
	g.add_point(0.1, Color(color, 0.55)); g.add_point(0.55, Color(color, 0.18))
	var tex := GradientTexture2D.new()
	tex.gradient = g; tex.fill_from = Vector2(0, 1); tex.fill_to = Vector2(0, 0); tex.width = 4; tex.height = 64
	var mat := StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	mat.billboard_mode = BaseMaterial3D.BILLBOARD_FIXED_Y
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.no_depth_test = false
	mat.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	mat.disable_fog = true
	mat.albedo_texture = tex
	return mat

func set_shown(value: bool) -> void:
	shown = value
	ring.visible = value
	beam.visible = value
	if not value:
		for dot in dots: dot.visible = false

func blocked() -> bool:
	if view.room_root == null or view.runtime == null: return true
	if view.room_transition != null and view.room_transition.active(): return true
	if view.scene_cards != null and str(view.scene_cards.phase) != "idle": return true
	if view.menu_open or view.dialogue_active() or view.belt.settings_open or view.n64_ui.inv_open: return true
	if view.module_host != null and (view.module_host.active_id != "" or not view.module_host.pending.is_empty()): return true
	return str(view.runtime.state.get("modules", {}).get("active", "")) != ""

## The goal for the current state (see header). Pure read.
func find_goal() -> Dictionary:
	var runtime = view.runtime
	var here: String = runtime.state.location
	var available := {}
	for a in runtime.actions(runtime.state): available[a.id] = a
	if runtime.modules == null: return {}
	var completed: Array = runtime.state.modules.get("completed", [])
	for id in available:
		if str(id).begins_with("challenge:start:"):
			var cid := str(id).trim_prefix("challenge:start:")
			if runtime.modules.challenges.has(cid) and runtime.modules.challenges[cid].room == here and not completed.has(cid):
				var at: Vector3 = view.module_host.anchor(id) if view.module_host != null else Vector3.INF
				if at != Vector3.INF: return {"id": id, "kind": "challenge", "at": at}
	var targets := {}
	for c in runtime.modules.challenges.values():
		if not completed.has(c.id) and c.room != here: targets[c.room] = true
	if targets.is_empty(): return {}
	# Breadth-first over door links (gated or not) from this room; the first door of the shortest path is the goal
	# only when its move action is open now.
	var first := {}
	var seen := {here: true}
	var frontier := [here]
	while not frontier.is_empty():
		var next := []
		for room_id in frontier:
			for door in runtime.rooms[room_id].get("doors", []):
				var to := str(door.get("to_room", door.get("to", "")))
				if to == "" or seen.has(to): continue
				seen[to] = true
				first[to] = first.get(room_id, "move:%s:%s" % [here, door.id]) if room_id != here else "move:%s:%s" % [here, door.id]
				if targets.has(to):
					var id: String = first[to]
					if not available.has(id): return {}
					var at = view.room_root.target_positions.get(id, null)
					return {"id": id, "kind": "door", "at": at} if at is Vector3 else {}
				next.append(to)
		frontier = next
	return {}

func _physics_process(_delta: float) -> void:
	if view == null: return
	tick += 1
	var runtime = view.runtime
	var completed: int = runtime.state.get("modules", {}).get("completed", []).size() if runtime != null else 0
	var sig := "%s|%s|%d|%d" % [runtime.state.location if runtime != null else "", str(runtime.state.get("modules", {}).get("active", "")) if runtime != null else "", completed, view.ui_actions.size()]
	if sig != signature or tick % 30 == 0:
		signature = sig
		var before := str(goal.get("id", ""))
		goal = {} if runtime == null else find_goal()
		if completed_count >= 0 and completed > completed_count and not goal.is_empty(): bloom = BLOOM_TICKS
		completed_count = completed
		if str(goal.get("id", "")) != before: log.append([view.actions.tick if view.actions != null else tick, str(goal.get("id", ""))])
	if goal.is_empty() or blocked():
		set_shown(false)
		return
	if not shown: set_shown(true)
	present_goal()

func present_goal() -> void:
	var at: Vector3 = goal.at
	var pulse := 0.5 + 0.5 * sin(TAU * float(tick) / 72.0)
	var k := float(bloom) / float(BLOOM_TICKS)
	if bloom > 0: bloom -= 1
	ring.global_position = Vector3(at.x, 0.035, at.z)
	var grow := 1.0 + 0.06 * pulse + 0.5 * sin(PI * (1.0 - k)) * float(k > 0.0)   # bloom: 1 -> 1.5 -> 1
	ring.scale = Vector3.ONE * grow
	var rm: ShaderMaterial = ring.material_override
	rm.set_shader_parameter("alpha", clampf(0.42 + 0.3 * pulse + 0.4 * k, 0.0, 1.0))
	beam.global_position = Vector3(at.x, BEAM_HEIGHT_M * 0.5, at.z)
	var bm: StandardMaterial3D = beam.material_override
	bm.albedo_color = Color(1, 1, 1, clampf(0.55 + 0.25 * pulse + 0.45 * k, 0.0, 1.0))
	update_trail(at)

func update_trail(at: Vector3) -> void:
	var player: Vector3 = view.player.position
	var flat_d := Vector2(player.x - at.x, player.z - at.z).length()
	if flat_d < TRAIL_HIDE_M:
		for dot in dots: dot.visible = false
		return
	var room_id: String = view.runtime.state.location
	if route_room != room_id or route_from == Vector3.INF or route_from.distance_to(player) > 0.6:
		route_room = room_id
		route_from = player
		# The player's own per-room grid (configured in place_in_room from the same solids and boundary).
		var nav = view.player.room_navigation
		route = nav.route(player, at, 0.9, false) if nav != null else PackedVector3Array()
		if route.is_empty(): route = PackedVector3Array([at])
		else: route.append(at)
	# Walk the route polyline from the player, placing dots every TRAIL_STEP_M after a 1.0 m gap.
	var points := PackedVector3Array([player]); points.append_array(route)
	var want := 1.0
	var placed := 0
	var travelled := 0.0
	for i in range(1, points.size()):
		var a: Vector3 = points[i - 1]; var b: Vector3 = points[i]
		var seg := Vector2(b.x - a.x, b.z - a.z).length()
		while placed < TRAIL_DOTS and travelled + seg >= want:
			var t := (want - travelled) / maxf(seg, 0.0001)
			var p := a.lerp(b, t)
			if Vector2(p.x - at.x, p.z - at.z).length() < RING_M + 0.2: break
			var dot: MeshInstance3D = dots[placed]
			dot.visible = true
			dot.global_position = Vector3(p.x, 0.03, p.z)
			# A soft wave runs from the player toward the goal; dots fade with distance along the trail.
			var wave := 0.5 + 0.5 * sin(TAU * (float(tick) / 48.0 - float(placed) * 0.14))
			var dm: ShaderMaterial = dot.material_override
			dm.set_shader_parameter("alpha", clampf((0.28 + 0.42 * wave) * (1.0 - float(placed) / float(TRAIL_DOTS + 2)), 0.0, 1.0))
			placed += 1
			want += TRAIL_STEP_M
		travelled += seg
	for i in range(placed, TRAIL_DOTS): dots[i].visible = false

## Probe/report view of the cue (no side effects).
func report() -> Dictionary:
	var visible_dots := 0
	for dot in dots: if dot.visible: visible_dots += 1
	return {"shown": shown, "goal": str(goal.get("id", "")), "kind": str(goal.get("kind", "")),
		"at": [goal.at.x, goal.at.y, goal.at.z] if goal.get("at") is Vector3 else null, "trail_dots": visible_dots, "bloom": bloom, "log": log}
