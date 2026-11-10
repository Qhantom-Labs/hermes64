extends Node
## STORY 1.3 puzzle executor: fixed 60 Hz ticks, logic in whole grid steps (config.step_ticks), no wall clock.
## Loaded by the module host only when res://puzzle.json (the compiled puzzle sidecar) is present.
## Input comes from the host's InputAdapter over production Actions: WASD move/push, hold E + back to pull,
## E act (lever, brazier, key, lock; orbs along the facing line), hold Z (Focus) to turn in place and see the
## next interactable, hold R (Actions "reset") to reset the room. Facts are reserved flags in runtime.state.
const Rules = preload("res://modules/puzzle/rules.gd")
const Props = preload("res://modules/puzzle/props.gd")
const Player = preload("res://view/player.gd")
const Pack = preload("res://look/pack.gd")
const DIR_YAW := {"n": 0.0, "s": PI, "e": -PI / 2.0, "w": PI / 2.0}
const WALL_DIR := {"north": "n", "south": "s", "east": "e", "west": "w"}
const INWARD := {"north": "s", "south": "n", "east": "w", "west": "e"}
## Cue events resolve through the build's audio.json (shipped catalog WAVs, see tools/puzzle_play.py AUDIO).
const CUES := {"switch": "puzzle_lever", "plate": "puzzle_plate", "door": "puzzle_door", "timed_gate": "puzzle_gate",
	"block": "puzzle_push", "torch": "puzzle_torch", "key": "puzzle_key", "lock": "puzzle_unlock", "orb": "puzzle_orb",
	"solve": "puzzle_solve", "reset": "puzzle_reset"}

var host
var presenter
var runtime
var data: Dictionary = {}
var error := ""
var grids := {}          # room id -> Rules
var rules = null         # active Rules or null
var active := false
var st: Dictionary = {}
var anim_from: Dictionary = {}
var entry := ""
var facing := "n"
var step_age := -1
var token := ""
var tick := 0
var props
var pending_setup := false
var pending_entry := ""
var buffered_act := false
var steps := []           # receipts: every executed token with its exact state key
var lit := {}
var base_lights: Array = []
var cue_player: AudioStreamPlayer
var cue_log := []
var dispatched := []

func attach(module_host) -> void:
	host = module_host
	presenter = host.presenter
	runtime = host.runtime
	# Same typed-number reader as game.json and saves, so membership compares ints with ints.
	var parsed = preload("res://core/wire.gd").read_json("res://puzzle.json")
	if not parsed is Dictionary or parsed.get("api_version") != "1.0.0" or not parsed.get("puzzles") is Array:
		error = "invalid puzzle sidecar"; return
	if str(parsed.get("lowered_game_hash", "")) != str(runtime.game.game_hash):
		error = "puzzle sidecar is bound to a different build"; return
	data = parsed
	use_look(data.get("look", {}))
	if data.get("reachable") is Array: runtime.set_meta("puzzle_reachable", data.reachable)
	for p in data.puzzles:
		var r = Rules.new()
		r.configure(runtime.rooms[p.room], p, data.config)
		grids[str(p.room)] = r
	cue_player = AudioStreamPlayer.new()
	cue_player.volume_db = -12
	if AudioServer.get_bus_index("SFX") >= 0: cue_player.bus = "SFX"   # AUDIOPIPE: follows the user's SFX volume
	add_child(cue_player)
	presenter.room_entered.connect(_room_entered)
	presenter.state_changed.connect(_state_changed)
	setup("")

## The style pack's look data (palette + painted texture recipes) for the procedural puzzle props; it is
## shipped in the sidecar because the module runtime does not load look/pack.gd itself.
func use_look(look) -> void:
	if not look is Dictionary or not look.get("palette") is Array or not Pack.palette().is_empty(): return
	var colors: Array[Color] = []
	for h in look.palette: colors.append(Color(str(h)))
	Pack.current = look
	Pack.current_id = "puzzle_" + str(look.get("id", "pack"))
	Pack._palette = colors

## -------------------------------------------------------------------- room lifecycle
func _room_entered(_id: String) -> void:
	pending_setup = true
	pending_entry = ""

