extends Node
## SCENES lane: data-driven scene cards, travel shots, wave labels and the results card.
## Data: `metadata.presentation.scenes` and `metadata.presentation.results` (docs/SCENES.md).
##
## Presentation only. While a card shows, the canonical pipeline (presenter, Actions,
## player, Movie, module host, follow camera, actor bridge) is frozen with
## set_physics_process(false) at a tick boundary, the same barrier the FEEL2 room
## envelope uses: no movie frame, Action tick, run-clock tick or module tick passes, so
## a movie replays identically with scenes on, off, watched or skipped. A request made
## inside a fixed tick (ending, module event) is started from this node's tail at
## physics priority 210, after Movie (100) recorded that tick. Scene rooms are built in
## a private SubViewport/World3D (own physics space); the live room is never touched.
signal scene_started(id: String)
signal scene_finished(id: String, skipped: bool)
signal results_shown(receipt: Dictionary)
signal travel_done()
const PixelFont = preload("res://look/pixel_font.gd")
const Pack = preload("res://look/pack.gd")
const Room = preload("res://view/room.gd")
const RunSource = preload("res://view/run_source.gd")
const BestStore = preload("res://view/best_store.gd")
const Results = preload("res://view/results_card.gd")
const H := 240
const MAX_HOLD_TICKS := 1800
const MAX_CARDS := 16
# Same timings as view/room_transition.gd, so cuts into and out of scenes match doors.
const OUT_SECONDS := 0.22
const IN_SECONDS := 0.18
const QUICK_SECONDS := 0.06
const LABEL_SECONDS := 1.5
const LETTERBOX := 18
const SHOTS := ["cut", "hold", "push", "pan", "orbit", "track"]
const TRIGGERS := ["start", "door", "enter", "event", "ending"]

class Canvas extends Control:
	var director
	func _draw() -> void:
		if director != null: director.draw_overlay(self)

var view
var canvas: Canvas
var enabled := true
var scenes := []
var results_cfg := {}
var played := {}
var queue := []
var pending := []
var pending_results := false
var results_wanted := false
var end_tick := -1
var started := false
var scene := {}
var card := {}
var card_index := -1
var card_time := 0.0
var card_hold := 1.0
var in_travel := false
var phase := "idle"
var elapsed := 0.0
var fade := 0.0
var fade_kind := "fade"
var skipped := false
var reduced := false
var frozen := false
var gates := []
var hud_gates := []
var stage: SubViewport
var stage_world: Node3D
var stage_env: WorldEnvironment
var stage_cam: Camera3D
var stage_room
var stage_actors := []
var shot := {}
var label_text := ""
var label_left := 0.0
var results
var results_armed := false
var results_receipt := {}
var receipts := []
var receipt_row := {}
var cue_log := []
var watchdog := []
var fault := ""
var best_path := BestStore.DEFAULT_PATH
var again_handler: Callable
var _width := 320

# ------------------------------------------------------------------ setup
func attach(presenter) -> void:
	view = presenter
	name = "scene_director"
	process_physics_priority = 210
	var pres = view.runtime.game.metadata.get("presentation", {})
	if pres is Dictionary:
		if pres.get("scenes") is Array: scenes = (pres.scenes as Array).duplicate(true)
		if pres.get("results") is Dictionary: results_cfg = (pres.results as Dictionary).duplicate(true)
	enabled = str(view.options.get("scenes", "on")) != "off"
	fault = str(view.options.get("scenes_fault", ""))
	best_path = str(view.options.get("best_store", BestStore.DEFAULT_PATH))
	canvas = Canvas.new()
	canvas.name = "scene_cards"
	canvas.director = self
	canvas.mouse_filter = Control.MOUSE_FILTER_IGNORE
	canvas.focus_mode = Control.FOCUS_NONE
	canvas.z_index = 110
	canvas.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	view.viewport.add_child(canvas)
	set_width(view.viewport.size.x)
	view.ending_reached.connect(on_ending)
	if view.module_host != null: view.module_host.story_event.connect(on_module_event)
	again_handler = func(): get_tree().call_deferred("reload_current_scene")

func set_width(width: int) -> void:
	_width = maxi(240, width)
	if canvas != null: canvas.size = Vector2(_width, H); canvas.queue_redraw()
	if stage != null: stage.size = Vector2i(_width, H)

func results_enabled() -> bool:
	return bool(results_cfg.get("enabled", not results_cfg.is_empty()))

static func trig(row: Dictionary) -> Dictionary:
	return row.get("trigger", {}) if row.get("trigger") is Dictionary else {}

func active() -> bool:
	return phase != "idle"

func blocking() -> bool:
	return frozen or phase != "idle"

