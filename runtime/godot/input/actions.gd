extends Node
## Canonical fixed-tick input provider. Frozen consumer contract: docs/CONTROLS-API.md.
const NAMES := ["move", "walk", "primary", "secondary", "focus", "dodge", "menu", "action_menu", "inventory", "quick_save", "quick_load", "reset", "run"]
const ORBIT_NAMES := ["camera_left","camera_right","camera_up","camera_down","camera_recenter"]
const Profile = preload("res://input/profile.gd")
const HZ := 60
const DT := 1.0 / HZ
var tick := 0
var held: Dictionary = {}
var edges: Dictionary = {}
var movement := Vector2.ZERO
var profile: Dictionary = Profile.defaults()
var source := "live"
var context := "gameplay"
var fixed_camera := true
var last_frame := {}
var pending := {}
var raw_previous := []
var key_order := {}
var key_direction := Vector2.ZERO
var stick := 0.0
var buffers := {}
var focus_toggle := false
var walk_toggle := false
var run_toggle := false
var reset_ticks := 0
var blocked_move := false
var active_device := "key"
var camera_move := Vector2.ZERO
var config_error := ""
var frame_provider: Callable
# MOVE: live frames carry the fixed-tick view heading [yaw_rad, orbiting]. It is
# recorded so replays reproduce camera-relative movement without mouse state.
var heading_provider: Callable

func _ready() -> void:
	process_physics_priority = -100
	Profile.install(profile)
	load_remap()

func configure(raw: Variant) -> Dictionary:
	var result := Profile.validate(raw)
	profile = result.profile if result.ok else Profile.defaults()
	config_error = "" if result.ok else result.reason
	Profile.install(profile)
	return result

func load_remap(path := Profile.PATH) -> Dictionary:
	if not FileAccess.file_exists(path): return configure({"version":1})
	if FileAccess.get_file_as_bytes(path).size() > 65536: return configure(null)
	var parser := JSON.new()
	if parser.parse(FileAccess.get_file_as_string(path)) != OK: return configure(null)
	var result := configure(Profile.saved_profile(parser.data))
	if result.ok and not profile.bindings.has("run"):
		config_error="Saved controls retained: no unused key available for FEEL2 upgrade"
		result["warning"]=config_error
	return result

func save_remap(raw: Dictionary, path := Profile.PATH) -> Dictionary:
	var result := Profile.validate(raw)
	if not result.ok: return result
	var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null: return {"ok":false,"reason":"remap write failed"}
	file.store_string(JSON.stringify(raw, "	", true)); file.close()
	if DirAccess.rename_absolute(path + ".tmp", path) != OK: return {"ok":false,"reason":"remap rename failed"}
	return configure(raw)

func set_source(value: String) -> void:
	assert(value in ["live","bot","replay"])
	source = value
	restore({})

func set_context(value: String) -> void:
	assert(value in ["gameplay","menu","dialogue","inventory","pause"])
	if value == context: return
	context = value
	movement = Vector2.ZERO; stick = 0.0
	blocked_move = true; focus_toggle = false; walk_toggle = false; run_toggle = false
	held["focus"] = false
	if held.has("run"): held.run = false
	buffers.clear()

func submit_frame(frame: Dictionary) -> void:
	pending = frame.duplicate(true)

func _physics_process(_delta: float) -> void:
	var frame: Dictionary = sample_live() if source == "live" else (frame_provider.call() if source == "replay" and frame_provider.is_valid() else pending)
	pending = {}
	advance(frame)

func sample_live() -> Dictionary:
	var digital := []
	var buttons := []
	for action in profile.bindings:
		if Input.is_action_pressed("h64_key_" + action): digital.append(action)
		if not action in Profile.DIRECTIONS and pad_strength(action)>0: buttons.append(action)
	if "quick_save" in buttons or "quick_load" in buttons:
		buttons.erase("dodge"); buttons.erase("reset")
	# Enter is a modal-only fallback; Space is the remappable dodge binding.
	if context != "gameplay" and Input.is_physical_key_pressed(KEY_ENTER): digital.append("confirm")
	var analog := Vector2(pad_strength("move_right") - pad_strength("move_left"),pad_strength("move_down") - pad_strength("move_up"))
	var cam := Vector2(pad_strength("camera_right") - pad_strength("camera_left"),pad_strength("camera_down") - pad_strength("camera_up"))
	var frame := {"digital":digital,"buttons":buttons,"analog":[analog.x,analog.y],"camera":[cam.x,cam.y]}
	if heading_provider.is_valid():
		var heading = heading_provider.call()
		if heading is Array and heading.size() == 2: frame["heading"] = heading
	return frame