func _state_changed(result: Dictionary) -> void:
	var action := str(result.get("action", ""))
	if pending_setup:
		if action.begins_with("move:"):
			var parts := action.split(":")
			for door in runtime.rooms[parts[1]].doors:
				if door.id == parts[2]: pending_entry = str(door.to_door)
		setup(pending_entry)
	elif active and action.begins_with("checkpoint:"):
		setup("")  # a checkpoint committed in a puzzle room resets it with the player on the start cell
	elif active:
		pose_now()

func setup(new_entry: String) -> void:
	pending_setup = false
	step_age = -1
	buffered_act = false
	token = ""
	lit = {}
	rules = grids.get(str(runtime.state.location), null)
	active = rules != null
	if not active:
		props = null
		return
	entry = new_entry if rules.exits.has(new_entry) else ""
	var c := context()
	var out: Array = rules.canonical(c, entry)
	st = out[0]
	if not out[1].is_empty():
		apply_facts(out[1])
		st = rules.settle(st, context(), 0)[0]
	anim_from = st
	if props != null and is_instance_valid(props): props.queue_free()
	props = Props.new()
	presenter.room_root.add_child(props)
	props.build(rules, presenter.resolver)
	base_lights = presenter.room_root.presentation.get("lights", []).duplicate(true)
	if c.solved and not rules.goal.rewards.items.is_empty(): show_reward()
	facing = "n"
	if entry != "":
		for door in runtime.rooms[rules.room].doors:
			if door.id == entry: facing = INWARD[str(door.wall)]
	place_player(st.p)
	pose_now()
	host.emit_event("puzzle_entered", {"puzzle": rules.id, "entry": entry, "key": str(rules.key(st))})
	quiet_ui()
	steps.append({"tick": tick, "room": rules.room, "token": "enter:" + entry, "key": str(rules.key(st)), "events": []})

func reset_room() -> void:
	var c := context()
	var out: Array = rules.canonical(c, entry)
	st = out[0]
	if not out[1].is_empty():
		apply_facts(out[1])
		st = rules.settle(st, context(), 0)[0]
	anim_from = st
	step_age = -1
	buffered_act = false
	token = ""
	place_player(st.p)
	pose_now()
	cue("reset")
	host.emit_event("puzzle_reset", {"puzzle": rules.id, "key": str(rules.key(st))})
	steps.append({"tick": tick, "room": rules.room, "token": "reset", "key": str(rules.key(st)), "events": []})

func claim_reset() -> bool:
	if not active or not rules.resettable: return false
	reset_room()
	return true

func owns_input() -> bool:
	return active

func allows(id: String) -> bool:
	if not active or not id.begins_with("move:" + rules.room + ":"): return true
	var door := id.split(":")[2]
	return step_age < 0 and rules.exits.has(door) and rules.exits[door] == st.p

## -------------------------------------------------------------------- facts
func context() -> Dictionary:
	var solved := []; var taken := []; var opened := []; var latched := []
	for name in runtime.state.flags:
		if not runtime.state.flags[name] or not str(name).begins_with("puzzle__"): continue
		var kind := str(name).substr(8, 1)
		var eid := str(name).substr(11)
		match kind:
			"s": solved.append(eid)
			"t": taken.append(eid)
			"o": opened.append(eid)
			"l": latched.append(eid)
	return rules.ctx(solved, taken, opened, latched, runtime.state.inventory)

func apply_facts(events: Array) -> void:
	var s: Dictionary = runtime.state
	var inventory: Array = s.inventory.duplicate()
	for ev in events:
		match str(ev[0]):
			"take":
				s.flags["puzzle__t__" + str(ev[1])] = true
				var item := str(rules.el[ev[1]].item)
				if not inventory.has(item): inventory.append(item)
				cue("key")
			"unlock":
				s.flags["puzzle__o__" + str(ev[1])] = true
				inventory.erase(str(ev[2]))
				cue("lock")
			"latch":
				s.flags["puzzle__l__" + str(ev[1])] = true
			"solve":
				s.flags["puzzle__s__" + rules.id] = true
				for item in rules.goal.rewards.items:
					if not inventory.has(str(item)): inventory.append(str(item))
				cue("solve")
				if not rules.goal.rewards.items.is_empty(): show_reward()
		host.emit_event("puzzle_" + str(ev[0]), {"puzzle": rules.id, "event": Rules.event_token(ev)})
	inventory.sort()
	s.inventory = inventory
	presenter.refresh()
	quiet_ui()