# ------------------------------------------------------------------ triggers
func _process(delta: float) -> void:
	if view == null or view.runtime == null: return
	if canvas != null and canvas.size.x != view.viewport.size.x: set_width(view.viewport.size.x)
	if not started:
		started = true
		begin_session()
	if label_left > 0.0:
		label_left = maxf(0.0, label_left - delta)
		canvas.queue_redraw()
	if phase != "idle": advance(delta)
	# Read-only browser receipt for real-key tests; no input or state is read back from it.
	if OS.has_feature("web") and Engine.get_process_frames() - _published >= 10: publish()

func begin_session() -> void:
	# The run code is the hash of the input movie, so a results game records one from
	# boot in live play. Recording reads state only; replays and bots are untouched.
	if results_enabled() and view.replay != null and not view.replay.recording and not view.replay.playing and view.actions.source == "live":
		view.replay.start_record(str(view.options.get("run_movie", "user://replays/last-run.h64movie.json")), int(str(view.options.get("seed", "7"))))
	for row in scenes:
		if trig(row).get("on") == "start": request(row)

func request(row: Dictionary) -> void:
	if not enabled: return
	var id := str(row.get("id", ""))
	if bool(row.get("once", true)) and played.has(id): return
	played[id] = true
	if Engine.is_in_physics_frame() and fault != "freeze_now":
		pending.append(row)
		return
	start_or_queue(row)

func start_or_queue(row: Dictionary) -> void:
	if phase != "idle" or (view.room_transition != null and view.room_transition.active()):
		queue.append(row)
		return
	begin(row, false, false)

## Tail of every fixed tick (priority 210, after Movie 100): start requests made in it.
func _physics_process(_delta: float) -> void:
	if view == null: return
	if str(results_cfg.get("on", "ending")) == "run_finished" and not results_wanted and results == null and results_enabled():
		var r := RunSource.read(view, view.actions.tick)
		if r.source == "combat2_run" and r.finished: on_ending("")
	if pending.is_empty() and not pending_results: return
	var rows := pending
	pending = []
	for row in rows: start_or_queue(row)
	if pending_results and phase == "idle" and queue.is_empty():
		pending_results = false
		show_results()

## Presenter hook: the doorway envelope finished and input is released.
func room_ready(room_id: String) -> void:
	if not queue.is_empty() and phase == "idle":
		begin(queue.pop_front(), false, false)
	for row in scenes:
		var t := trig(row)
		if t.get("on") == "enter" and str(t.get("room", "")) == room_id: request(row)

## Presenter hook at the doorway black: a travel scene plays inside the black hold,
## then the envelope's own reveal (name card, 0.18 s fade) continues as before.
func travel(action_id: String) -> void:
	if not enabled or not action_id.begins_with("move:") or phase != "idle": return
	var from := action_id.get_slice(":", 1)
	var to: String = view.runtime.state.location
	for row in scenes:
		var t := trig(row)
		if t.get("on") != "door" or str(t.get("from", "")) != from or str(t.get("to", "")) != to: continue
		if bool(row.get("once", true)) and played.has(str(row.get("id", ""))): continue
		played[str(row.get("id", ""))] = true
		begin(row, true, true)
		await travel_done
		return

func on_ending(ending_id: String) -> void:
	if results_wanted or results != null: return
	end_tick = int(view.actions.tick)
	results_wanted = results_enabled()
	for row in scenes:
		var t := trig(row)
		if t.get("on") == "ending" and str(t.get("ending", ending_id)) == ending_id: request(row)
	if not results_wanted: return
	if Engine.is_in_physics_frame() and fault != "freeze_now": pending_results = true
	elif phase == "idle" and queue.is_empty(): show_results()

func on_module_event(kind: String, payload: Dictionary) -> void:
	if kind == "challenge_started": show_label(label_for(str(payload.get("challenge", ""))))
	for row in scenes:
		var t := trig(row)
		if t.get("on") != "event" or str(t.get("kind", "")) != kind: continue
		if t.has("challenge") and str(t.challenge) != str(payload.get("challenge", "")): continue
		request(row)

## Wave label consumer: `encounter.label` (combat 1.2.0) or the challenge's own label.
func label_for(challenge_id: String) -> String:
	var mods = view.runtime.get("modules")
	if mods == null or challenge_id == "": return ""
	var c = mods.challenges.get(challenge_id, {}) if mods.get("challenges") is Dictionary else {}
	if not c is Dictionary: return ""
	var label := str(c.get("label", ""))
	if str(c.get("kind", "")) == "combat" and c.has("subject"):
		var encounters = mods.entities("combat", "encounters")
		if encounters is Dictionary and encounters.get(c.subject) is Dictionary:
			label = str(encounters[c.subject].get("label", label))
	return label

