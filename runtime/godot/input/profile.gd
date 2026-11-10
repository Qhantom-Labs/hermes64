extends RefCounted
## Remap validation is atomic: one bad field rejects the whole override.
const PATH := "user://hermes64_input.json"
const DIRECTIONS := ["move_left", "move_right", "move_up", "move_down"]
const BUTTONS := ["walk", "primary", "secondary", "focus", "dodge", "menu", "action_menu", "inventory", "quick_save", "quick_load", "reset", "camera_cycle", "camera_left", "camera_right", "camera_up", "camera_down", "dev_toggle", "dev_pause", "dev_step", "dev_slow", "dev_input", "dev_perf", "dev_record", "screenshot", "run", "camera_recenter"]

static func defaults() -> Dictionary:
	var d: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://input/defaults.json"))
	d["bindings"] = {
		"move_left":[{"key":KEY_A},{"key":KEY_LEFT},{"axis":JOY_AXIS_LEFT_X,"sign":-1}],
		"move_right":[{"key":KEY_D},{"key":KEY_RIGHT},{"axis":JOY_AXIS_LEFT_X,"sign":1}],
		"move_up":[{"key":KEY_W},{"key":KEY_UP},{"axis":JOY_AXIS_LEFT_Y,"sign":-1}],
		"move_down":[{"key":KEY_S},{"key":KEY_DOWN},{"axis":JOY_AXIS_LEFT_Y,"sign":1}],
		"walk":[{"key":KEY_ALT}], "primary":[{"key":KEY_E},{"button":JOY_BUTTON_A}],
		"secondary":[{"key":KEY_Q},{"key":KEY_BACKSPACE},{"button":JOY_BUTTON_B}],
		"focus":[{"key":KEY_Z},{"axis":JOY_AXIS_TRIGGER_LEFT,"sign":1}],
		"dodge":[{"key":KEY_SPACE},{"button":JOY_BUTTON_RIGHT_SHOULDER}],
		"menu":[{"key":KEY_ESCAPE},{"button":JOY_BUTTON_START}],
		"action_menu":[{"key":KEY_TAB},{"button":JOY_BUTTON_Y}],
		"inventory":[{"key":KEY_I},{"button":JOY_BUTTON_DPAD_UP}],
		"quick_save":[{"key":KEY_F5},{"button":JOY_BUTTON_RIGHT_SHOULDER,"with":JOY_BUTTON_BACK}],
		"quick_load":[{"key":KEY_F9},{"button":JOY_BUTTON_LEFT_SHOULDER,"with":JOY_BUTTON_BACK}],
		"reset":[{"key":KEY_R},{"button":JOY_BUTTON_BACK}],
		"camera_cycle":[{"key":KEY_C}],
		"camera_left":[{"key":KEY_J},{"axis":JOY_AXIS_RIGHT_X,"sign":-1}],
		"camera_right":[{"key":KEY_L},{"axis":JOY_AXIS_RIGHT_X,"sign":1}],
		"camera_up":[{"key":KEY_U},{"axis":JOY_AXIS_RIGHT_Y,"sign":-1}],
		"camera_down":[{"key":KEY_K},{"axis":JOY_AXIS_RIGHT_Y,"sign":1}],
		"dev_toggle":[{"key":KEY_F1,"ctrl":true,"alt":true}],
		"dev_pause":[{"key":KEY_P}], "dev_step":[{"key":KEY_PERIOD}],
		"dev_slow":[{"key":KEY_F6}], "dev_input":[{"key":KEY_F2}],
		"dev_perf":[{"key":KEY_F3}], "dev_record":[{"key":KEY_F4}], "screenshot":[{"key":KEY_F12}],
		"run":[{"key":KEY_SHIFT}], "camera_recenter":[{"key":KEY_V}]
	}
	d["preset"] = "left"
	return d