func pad_strength(action: String) -> float:
	var strength:=Input.get_action_raw_strength("h64_pad_"+action)
	if strength==0 or not profile.bindings[action].any(func(b):return b.has("with")): return strength
	# InputMap tracks constituent buttons; gate chords against the same device.
	# Plain alternatives remain usable, but never unlock an unheld chord.
	for b in profile.bindings[action]:
		for device in Input.get_connected_joypads():
			if b.has("button") and Input.is_joy_button_pressed(device,int(b.button)):
				if not b.has("with") or Input.is_joy_button_pressed(device,int(b.with)): return strength
			if b.has("axis") and Input.get_joy_axis(device,int(b.axis))*float(b.sign)>0: return strength
	return 0.0

func get_raw_move() -> Vector2:
	return key_direction if active_device == "key" else vector(last_frame.get("analog",[0,0]))

func get_camera() -> Vector2:
	return camera_move

static func vector(raw: Variant) -> Vector2:
	if not raw is Array or raw.size() != 2: return Vector2.ZERO
	if not (raw[0] is int or raw[0] is float) or not (raw[1] is int or raw[1] is float): return Vector2.ZERO
	if not is_finite(float(raw[0])) or not is_finite(float(raw[1])): return Vector2.ZERO
	return Vector2(clampf(raw[0],-1,1),clampf(raw[1],-1,1))

func get_move() -> Vector2:
	return movement

func is_pressed(action: String) -> bool:
	return bool(held.get(action, false))

func just_pressed(action: String) -> bool:
	return bool(edges.get(action, false))

func advance(frame: Dictionary) -> void:
	tick += 1
	last_frame = frame.duplicate(true)
	var previous := held.duplicate()
	var raw: Array = frame.get("digital", []).duplicate()
	var buttons: Array = frame.get("buttons", [])
	for action in buttons:
		if action not in raw: raw.append(action)
	var rising := []
	for action in raw:
		if action not in raw_previous: rising.append(action); key_order[action] = tick
	var tuning: Dictionary = profile.tuning
	var legacy: bool = not profile.bindings.has("run")
	held.clear(); edges.clear()
	for action in NAMES + Profile.BUTTONS + Profile.DIRECTIONS + ["confirm","nav_up","nav_down","nav_left","nav_right"]:
		if (legacy and action == "run") or (action == "camera_recenter" and not profile.bindings.has(action)): continue
		held[action] = action in raw
	if "focus" in rising: focus_toggle = not focus_toggle
	held.focus = focus_toggle if profile.options.focus_mode == "toggle" else "focus" in raw
	if legacy:
		# Preserve old movie physical frames, mode inversion and snapshot shape.
		if "walk" in rising: walk_toggle = not walk_toggle
		held.walk = (not "walk" in raw) if profile.options.run_mode == "hold" else (walk_toggle if profile.options.run_mode == "toggle" else "walk" in raw)
	else:
		if context == "gameplay" and profile.options.run_mode == "toggle" and "run" in rising: run_toggle = not run_toggle
		held.walk = "walk" in raw
		held.run = not held.walk and (profile.options.run_mode == "auto" or ("run" in raw if profile.options.run_mode == "hold" else run_toggle))
	reset_ticks = reset_ticks + 1 if "reset" in raw else 0
	held.reset = reset_ticks >= ceili(tuning.hold_to_retry_s * HZ)
	key_direction = Vector2(axis(raw,"move_left","move_right"),axis(raw,"move_up","move_down")).limit_length()
	if key_direction != Vector2.ZERO: active_device = "key"
	var analog := vector(frame.get("analog",[0,0]))
	var magnitude := analog.length()
	analog = analog.normalized() * clampf((magnitude-tuning.dead_zone_pad)/(tuning.outer_saturation-tuning.dead_zone_pad),0,1)
	if analog != Vector2.ZERO or buttons.any(func(action): return legacy or action not in ORBIT_NAMES): active_device = "pad"
	var prior_dir := movement.normalized()
	stick = move_toward(stick, 1.0 if key_direction != Vector2.ZERO else 0.0, DT / float(tuning.stick_ramp_up_s if key_direction != Vector2.ZERO else tuning.stick_ramp_down_s))
	stick = Vector2(stick,0).x
	if stick < 0.000001: stick = 0.0
	movement = (key_direction if key_direction != Vector2.ZERO else prior_dir) * stick
	if analog != Vector2.ZERO or active_device == "pad": movement = analog
	if held.walk: movement = movement.limit_length(tuning.walk_modifier_cap)
	elif not legacy and not held.run: movement = movement.limit_length(tuning.jog_modifier_cap)
	if blocked_move:
		movement = Vector2.ZERO; stick = 0.0
		if key_direction == Vector2.ZERO and analog == Vector2.ZERO: blocked_move = false
	camera_move = Vector2.ZERO
	if not fixed_camera and context == "gameplay":
		camera_move = vector(frame.get("camera",[0,0])).limit_length()
		if "camera_cycle" in raw:
			camera_move = Vector2(float("camera_right" in raw)-float("camera_left" in raw),float("camera_down" in raw)-float("camera_up" in raw)).limit_length()
			held.inventory = false
	if context != "gameplay":
		movement = Vector2.ZERO; stick = 0.0
		held.walk = "walk" in raw
		if not legacy: held.run = "run" in raw
		held.focus = false; held.dodge = false
		held.confirm = "confirm" in raw or "dodge" in raw or "primary" in raw
		for d in ["up","down","left","right"]: held["nav_"+d] = "move_"+d in raw
	else:
		held.confirm = false
		for d in ["up","down","left","right"]: held["nav_"+d] = false
	held.move = movement != Vector2.ZERO
	for action in held: edges[action] = held[action] and not previous.get(action,false)
	for action in ["primary","secondary","dodge"]:
		if just_pressed(action): buffers[action] = tick
	raw_previous = raw