func show_label(text: String) -> void:
	text = text.replace("\n", " ").replace("	", " ").strip_edges()   # authored spacing kept
	if text == "": return
	label_text = text
	label_left = LABEL_SECONDS
	canvas.queue_redraw()
	publish()

# ------------------------------------------------------------------ freeze barrier
func freeze() -> void:
	if frozen or fault == "no_freeze": return
	frozen = true
	gates = []
	var nodes: Array = [view, view.actions, view.player, view.replay, view.module_host, view.follow_camera]
	for child in view.get_children():
		if child.get_script() != null and child.get_script().resource_path.ends_with("actors/bridge.gd"): nodes.append(child)
	for node in nodes:
		if is_instance_valid(node):
			gates.append([node, node.is_physics_processing()])
			node.set_physics_process(false)
	hud_gates = []
	for hud in [view.n64_ui, view.controls_hud, view.module_host.hud if view.module_host != null else null]:
		if is_instance_valid(hud): hud_gates.append([hud, hud.visible]); hud.visible = false

## The Actions autoload outlives the presenter (AGAIN reloads the scene): never leave it frozen.
func _exit_tree() -> void:
	if frozen: unfreeze()

func unfreeze() -> void:
	for gate in gates:
		if is_instance_valid(gate[0]): gate[0].set_physics_process(gate[1])
	gates = []
	for gate in hud_gates:
		if is_instance_valid(gate[0]): gate[0].visible = gate[1]
	hud_gates = []
	frozen = false

## Live play resumes only after every key/button is released, so the key that skipped a
## scene never becomes a jump or an action. Bots and replays have no physical input.
func released() -> bool:
	if view.actions.source != "live": return true
	var raw: Dictionary = view.actions.sample_live()
	for key in ["digital", "buttons"]:
		if not (raw.get(key, []) as Array).is_empty(): return false
	var dz := float(view.actions.profile.tuning.get("dead_zone_pad", 0.18))
	for key in ["analog", "camera"]:
		var a = raw.get(key, [0, 0])
		if a is Array and a.size() == 2 and Vector2(float(a[0]), float(a[1])).length() > dz: return false
	return true

# ------------------------------------------------------------------ scene timeline
func out_seconds() -> float: return QUICK_SECONDS if reduced else OUT_SECONDS
func in_seconds() -> float: return QUICK_SECONDS if reduced else IN_SECONDS

func set_phase(value: String) -> void:
	phase = value
	elapsed = 0.0
	canvas.queue_redraw()
	publish()

func begin(row: Dictionary, is_travel: bool, at_black: bool) -> void:
	scene = row
	in_travel = is_travel
	skipped = false
	card_index = -1
	reduced = bool(view.actions.profile.options.get("reduced_motion", false))
	if not in_travel: freeze()
	receipt_row = {"id":str(row.get("id", "")),"trigger":str(trig(row).get("on", "")),"travel":in_travel,"reduced":reduced,
		"tick_start":int(view.actions.tick),"cursor_start":int(view.replay.cursor) if view.replay != null else -1,"cards":0,"skipped":false}
	ensure_stage()
	stage.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var music := str(row.get("music", ""))
	if music != "": cue("music", music)
	scene_started.emit(receipt_row.id)
	fade_kind = transition_kind(str(row.get("transition_in", "fade")))
	if at_black:
		fade = 1.0
		next_card()
	elif str(row.get("transition_in", "fade")) == "cut":
		fade = 0.0
		next_card()
	else:
		fade = 0.0
		set_phase("lead_out")

func transition_kind(value: String) -> String:
	if reduced: return "fade"
	return "iris" if value == "iris" else "fade"

func hold_seconds(c: Dictionary) -> float:
	var v = c.get("hold", 0)
	var ticks := int(v) if (v is int or v is float) and is_finite(float(v)) else 0
	if ticks < 1 or ticks > MAX_HOLD_TICKS:
		# Never-ending or empty card: validation refuses it; the runtime still ends it.
		watchdog.append({"scene":str(scene.get("id", "")),"card":card_index,"hold":str(v)})
		push_error("SCENES watchdog: card hold %s outside 1..%d ticks in scene %s" % [str(v), MAX_HOLD_TICKS, str(scene.get("id", ""))])
		ticks = clampi(ticks, 1, MAX_HOLD_TICKS)
	return float(ticks) / 60.0

func next_card() -> void:
	card_index += 1
	var cards: Array = scene.get("cards", []) if scene.get("cards") is Array else []
	if skipped or card_index >= mini(cards.size(), MAX_CARDS):
		end_scene()
		return
	card = cards[card_index] if cards[card_index] is Dictionary else {}
	setup_card(card)
	receipt_row.cards += 1
	set_phase("card_in" if fade >= 1.0 else "card")