static func validate(raw: Variant) -> Dictionary:
	var d := defaults()
	if not raw is Dictionary: return {"ok":false,"reason":"input profile must be an object"}
	for k in raw:
		if k not in ["version","preset","bindings","options","tuning"]: return {"ok":false,"reason":"unknown input field: " + str(k)}
	if not integer(raw.get("version")) or int(raw.version) != 1: return {"ok":false,"reason":"unsupported input version"}
	if raw.get("preset", "left") not in ["left","right"]: return {"ok":false,"reason":"unknown preset"}
	d.preset = raw.get("preset", "left")
	if d.preset == "right":
		for pair in [["primary",KEY_ENTER],["secondary",KEY_CTRL],["focus",KEY_SLASH],["dodge",KEY_SPACE],["action_menu",KEY_BACKSPACE]]:
			d.bindings[pair[0]] = [{"key":pair[1]}] + d.bindings[pair[0]].filter(func(e): return not e.has("key"))
	# Movie v1 stores a full profile. Absence of only the appended run action
	# selects the old reducer; partial user overrides still get modern defaults.
	var old_bindings = raw.get("bindings",{})
	if old_bindings is Dictionary and not old_bindings.has("run") and d.bindings.keys().all(func(action): return action in ["run","camera_recenter"] or old_bindings.has(action)):
		d.bindings.erase("run")
		if not old_bindings.has("camera_recenter"): d.bindings.erase("camera_recenter")
		d.options.run_mode = "auto"
	for section in ["bindings","options","tuning"]:
		if not raw.get(section, {}) is Dictionary: return {"ok":false,"reason":"invalid " + section}
		for k in raw.get(section, {}):
			if not d[section].has(k): return {"ok":false,"reason":"unknown " + section + ": " + str(k)}
			d[section][k] = raw[section][k]
	if d.options.run_mode not in ["auto","hold","toggle"] or d.options.focus_mode not in ["hold","toggle"] or d.options.opposite_key_rule not in ["last_wins","cancel"] or not d.options.reduced_motion is bool:
		return {"ok":false,"reason":"invalid control option"}
	for k in d.tuning:
		var v = d.tuning[k]
		if not (v is float or v is int) or not is_finite(float(v)) or v < d.ranges[k][0] or v > d.ranges[k][1]: return {"ok":false,"reason":"out of range tuning: " + k}
	if d.tuning.focus_release_m < d.tuning.focus_acquire_m or d.tuning.dead_zone_pad >= d.tuning.outer_saturation or d.tuning.jog_modifier_cap < d.tuning.walk_modifier_cap: return {"ok":false,"reason":"inconsistent tuning ranges"}
	var used := {}
	for action in d.bindings:
		var entries = d.bindings[action]
		if not entries is Array or entries.is_empty() or entries.size() > 8: return {"ok":false,"reason":"empty/oversized binding: " + action}
		for e in entries:
			if not e is Dictionary: return {"ok":false,"reason":"binding must be object"}
			var types := int(e.has("key")) + int(e.has("button")) + int(e.has("axis"))
			if types != 1: return {"ok":false,"reason":"binding needs one device type"}
			for k in e:
				if k not in ["key","button","axis","sign","with","ctrl","alt","shift"]: return {"ok":false,"reason":"unknown binding field"}
			var signature := ""
			if e.has("key"):
				if not integer(e.key) or e.key <= 0 or OS.get_keycode_string(int(e.key)).is_empty(): return {"ok":false,"reason":"invalid physical key"}
				if e.has("with") or e.has("sign"): return {"ok":false,"reason":"key has pad fields"}
				for k in ["ctrl","alt","shift"]:
					if e.has(k) and not e[k] is bool: return {"ok":false,"reason":"invalid modifier"}
				signature = "key:%d:%s:%s:%s" % [e.key,e.get("ctrl",false),e.get("alt",false),e.get("shift",false)]
			elif e.has("button"):
				for key in ["axis","sign","ctrl","alt","shift"]:
					if e.has(key): return {"ok":false,"reason":"pad button has incompatible fields"}
				if not integer(e.button) or e.button < 0 or e.button >= JOY_BUTTON_MAX: return {"ok":false,"reason":"invalid pad button"}
				if e.has("with") and (not integer(e.with) or e.with < 0 or e.with >= JOY_BUTTON_MAX or e.with == e.button): return {"ok":false,"reason":"invalid pad chord"}
				signature = "button:%d:%d" % [e.button,e.get("with",-1)]
			else:
				for key in ["with","ctrl","alt","shift"]:
					if e.has(key): return {"ok":false,"reason":"pad axis has incompatible fields"}
				# JSON remap files represent integral axis signs as floats.
				if not integer(e.axis) or e.axis < 0 or e.axis >= JOY_AXIS_MAX or not integer(e.get("sign")) or absf(float(e.sign)) != 1.0: return {"ok":false,"reason":"invalid pad axis"}
				signature = "axis:%d:%d" % [e.axis,e.sign]
			if used.has(signature) and not ([used[signature],action].has("camera_up") and [used[signature],action].has("inventory")):
				return {"ok":false,"reason":"duplicate binding: " + action + "/" + used[signature]}
			used[signature] = action
	return {"ok":true,"profile":d}