## Puzzle rooms read through props, light and sound: no room-description box over the play field. Story text
## from interactions, dialogue and endings still shows; E dismisses it when nothing else is in reach.
func quiet_ui() -> void:
	presenter.last_text = ""
	if presenter.text_label != null: presenter.text_label.text = ""
	hide_empty_box()

func hide_empty_box() -> void:
	var ui = presenter.n64_ui
	if ui == null or not ui.dlg_on or presenter.menu_open or presenter.dialogue_active(): return
	if str(presenter.text_label.text) == "" and runtime.endings(runtime.state).is_empty(): ui.hide_dialog()

func dismiss_text() -> bool:
	var ui = presenter.n64_ui
	if ui == null or not ui.dlg_on or presenter.menu_open or presenter.dialogue_active() or not runtime.endings(runtime.state).is_empty(): return false
	quiet_ui()
	ui.hide_dialog()
	return true

func show_reward() -> void:
	if props == null: return
	for y in rules.rows:
		for x in rules.cols:
			var c := Vector2i(x, y)
			if rules.terrain(c) == "." and not rules.cell_of.has(c) and c != rules.start and rules.exit_cells.get(c, []).is_empty():
				# first free floor cell behind a goal-opened door: the reward alcove
				for oid in rules.goal.opens:
					var e: Dictionary = rules.el[oid]
					if e.kind == "door" and Rules.adjacent(c, Rules.cell(e.cell)) and c.y < Rules.cell(e.cell).y:
						props.show_reward(c)
						return

## -------------------------------------------------------------------- fixed tick
func physics_tick(input) -> void:
	if pending_setup: setup(pending_entry)
	if not active: return
	tick += 1
	hide_empty_box()
	if input.just_pressed("primary") and step_age >= 0: buffered_act = true
	if step_age >= 0:
		step_age += 1
		animate(float(step_age) / float(rules.step_ticks))
		if step_age < rules.step_ticks: return
		step_age = -1
		anim_from = st
		presenter.player.actual_velocity = Vector3.ZERO
	decide(input)
	if step_age < 0: pose_now()
	props.show_marker(next_hint() if input.is_pressed("focus") else "", tick)

func dir_of(move: Vector2) -> String:
	if move.length() < 0.5: return ""
	var basis: Basis = Player.horizontal_basis(presenter.player.camera_basis)
	var w: Vector3 = basis.x * move.x + basis.z * move.y
	if absf(w.x) >= absf(w.z): return "e" if w.x > 0.0 else "w"
	return "s" if w.z > 0.0 else "n"

## Inverse used by bots: which digital stick direction produces grid direction d under the current camera.
func input_for(d: String) -> Vector2:
	for v in [Vector2(0, -1), Vector2(1, 0), Vector2(0, 1), Vector2(-1, 0)]:
		if dir_of(v) == d: return v
	return Vector2.ZERO

func intent(input) -> Vector2:
	return input.get_raw_move() if input.has_method("get_raw_move") else input.get_move()

## One decision per idle tick: pull (hold E + back), turn (free), act (E on the faced element, else the room's
## own interaction in reach), move/push, exit (walk into the door wall from its cell). While a timed gate runs,
## standing still lets one step of time pass (``wait``), exactly the proof's token set.
func decide(input) -> void:
	var c := context()
	var d := dir_of(intent(input))
	var focus: bool = input.is_pressed("focus")
	var grab: bool = input.is_pressed("primary")
	var act: bool = input.just_pressed("primary") or buffered_act
	buffered_act = false
	var front: Vector2i = st.p + Rules.DIRS[facing]
	var holding: bool = grab and st.blocks.has(front)
	var turned := false
	var next := ""
	if holding and d == Rules.OPPOSITE[facing] and rules.apply(st, c, "pull." + d) != null:
		next = "pull." + d
	if next == "" and d != "" and d != facing and not holding and (focus or rules.apply(st, c, "move." + d) == null):
		set_facing(d)  # turning in place takes no time
		turned = true
	if next == "" and act:
		var target := facing_target(c)
		if target != "": next = "act." + target
		elif context_dispatch(): return
		elif dismiss_text(): return
	if next == "" and d != "" and not focus and not holding:
		if rules.apply(st, c, "move." + d) != null:
			next = "move." + d
			set_facing(d)
		elif try_exit(d):
			return
	if next == "" and not turned:
		for t in st.tm:
			if int(t) > 0: next = "wait"
	if next != "": start_step(next, c)