func axis(raw: Array, negative: String, positive: String) -> float:
	if negative in raw and positive in raw:
		if profile.options.opposite_key_rule == "cancel": return 0.0
		return -1.0 if key_order.get(negative,0) > key_order.get(positive,0) else 1.0
	return float(positive in raw) - float(negative in raw)

func consume_buffer(action: String, legal: bool, contact_tick := -1) -> bool:
	if not buffers.has(action) or tick - int(buffers[action]) >= ceili(float(profile.tuning.action_buffer_s) * HZ): return false
	if not legal and (contact_tick < 0 or tick - contact_tick > ceili(float(profile.tuning.coyote_s) * HZ)): return false
	buffers.erase(action)
	return true

func binding_glyph(action: String) -> String:
	for binding in profile.bindings.get(action, []):
		if active_device == "pad" and binding.has("button"): return "B%d" % int(binding.button)
		if active_device == "pad" and binding.has("axis"): return "T%d" % int(binding.axis)
	for binding in profile.bindings.get(action, []):
		if binding.has("key"):
			# Layout-aware labels where the display server supports them (the web display
			# server reports "Not supported" on every call); physical/US label otherwise.
			var code := DisplayServer.keyboard_get_label_from_physical(int(binding.key)) if DisplayServer.get_name() != "headless" and not OS.has_feature("web") else int(binding.key)
			var text := OS.get_keycode_string(code)
			return {"Escape":"Esc","Backspace":"Bk","Shift":"Sh","Option":"Alt","Space":"Spc","Enter":"Ent","Control":"Ctl","Period":".","Slash":"/"}.get(text,text.substr(0,3))
	return "?"

func snapshot() -> Dictionary:
	var state := {"tick":tick,"held":held.duplicate(),"edges":edges.duplicate(),"move":[movement.x,movement.y],"raw_previous":raw_previous.duplicate(),"key_order":key_order.duplicate(),"key_direction":[key_direction.x,key_direction.y],"stick":stick,"buffers":buffers.duplicate(),"focus_toggle":focus_toggle,"walk_toggle":walk_toggle,"reset_ticks":reset_ticks,"blocked_move":blocked_move,"context":context,"active_device":active_device}
	if profile.bindings.has("run"):
		state["run_toggle"] = run_toggle
		# Modern orbit input is recorded for presentation but excluded from every
		# canonical reducer field. Legacy profiles retain their exact old shape.
		for field in ["held","edges","buffers","key_order"]:
			for action in ORBIT_NAMES: state[field].erase(action)
		state.raw_previous=state.raw_previous.filter(func(action): return action not in ORBIT_NAMES)
	return state

func restore(s: Dictionary) -> void:
	tick = int(s.get("tick",0)); held = s.get("held",{}).duplicate(); edges = s.get("edges",{}).duplicate()
	movement = vector(s.get("move",[0,0])); raw_previous = s.get("raw_previous",[]).duplicate()
	key_order = s.get("key_order",{}).duplicate(); key_direction = vector(s.get("key_direction",[0,0])); stick = float(s.get("stick",0.0))
	buffers = s.get("buffers",{}).duplicate(); focus_toggle = s.get("focus_toggle",false); walk_toggle = s.get("walk_toggle",false)
	run_toggle = s.get("run_toggle",false)
	reset_ticks = int(s.get("reset_ticks",0)); blocked_move = s.get("blocked_move",false); context = s.get("context","gameplay"); active_device = s.get("active_device","key")
	pending = {}; last_frame = {}; camera_move = Vector2.ZERO