# Upgrade only the live saved-settings entry point. validate()/configure() keep
# the exact historical full-profile reducer for input movies and their hashes.
static func saved_profile(raw: Variant) -> Variant:
	var result := validate(raw)
	if not result.ok or result.profile.bindings.has("run"): return raw
	var p: Dictionary=result.profile
	var cfg := {"version":1,"preset":p.preset,"bindings":p.bindings.duplicate(true),"options":p.options.duplicate(),"tuning":p.tuning.duplicate()}
	if cfg.preset=="right" and saved_default_key(cfg.bindings,"dodge",KEY_ALT):
		if not saved_bind_key(cfg.bindings,"dodge",KEY_SPACE): return raw
	if saved_default_key(cfg.bindings,"walk",KEY_SHIFT):
		# Release old Shift first so the newly appended run can claim it.
		cfg.bindings.walk=cfg.bindings.walk.filter(func(e): return not e.has("key"))
		if not saved_bind_key(cfg.bindings,"walk",KEY_ALT): return raw
	if saved_default_key(cfg.bindings,"camera_up",KEY_I):
		if not saved_bind_key(cfg.bindings,"camera_up",KEY_U): return raw
	if not saved_bind_key(cfg.bindings,"run",KEY_SHIFT): return raw
	if not saved_bind_key(cfg.bindings,"camera_recenter",KEY_V): return raw
	if cfg.options.run_mode=="auto": cfg.options.run_mode="hold"
	return cfg

static func saved_default_key(bindings: Dictionary, action: String, code: int) -> bool:
	var keys: Array=bindings.get(action,[]).filter(func(e): return e.has("key"))
	return keys.size()==1 and int(keys[0].key)==code and not keys[0].get("ctrl",false) and not keys[0].get("alt",false) and not keys[0].get("shift",false)

static func saved_key_candidates(preferred: int) -> Array:
	var codes := [preferred,KEY_G,KEY_H,KEY_N,KEY_B,KEY_HOME,KEY_END,KEY_INSERT]
	codes.append_array(range(KEY_A,KEY_Z+1))
	codes.append_array(range(KEY_0,KEY_9+1))
	codes.append_array(range(KEY_F1,KEY_F12+1))
	return codes

static func saved_bind_key(bindings: Dictionary, action: String, preferred: int) -> bool:
	var used := []
	for id in bindings:
		if id==action: continue
		for entry in bindings[id]:
			if entry.has("key"): used.append(int(entry.key))
	for code in saved_key_candidates(preferred):
		if code in used: continue
		bindings[action]=[{"key":code}]+bindings.get(action,[]).filter(func(e): return not e.has("key"))
		return true
	return false # caller preserves the entire original saved profile, not defaults

static func integer(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and float(value) == floorf(float(value))

static func install(profile: Dictionary) -> void:
	for action in profile.bindings:
		for device in ["key","pad"]:
			var name: String = "h64_" + device + "_" + action
			if not InputMap.has_action(name): InputMap.add_action(name, 0.0)
			InputMap.action_erase_events(name)
			for b in profile.bindings[action]:
				if b.has("key") != (device == "key"): continue
				var e: InputEvent
				if b.has("key"):
					e = InputEventKey.new(); e.physical_keycode = int(b.key)
					e.ctrl_pressed = b.get("ctrl",false); e.alt_pressed = b.get("alt",false); e.shift_pressed = b.get("shift",false)
				elif b.has("button"):
					e = InputEventJoypadButton.new(); e.button_index = int(b.button)
				else:
					e = InputEventJoypadMotion.new(); e.axis = int(b.axis); e.axis_value = float(b.sign)
				InputMap.action_add_event(name, e)