func card_done() -> void:
	var cards: Array = scene.get("cards", [])
	if card_index + 1 < mini(cards.size(), MAX_CARDS) and not skipped:
		var nxt = cards[card_index + 1]
		var kind := str(nxt.get("cut", "cut")) if nxt is Dictionary else "cut"
		if kind == "cut":
			next_card()
			return
		fade_kind = transition_kind(kind)
		set_phase("card_out")
		return
	end_scene()

func end_scene() -> void:
	stop_voice()
	fade_kind = transition_kind(str(scene.get("transition_out", "fade")))
	if str(scene.get("transition_out", "fade")) == "cut" and not in_travel:
		fade = 1.0
		after_tail_out()
		return
	var from := fade
	set_phase("tail_out")
	elapsed = from * out_seconds()

func skip() -> void:
	if skipped or not phase in ["lead_out", "card_in", "card", "card_out"]: return
	skipped = true
	receipt_row.skipped = true
	end_scene()

func after_tail_out() -> void:
	teardown_stage()
	receipt_row["tick_end"] = int(view.actions.tick)
	receipt_row["cursor_end"] = int(view.replay.cursor) if view.replay != null else -1
	receipts.append(receipt_row.duplicate(true))
	scene_finished.emit(str(receipt_row.id), bool(receipt_row.skipped))
	if fault == "teleport" and not in_travel and view.player != null:
		# Known-bad control only: a scene that moves the canonical player desyncs replays.
		view.player.position += Vector3(0.75, 0, 0)
	if in_travel:
		in_travel = false
		scene = {}
		phase = "idle"
		fade = 0.0
		canvas.queue_redraw()
		publish()
		travel_done.emit()
		return
	if not queue.is_empty():
		begin(queue.pop_front(), false, true)
		return
	fade_kind = transition_kind(str(scene.get("transition_out", "fade")))
	set_phase("tail_in")

func advance(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0: return
	match phase:
		"lead_out", "card_out", "tail_out":
			elapsed += delta
			if phase == "card_out": tick_card(delta)
			fade = minf(1.0, elapsed / out_seconds())
			if fade >= 1.0 - 0.0000001:
				fade = 1.0
				if phase == "tail_out": after_tail_out()
				else: next_card()
		"card_in":
			elapsed += delta
			tick_card(delta)
			fade = maxf(0.0, 1.0 - elapsed / in_seconds())
			if fade <= 0.0000001:
				fade = 0.0
				phase = "card"
				publish()
				if card_time >= card_hold and not waits_for_key(): card_done()
		"card":
			tick_card(delta)
			if card_time >= card_hold and not waits_for_key(): card_done()
		"tail_in":
			elapsed += delta
			fade = maxf(0.0, 1.0 - elapsed / in_seconds())
			if fade <= 0.0000001:
				fade = 0.0
				scene = {}
				if results_wanted and queue.is_empty(): show_results()
				else: set_phase("fence")
		"fence":
			if released():
				unfreeze()
				set_phase("idle")
				if not queue.is_empty(): begin(queue.pop_front(), false, false)
		"results":
			if not results_armed and released(): results_armed = true
	canvas.queue_redraw()

func waits_for_key() -> bool:
	return str(card.get("wait", "")) == "key" and view.actions.source == "live"

func tick_card(delta: float) -> void:
	card_time += delta
	update_card_motion()

# ------------------------------------------------------------------ stage (private world)
func ensure_stage() -> void:
	if stage != null: return
	stage = SubViewport.new()
	stage.name = "scene_stage"
	stage.size = Vector2i(_width, H)
	stage.own_world_3d = true
	stage.msaa_3d = view.viewport.msaa_3d
	stage.render_target_update_mode = SubViewport.UPDATE_DISABLED
	add_child(stage)
	stage_world = Node3D.new()
	stage.add_child(stage_world)
	stage_env = WorldEnvironment.new()
	stage_env.environment = view.world_env.environment.duplicate() if view.world_env != null else Environment.new()
	stage_world.add_child(stage_env)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-55, -30, 0)
	stage_world.add_child(light)
	stage_cam = Camera3D.new()
	stage_cam.name = "scene_camera"
	stage_world.add_child(stage_cam)