## A STORY 1.2 interaction/take/talk of this room whose anchor is on the player's cell or the faced cell.
func context_action() -> String:
	var here := centre(st.p)
	var ahead := centre(st.p + Rules.DIRS[facing])
	for a in runtime.actions(runtime.state):
		var id := str(a.id)
		if id.begins_with("move:") or id.begins_with("checkpoint:") or id.begins_with("challenge:") or id.begins_with("assume:"): continue
		var at = presenter.room_root.target_positions.get(id, null)
		if not at is Vector3: continue
		for probe in [ahead, here]:
			if Vector2(at.x - probe.x, at.z - probe.z).length() <= 0.75: return id
	return ""

func context_dispatch() -> bool:
	var id := context_action()
	if id == "": return false
	var result: Dictionary = presenter.dispatch(id)
	dispatched.append({"tick": tick, "action": id, "ok": bool(result.get("ok", false))})
	return bool(result.get("ok", false))

func facing_target(c: Dictionary) -> String:
	var dv: Vector2i = Rules.DIRS[facing]
	var front: Vector2i = st.p + dv
	if rules.cell_of.has(front):
		var eid: String = rules.cell_of[front]
		if str(rules.el[eid].kind) in ["switch", "torch", "lock", "key"]:
			return eid if rules.apply(st, c, "act." + eid) != null else ""
	for k in range(1, 9):
		var at: Vector2i = st.p + dv * k
		if not rules.inside(at) or rules.terrain(at) == "#" or st.blocks.has(at): return ""
		if rules.cell_of.has(at):
			var oid: String = rules.cell_of[at]
			if rules.el[oid].kind == "orb": return oid if rules.apply(st, c, "act." + oid) != null else ""
			if rules.solid(st, c, at): return ""
	return ""

func try_exit(d: String) -> bool:
	for did in rules.exit_cells.get(st.p, []):
		for door in runtime.rooms[rules.room].doors:
			if door.id == did and WALL_DIR[str(door.wall)] == d:
				var result: Dictionary = presenter.dispatch("move:" + rules.room + ":" + did)
				return bool(result.get("ok", false))
	return false

func start_step(next: String, c: Dictionary) -> void:
	var res = rules.advance(st, c, next)
	if res == null: return
	anim_from = st
	st = res[0]
	var events: Array = res[1]
	if not events.is_empty():
		apply_facts(events)
		var more: Array = rules.settle(st, context(), 0)
		st = more[0]
		if not more[1].is_empty():
			apply_facts(more[1])
			events = events + more[1]
	token = next
	step_age = 0
	steps.append({"tick": tick, "room": rules.room, "token": next, "key": str(rules.key(st)), "events": events.map(func(e): return Rules.event_token(e))})
	play_cues(next)
	update_lights()

func play_cues(next: String) -> void:
	var c := context()
	if next.begins_with("act."):
		var kind := str(rules.el[next.substr(4)].kind)
		if kind in ["switch", "torch", "orb"]: cue(kind)
	elif (next.begins_with("move.") or next.begins_with("pull.")) and anim_from.blocks != st.blocks:
		cue("block")
	for i in rules.ids:
		var k := str(rules.el[i].kind)
		if k in ["door", "timed_gate"] and rules.has(anim_from, i, "open") != rules.has(st, i, "open"): cue(k)
		elif k == "plate" and rules.source(st, c, i) and not rules.source(anim_from, c, i): cue("plate")

func cue(kind: String) -> void:
	var event: String = CUES.get(kind, "")
	if cue_log.size() < 512: cue_log.append({"tick": tick, "cue": event})
	var sounds = presenter.sounds
	if sounds == null or not sounds.playback_enabled or not sounds.clips.has(event): return
	cue_player.stream = sounds.clips[event]
	cue_player.play()

## -------------------------------------------------------------------- presentation
func centre(c: Vector2i) -> Vector3:
	return Vector3(c.x + 0.5, 0.02, c.y + 0.5)