func build_stage_room(room_id: String) -> void:
	clear_actors()
	if stage_room != null and is_instance_valid(stage_room) and str(stage_room.data.id) == room_id: return
	if stage_room != null and is_instance_valid(stage_room):
		stage_world.remove_child(stage_room)
		stage_room.queue_free()
	stage_room = Room.new()
	stage_room.theme = view.theme
	stage_room.build(view.runtime.rooms[room_id], view.runtime, view.resolver)
	stage_world.add_child(stage_room)
	stage_room.settle()
	stage_room.frame_people()
	stage_room.ensure_accent()
	stage_room.blob_shadows()
	apply_stage_look()
	stage_cam.make_current()

func apply_stage_look() -> void:
	const Rig = preload("res://look/rig.gd")
	if not Rig.has_look(view.theme): return
	if not Rig.has_profile(view.theme, stage_room.profile_name()):
		view.resolver.legacy_globals(0.0)
		stage_env.environment.background_color = Color.from_string(view.theme.fog.color, Color.GRAY)
		return
	stage_room.gather_lights()
	var p: Dictionary = Rig.profile(view.theme, stage_room.profile_name(), stage_room.presentation.get("look", {}))
	if p.has("room") and not (p.room as Dictionary).has("centre"):
		p.room["centre"] = [float(stage_room.data.grid_size[0]) / 2.0, float(stage_room.data.grid_size[1]) / 2.0]
	Rig.apply(p, stage_room.lights)
	stage_env.environment.background_color = Rig.graded(Rig.col(p.get("background", p.get("fog", {}).get("color", view.theme.fog.color))), p)

func clear_actors() -> void:
	for a in stage_actors:
		if a.spawned and is_instance_valid(a.node): a.node.queue_free()
	stage_actors = []

func teardown_stage() -> void:
	clear_actors()
	if stage_room != null and is_instance_valid(stage_room):
		stage_world.remove_child(stage_room)
		stage_room.queue_free()
	stage_room = null
	if stage != null: stage.render_target_update_mode = SubViewport.UPDATE_DISABLED
	# Global look uniforms were set for the scene room; give the live room its look back.
	if view.room_root != null: view.apply_room_look()

static func v3(a, fallback := Vector3.ZERO) -> Vector3:
	if a is Array and a.size() == 3 and a.all(func(n): return (n is int or n is float) and is_finite(float(n))):
		return Vector3(float(a[0]), float(a[1]), float(a[2]))
	return fallback

static func v2(a, fallback := Vector3.ZERO) -> Vector3:
	if a is Array and a.size() == 2 and a.all(func(n): return (n is int or n is float) and is_finite(float(n))):
		return Vector3(float(a[0]), 0.0, float(a[1]))
	return fallback

func setup_card(c: Dictionary) -> void:
	var room_id := str(c.get("room", scene.get("room", view.runtime.state.location)))
	if not view.runtime.rooms.has(room_id):
		watchdog.append({"scene":str(scene.get("id", "")),"card":card_index,"room":room_id})
		room_id = view.runtime.state.location
	build_stage_room(room_id)
	var listed := {}
	for a in (c.get("actors", []) if c.get("actors") is Array else []):
		if not a is Dictionary: continue
		var cid := str(a.get("character", ""))
		if cid == "protagonist": cid = str(view.runtime.game.metadata.get("protagonist", ""))
		listed["actor_" + cid] = true
		var node: Node3D = stage_room.get_node_or_null("actor_" + cid)
		var spawned := false
		if node == null:
			var ch = view.runtime.characters.get(cid, {})
			if (not ch is Dictionary or ch.is_empty()) and view.resolver.has_method("cast_character"): ch = view.resolver.cast_character(cid)
			if not ch is Dictionary or ch.is_empty():
				watchdog.append({"scene":str(scene.get("id", "")),"card":card_index,"character":cid})
				continue
			node = view.resolver.character(ch)
			if node != null: stage_world.add_child(node)
			else: node = stage_room.person(stage_world, ch.get("params", {}))
			spawned = true
		node.visible = true
		var at := v2(a.get("at"), node.position)
		var to := v2(a.get("to"), at)
		var real: bool = node.get_meta("real_character", false)
		var row := {"node":node,"from":at,"to":to,"spawned":spawned,"real":real,
			"clip":str(a.get("clip", "idle")),"moving_clip":str(a.get("moving_clip", "walk")),"yaw":deg_to_rad(float(a.get("yaw", 0.0)))}
		stage_actors.append(row)
		place_actor(row, 1.0 if reduced else 0.0)
	if bool(c.get("cast_only", false)):
		for n in stage_room.get_children():
			if str(n.name).begins_with("actor_") and not listed.has(str(n.name)): n.visible = false
	shot = c.get("shot", {}) if c.get("shot") is Dictionary else {}
	if reduced and c.get("reduced") is Dictionary and c.reduced.get("shot") is Dictionary: shot = c.reduced.shot
	card_time = 0.0
	card_hold = hold_seconds(c)
	var line := str(c.get("voice", ""))
	if line != "": cue("voice", line)
	update_card_motion()

func place_actor(row: Dictionary, t: float) -> void:
	var node: Node3D = row.node
	if not is_instance_valid(node): return
	var moving: bool = row.from.distance_to(row.to) > 0.01
	node.position = row.from.lerp(row.to, clampf(t, 0.0, 1.0))
	if moving:
		var d: Vector3 = row.to - row.from
		node.rotation.y = atan2(d.x, d.z) if row.real else atan2(-d.x, -d.z)
	else:
		node.rotation.y = row.yaw if row.real else row.yaw + PI
	if node.has_method("play_clip"): node.play_clip(row.moving_clip if moving and t < 1.0 else row.clip)

func update_card_motion() -> void:
	if stage_room == null: return
	var t := clampf(card_time / maxf(card_hold, 0.001), 0.0, 1.0)
	if reduced: t = 1.0
	for row in stage_actors: place_actor(row, t)
	var follow := Vector3.ZERO
	var idx := int(shot.get("follow", 0))
	if idx >= 0 and idx < stage_actors.size() and is_instance_valid(stage_actors[idx].node): follow = stage_actors[idx].node.position
	var authored := {}
	if shot.has("camera"):
		for entry in stage_room.camera_nodes:
			if str(entry.id) == str(shot.camera):
				authored = {"from":[entry.node.global_position.x, entry.node.global_position.y, entry.node.global_position.z],
					"look":[entry.target.x, entry.target.y, entry.target.z], "fov":entry.node.fov}
	var e := 1.0 if reduced else smoothstep(0.0, 1.0, t)
	var pose := shot_pose(shot, e, follow, authored)
	stage_cam.fov = clampf(float(pose.fov), 20.0, 100.0)
	stage_cam.global_position = pose.from
	if pose.from.distance_to(pose.look) > 0.01:
		var up := Vector3.UP if absf((pose.look - pose.from).normalized().dot(Vector3.UP)) < 0.98 else Vector3.FORWARD
		stage_cam.look_at(pose.look, up)

## The shot language. All positions are room metres (the room's own grid coordinates).
## e is the eased card progress 0..1 (1 = the end framing, used for reduced motion).
static func shot_pose(s: Dictionary, e: float, follow_at: Vector3, authored: Dictionary = {}) -> Dictionary:
	var kind := str(s.get("kind", "hold"))
	var from := v3(s.get("from", authored.get("from", null)), Vector3(0, 2, 4))
	var look := v3(s.get("look", authored.get("look", null)), Vector3(0, 1, 0))
	var fov := float(s.get("fov", authored.get("fov", 55.0)))
	match kind:
		"push":
			var to := v3(s.get("to"), from + (look - from).normalized() * float(s.get("amount", 1.0)))
			from = from.lerp(to, e)
		"pan":
			look = look.lerp(v3(s.get("look_to"), look), e)
		"orbit":
			var r := float(s.get("radius", 4.0))
			var a := deg_to_rad(float(s.get("start_deg", 0.0)) + float(s.get("sweep_deg", 30.0)) * e)
			from = Vector3(look.x + sin(a) * r, float(s.get("height", look.y + 1.5)), look.z + cos(a) * r)
		"track":
			from = follow_at + v3(s.get("offset"), Vector3(0, 2, 4))
			look = follow_at + Vector3(0, float(s.get("look_height", 1.0)), 0)
	return {"from":from, "look":look, "fov":fov}

# ------------------------------------------------------------------ audio cues (names only)
## Slot names follow the AUDIOPIPE schema; this lane plays nothing itself. A scene card does
## not switch the room's music; voice starts when its card starts.
func cue(kind: String, value: String) -> void:
	cue_log.append([kind, value, card_index])
	var s = view.get("sounds")
	if s == null: return
	if kind == "voice" and s.has_method("voice"): s.voice(value)
	elif kind == "music" and s.has_method("on_cutscene_music"): s.on_cutscene_music(value)
	elif kind == "results" and s.has_method("on_results"): s.on_results()

func stop_voice() -> void:
	var s = view.get("sounds")
	if s != null and s.has_method("stop_voice"): s.stop_voice()

# ------------------------------------------------------------------ results
static func canonical_text(movie: Dictionary) -> String:
	return JSON.stringify(JSON.parse_string(JSON.stringify(movie, "", true, true)), "", true, true)

## First 12 hex of the sha256 of the run's input movie (canonical JSON), the same for the
## live run and for any replay of its saved file.
func run_code() -> String:
	var r = view.replay
	if r == null: return ""
	if r.recording: r.stop_record()
	var m = r.movie
	if not m is Dictionary or not m.get("frames") is Array or (m.frames as Array).is_empty(): return ""
	return canonical_text(m).sha256_text().substr(0, 12)