func place_player(c: Vector2i) -> void:
	presenter.player.position = centre(c)
	presenter.player.velocity = Vector3.ZERO
	presenter.player.actual_velocity = Vector3.ZERO
	set_facing(facing)

func set_facing(d: String) -> void:
	facing = d
	presenter.player.set_facing_yaw(DIR_YAW[d])

func animate(t: float) -> void:
	var a: Vector3 = centre(anim_from.p)
	var b: Vector3 = centre(st.p)
	presenter.player.position = a.lerp(b, clampf(t, 0.0, 1.0))
	presenter.player.actual_velocity = (b - a) * (60.0 / float(rules.step_ticks)) if t < 1.0 else Vector3.ZERO
	props.pose(anim_from, st, context(), clampf(t, 0.0, 1.0), tick)

func pose_now() -> void:
	if props != null and is_instance_valid(props): props.pose(st, st, context(), 1.0, tick)

## Lit braziers add warm point lights through the pack light rig (vertex/pixel glow on nearby surfaces).
func update_lights() -> void:
	var now := {}
	for i in rules.ids:
		if rules.el[i].kind == "torch" and rules.has(st, i): now[i] = true
	if now == lit: return
	lit = now
	var room_root = presenter.room_root
	room_root.presentation = room_root.presentation.duplicate(true)
	var extra: Array = base_lights.duplicate(true)
	for i in lit:
		var c := Rules.cell(rules.el[i].cell)
		extra.append({"position": [c.x + 0.5, 1.3, c.y + 0.5], "color": "#ffb060", "intensity": 1.4, "radius": 3.6})
	room_root.presentation["lights"] = extra
	presenter.apply_room_look()

## The Focus assist target: the first hint element whose job is not done yet, else nothing.
func next_hint() -> String:
	var c := context()
	for h in rules.hint:
		var e: Dictionary = rules.el[h]
		match str(e.kind):
			"switch", "torch", "orb":
				if not (rules.has(st, h) or c.latched.has(h)): return h
			"plate":
				if not rules.source(st, c, h): return h
			"key":
				if not c.taken.has(h): return h
			"lock":
				if not c.opened.has(h): return h
			"block":
				var at: Vector2i = st.blocks[rules.blocks.find(h)]
				var on_plate: bool = rules.cell_of.has(at) and rules.el[rules.cell_of[at]].kind == "plate"
				if not on_plate: return h
	return ""

func snapshot() -> Dictionary:
	if not active: return {"active": false}
	return {"active": true, "room": rules.room, "entry": entry, "key": str(rules.key(st)), "facing": facing,
		"step_age": step_age, "token": token, "tick": tick}

static func pack_state(s: Dictionary) -> Dictionary:
	return {"p": [s.p.x, s.p.y], "blocks": s.blocks.map(func(b): return [b.x, b.y]), "on": str(s.on), "tm": s.tm.duplicate()}

static func unpack_state(s: Dictionary) -> Dictionary:
	return {"p": Vector2i(int(s.p[0]), int(s.p[1])), "blocks": s.blocks.map(func(b): return Vector2i(int(b[0]), int(b[1]))),
		"on": int(str(s.on)), "tm": s.tm.map(func(t): return int(t))}

## Replay-movie extension (modules/movie_state.gd): the complete transient executor state.
func capture() -> Dictionary:
	var out := {"active": active, "tick": tick}
	if active:
		out.merge({"room": rules.room, "entry": entry, "st": pack_state(st), "from": pack_state(anim_from), "facing": facing,
			"step_age": step_age, "token": token, "buffered_act": buffered_act})
	return out

func restore(data: Dictionary) -> void:
	tick = int(data.get("tick", 0))
	if not bool(data.get("active", false)):
		return
	if rules == null or rules.room != str(data.room) or not active: setup(str(data.entry))
	entry = str(data.entry)
	st = unpack_state(data.st)
	anim_from = unpack_state(data.from)
	facing = str(data.facing)
	step_age = int(data.step_age)
	token = str(data.token)
	buffered_act = bool(data.buffered_act)
	lit = {}
	update_lights()
	place_player(st.p if step_age < 0 else anim_from.p)
	if step_age >= 0: animate(float(step_age) / float(rules.step_ticks))
	else: pose_now()