func show_results() -> void:
	results_wanted = false
	pending_results = false
	freeze()
	var run := RunSource.read(view, end_tick if end_tick >= 0 else int(view.actions.tick))
	var code := run_code()
	var gh: String = str(view.runtime.game.game_hash)
	var rec := {"best":BestStore.best(gh, best_path), "new_best":false, "written":false}
	if view.actions.source == "live" and run.finished: rec = BestStore.record(gh, int(run.ticks), code, best_path)
	results = Results.new()
	results.configure(str(results_cfg.get("title", view.runtime.game.title)), run, int(rec.best), bool(rec.new_best), code,
		results_cfg.get("labels", {}) if results_cfg.get("labels") is Dictionary else {})
	cue("results", "")
	fade = 0.0
	results_armed = view.actions.source != "live"
	results_receipt = {"run":run, "code":code, "best":int(rec.best), "new_best":bool(rec.new_best), "rows":results.rows(), "choices":results.choice_labels()}
	set_phase("results")
	results_shown.emit(results_receipt)

func save_replay() -> Dictionary:
	var r = view.replay
	if r == null or not r.movie is Dictionary or r.movie.is_empty() or results == null or results.code == "":
		return {"ok":false, "reason":"no movie"}
	var text := JSON.stringify(r.movie, "", true, true)
	var path := "user://replays/%s.h64movie.json" % results.code
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var f := FileAccess.open(path, FileAccess.WRITE)
	if f == null: return {"ok":false, "reason":"cannot write"}
	f.store_string(text); f.close()
	if OS.has_feature("web"):
		JavaScriptBridge.eval("(function(t,n){var a=document.createElement('a');a.href=URL.createObjectURL(new Blob([t],{type:'application/json'}));a.download=n;document.body.appendChild(a);a.click();a.remove();})(" + JSON.stringify(text) + "," + JSON.stringify(path.get_file()) + ")")
	results.saved = true
	results_receipt["saved"] = path
	publish()
	return {"ok":true, "path":path}

func results_key(event: InputEvent) -> void:
	if not results_armed: return
	var move := 0
	var confirm := false
	if event is InputEventKey:
		var k: int = event.physical_keycode if event.physical_keycode != 0 else event.keycode
		if k in [KEY_LEFT, KEY_A, KEY_UP, KEY_W]: move = -1
		elif k in [KEY_RIGHT, KEY_D, KEY_DOWN, KEY_S, KEY_TAB]: move = 1
		elif k in [KEY_ENTER, KEY_KP_ENTER, KEY_SPACE, KEY_E]: confirm = true
	elif event is InputEventJoypadButton:
		if event.button_index in [JOY_BUTTON_DPAD_LEFT, JOY_BUTTON_DPAD_UP]: move = -1
		elif event.button_index in [JOY_BUTTON_DPAD_RIGHT, JOY_BUTTON_DPAD_DOWN]: move = 1
		elif event.button_index in [JOY_BUTTON_A, JOY_BUTTON_START]: confirm = true
	if move != 0: results.move(move); canvas.queue_redraw(); publish()
	if confirm: choose(results.selected())

func choose(value: String) -> void:
	results_receipt["chosen"] = value
	publish()
	if value == "save": save_replay(); canvas.queue_redraw()
	elif value == "again" and again_handler.is_valid(): again_handler.call()

func _input(event: InputEvent) -> void:
	if phase == "idle": return
	if event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN, MOUSE_BUTTON_WHEEL_LEFT, MOUSE_BUTTON_WHEEL_RIGHT]: return
	if not (event is InputEventKey or event is InputEventJoypadButton or event is InputEventMouseButton): return
	if not event.pressed or (event is InputEventKey and event.echo): return
	if phase == "results":
		results_key(event)
	elif phase in ["lead_out", "card_in", "card", "card_out"]:
		skip()
	if is_inside_tree(): get_viewport().set_input_as_handled()

# ------------------------------------------------------------------ drawing
func draw_overlay(ci: CanvasItem) -> void:
	var font = PixelFont.get_font()
	var text_c := Pack.ui("text", "#e8e0cc")
	var ink := Pack.ui("ink", "#0b0d12")
	if phase == "results":
		if results != null: results.draw(ci, _width, 1.0)
		return
	var show_stage: bool = stage_room != null and phase in ["card_in", "card", "card_out", "tail_out"]
	if show_stage:
		ci.draw_texture_rect(stage.get_texture(), Rect2(0, 0, _width, H), false)
		if bool(scene.get("letterbox", true)):
			ci.draw_rect(Rect2(0, 0, _width, LETTERBOX), Color.BLACK)
			ci.draw_rect(Rect2(0, H - LETTERBOX, _width, LETTERBOX), Color.BLACK)
		var title := str(card.get("title", ""))
		if title != "":
			var scale := 2 if font.measure(title) * 2 <= _width - 24 else 1
			var tw: int = font.measure(title) * scale
			# Upper third, clear of faces framed at the centre.
			ci.draw_set_transform(Vector2(roundf((_width - tw) / 2.0), LETTERBOX + 22), 0.0, Vector2(scale, scale))
			font.draw(ci, Vector2.ZERO, title, text_c, Color(ink, 0.8))
			ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
		var sub = card.get("subtitle", {})
		if sub is Dictionary and str(sub.get("text", "")) != "":
			draw_subtitle(ci, font, str(sub.get("speaker", "")), str(sub.text), Pack.color(sub.get("color", "#f0c060"), "f0c060"), text_c, ink)
	elif phase == "idle" and label_left > 0.0 and label_text != "":
		var scale := 2 if font.measure(label_text) * 2 <= _width - 24 else 1
		var lw: int = font.measure(label_text) * scale
		var a := clampf((LABEL_SECONDS - label_left) / 0.1, 0.0, 1.0) * clampf(label_left / 0.25, 0.0, 1.0)
		ci.draw_set_transform(Vector2(roundf((_width - lw) / 2.0), 58), 0.0, Vector2(scale, scale))
		font.draw(ci, Vector2.ZERO, label_text, Color(text_c, a), Color(ink, 0.8 * a))
		ci.draw_set_transform(Vector2.ZERO, 0.0, Vector2.ONE)
	if fade > 0.0:
		if fade_kind == "iris" and fade < 1.0: draw_iris(ci, fade)
		else: ci.draw_rect(Rect2(0, 0, _width, H), Color(0, 0, 0, fade))

func draw_subtitle(ci: CanvasItem, font, speaker: String, text: String, tint: Color, text_c: Color, ink: Color) -> void:
	var lines: PackedStringArray = font.wrap(text, _width - 40)
	if lines.size() > 2: lines = lines.slice(0, 2)
	var rows := lines.size() + (1 if speaker != "" else 0)
	var band := rows * 11 + 6
	var y := H - band - 4
	ci.draw_rect(Rect2(0, y, _width, band + 4), Color(0, 0, 0, 0.72))
	var cy := y + 4
	if speaker != "":
		font.draw(ci, Vector2(roundf((_width - font.measure(speaker)) / 2.0), cy), speaker, tint, Color(ink, 0.8))
		cy += 11
	for line in lines:
		font.draw(ci, Vector2(roundf((_width - font.measure(line)) / 2.0), cy), line, text_c, Color(ink, 0.8))
		cy += 11

func draw_iris(ci: CanvasItem, amount: float) -> void:
	var c := Vector2(_width / 2.0, H / 2.0)
	var outer := c.length() + 4.0
	var r := outer * (1.0 - amount)
	var n := 40
	for i in n:
		var a0 := TAU * float(i) / n
		var a1 := TAU * float(i + 1) / n
		var d0 := Vector2(cos(a0), sin(a0))
		var d1 := Vector2(cos(a1), sin(a1))
		ci.draw_colored_polygon(PackedVector2Array([c + d0 * r, c + d0 * outer, c + d1 * outer, c + d1 * r]), Color.BLACK)

# ------------------------------------------------------------------ receipts
func receipt() -> Dictionary:
	return {"phase":phase, "scene":str(scene.get("id", "")), "card":card_index, "frozen":frozen, "played":played.keys(),
		"receipts":receipts, "results":results_receipt, "watchdog":watchdog.size(), "label":label_text if label_left > 0.0 else "",
		"subtitle":str(card.get("subtitle", {}).get("text", "")) if card.get("subtitle") is Dictionary and phase in ["card_in", "card", "card_out"] else "",
		"title":str(card.get("title", "")) if phase in ["card_in", "card", "card_out"] else "",
		"tick":int(view.actions.tick), "room":str(view.runtime.state.location), "context":str(view.actions.context),
		"menu":{"open":view.menu_open, "index":view.menu_index, "actions":view.ui_actions.map(func(a): return str(a.id))},
		"results_choice":results.selected() if results != null else ""}

var _published := 0
func publish() -> void:
	if OS.has_feature("web"):
		_published = Engine.get_process_frames()
		JavaScriptBridge.eval("window.hermes64=window.hermes64||{};window.hermes64.scenes=" + JSON.stringify(receipt()))
