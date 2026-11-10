extends Node
## Deterministic input movie v1. All state checks happen after the physics consumers.
const Wire = preload("res://core/wire.gd")
const Profile = preload("res://input/profile.gd")
var view
var recording := false
var playing := false
var finished := false
var result := {}
var movie := {}
var cursor := 0
var path := ""
var quit_on_finish := false
var observed := []
var extensions := {}

func checkpoint_hash() -> Dictionary:
	var snapshot := state()
	var fields := {}
	for key in snapshot: fields[key] = digest(snapshot[key])
	var row := {"tick":cursor,"hash":digest(snapshot),"fields":fields}
	if view.options.get("replay_trace",false): row["state"] = snapshot
	return row

func attach(presenter) -> void:
	view = presenter
	process_physics_priority = 100

static func vec(v: Vector3) -> Array: return [v.x,v.y,v.z]
static func v3(a: Array) -> Vector3: return Vector3(a[0],a[1],a[2])
static func basis(b: Basis) -> Array: return [vec(b.x),vec(b.y),vec(b.z)]
static func b3(a: Array) -> Basis: return Basis(v3(a[0]),v3(a[1]),v3(a[2]))
static func digest(data: Variant) -> String: return JSON.stringify(data,"",true,true).sha256_text()

func build_hash() -> String:
	var files := ["res://main.gd","res://project.godot"]
	for directory in ["res://input","res://view","res://core","res://actors","res://modules","res://modules/combat","res://modules/course","res://modules/regions"]:
		for name in DirAccess.get_files_at(directory):
			if name.ends_with(".gd") or name.ends_with(".json"): files.append(directory.path_join(name))
	for entry in extensions.values():
		var object: Object = entry[0].get_object()
		if object != null and object.get_script() != null:
			var script_path: String = object.get_script().resource_path
			if script_path not in files: files.append(script_path)
	files.sort()
	var content: String = Engine.get_version_info().string
	for file in files: content += file + ":" + FileAccess.get_sha256(file) + "\n"
	return content.sha256_text()

func register_state(id: String, capture: Callable, restore_state: Callable) -> void:
	assert(not recording and not playing and not extensions.has(id))
	extensions[id] = [capture,restore_state]

func state() -> Dictionary:
	var p = view.player
	var extra := {}
	for id in extensions: extra[id] = extensions[id][0].call()
	var snapshot := {
		"story":view.codec.pack(view.runtime),
		"player":{"position":vec(p.position),"velocity":vec(p.velocity),"actual":vec(p.actual_velocity),"desired":vec(p.desired_velocity),"yaw":p.facing_yaw,"basis":basis(p.camera_basis),"latched_basis":basis(p.latched_basis),"last_input":[p.last_input.x,p.last_input.y],"latched":p.latched},
		"actions":view.actions.snapshot(),"camera":view.camera_index,
		"menu_open":view.menu_open,"menu_index":view.menu_index,"inventory":view.n64_ui.inv_open,"page_index":view.page_index,
		"focus_id":view.focus_id,"target_id":view.contextual.target_id,"checkpoint":view.checkpoint.duplicate(true),
		"belt":{"enabled":view.belt.enabled,"paused":view.belt.paused,"settings_open":view.belt.settings_open,"slow":view.belt.slow,"phase":view.belt.phase,"sim_tick":view.belt.sim_tick},
		"extensions":extra
	}
	# Additive only for the new modal: old movie state hashes stay byte-identical.
	if view.narration_pending: snapshot["presentation"] = {"narration":view.last_text}
	return snapshot

func restore_state(s: Dictionary) -> Dictionary:
	var loaded: Dictionary = view.codec.load_into(view.runtime,s.story)
	if not loaded.ok: return loaded
	view.enter_room(""); view.refresh()
	view.select_camera(int(s.camera))
	var p = view.player
	p.position = v3(s.player.position); p.set_facing_yaw(s.player.yaw)
	p.velocity = v3(s.player.velocity); p.actual_velocity = v3(s.player.actual); p.desired_velocity = v3(s.player.desired)
	p.camera_basis = b3(s.player.basis); p.latched_basis = b3(s.player.latched_basis)
	p.last_input = Vector2(s.player.last_input[0],s.player.last_input[1]); p.latched = s.player.latched
	view.menu_open = s.menu_open; view.menu_index = int(s.menu_index); view.n64_ui.inv_open = s.inventory; view.page_index = int(s.page_index)
	view.focus_id = s.focus_id; view.contextual.target_id = s.target_id; view.checkpoint = s.checkpoint.duplicate(true)
	# Stored physical vectors must re-enter the native float32 domain, just like
	# player transforms; JSON's decimal parser otherwise retains a double ULP.
	view.checkpoint.position = vec(v3(view.checkpoint.position))
	view.checkpoint.yaw = Vector2(view.checkpoint.yaw,0).x
	for k in s.belt: view.belt.set(k,s.belt[k])
	view.narration_pending = s.has("presentation")
	if view.narration_pending:
		view.last_text = s.presentation.narration
		view.text_label.text = view.last_text
	view.actions.restore(s.actions)
	view.sync_n64_ui(); view.sync_input_context()
	for id in extensions:
		if not s.extensions.has(id): return {"ok":false,"reason":"missing module state " + id}
		extensions[id][1].call(s.extensions[id])
	return {"ok":true}

func start_record(destination: String, seed_value := 7) -> Dictionary:
	if recording or playing: return {"ok":false,"reason":"movie already active"}
	if view.runtime.modules != null and not preload("res://modules/save_codec.gd").new().safe(view.runtime,view.runtime.state):
		return {"ok":false,"reason":"begin module movies at a safe checkpoint"}
	path = destination
	var cfg := {"version":1,"preset":view.actions.profile.preset,"bindings":view.actions.profile.bindings.duplicate(true),"options":view.actions.profile.options.duplicate(),"tuning":view.actions.profile.tuning.duplicate()}
	movie = {"header":{"version":1,"tick_rate":60,"game_hash":view.runtime.game.game_hash,"build_hash":build_hash(),"seed":seed_value,"profile":cfg,"initial":state()},"frames":[],"hashes":[]}
	recording = true; cursor = 0; finished = false; observed = []
	return {"ok":true,"path":path}

func stop_record() -> Dictionary:
	if not recording: return {"ok":false,"reason":"not recording"}
	recording = false
	if cursor == 0: return {"ok":false,"reason":"empty movie"}
	if movie.hashes.is_empty() or int(movie.hashes[-1].tick) != cursor: movie.hashes.append(checkpoint_hash())
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path+".tmp",FileAccess.WRITE)
	if file == null: return {"ok":false,"reason":"cannot write movie"}
	file.store_string(JSON.stringify(movie,"",true,true)); file.close()
	var error := DirAccess.rename_absolute(path+".tmp",path)
	print("MOVIE recorded ticks=%d hashes=%d path=%s" % [cursor,movie.hashes.size(),path])
	return {"ok":error == OK,"path":path,"ticks":cursor}

func toggle_record() -> void:
	if playing: return
	if recording: call_deferred("stop_record")
	else: call_deferred("start_record",view.options.get("record","user://replays/session.h64movie.json"),7)

static func finite_number(value: Variant) -> bool:
	return (value is int or value is float) and is_finite(float(value)) and absf(float(value)) < 1.0e12

static func number_array(value: Variant, size: int) -> bool:
	if not value is Array or value.size() != size: return false
	return value.all(finite_number)

static func shaped(value: Variant, template: Variant) -> bool:
	if template is bool: return value is bool
	if template is int: return Profile.integer(value)
	if template is float: return finite_number(value)
	if template is String: return value is String
	if template is Array:
		if not value is Array or value.size() != template.size(): return false
		for i in template.size():
			if not shaped(value[i],template[i]): return false
		return true
	if template is Dictionary:
		if not value is Dictionary or value.size() != template.size(): return false
		for key in template:
			if not value.has(key) or not shaped(value[key],template[key]): return false
		return true
	return false

func valid_initial(s: Dictionary) -> bool:
	if s.has("presentation"):
		var p = s.presentation
		if not p is Dictionary or p.size()!=1 or not p.get("narration") is String or p.narration.length()>65536: return false
	for key in ["story","player","actions","checkpoint","belt","extensions"]:
		if not s.get(key) is Dictionary: return false
	var expected: Dictionary = state()
	if not shaped(s.player,expected.player) or not shaped(s.belt,expected.belt): return false
	for key in ["camera","menu_index","page_index"]:
		if not Profile.integer(s.get(key)) or s[key] < 0 or s[key] > 100000: return false
	for key in ["menu_open","inventory"]:
		if not s.get(key) is bool: return false
	for key in ["focus_id","target_id"]:
		if not s.get(key) is String: return false
	var a: Dictionary = s.actions
	if a.has("run_toggle") and not a.run_toggle is bool: return false
	for key in ["tick","reset_ticks"]:
		if not Profile.integer(a.get(key)) or a[key] < 0: return false
	for key in ["move","key_direction"]:
		if not number_array(a.get(key),2): return false
	if not finite_number(a.get("stick")) or a.stick<0 or a.stick>1: return false
	for key in ["focus_toggle","walk_toggle","blocked_move"]:
		if not a.get(key) is bool: return false
	if a.get("context") not in ["gameplay","menu","dialogue","inventory","pause"] or a.get("active_device") not in ["key","pad"]: return false
	var names: Array = view.actions.NAMES + Profile.BUTTONS + Profile.DIRECTIONS + ["confirm","nav_up","nav_down","nav_left","nav_right"]
	if not a.get("raw_previous") is Array: return false
	for name in a.raw_previous:
		if name not in names: return false
	for key in ["held","edges","buffers","key_order"]:
		if not a.get(key) is Dictionary: return false
		for name in a[key]:
			if name not in names: return false
			if key in ["held","edges"]:
				if not a[key][name] is bool: return false
			elif not Profile.integer(a[key][name]): return false
	var checkpoint: Dictionary = s.checkpoint
	if not checkpoint.get("story") is Dictionary or not number_array(checkpoint.get("position"),3) or not finite_number(checkpoint.get("yaw")) or not Profile.integer(checkpoint.get("camera")): return false
	for story in [s.story,checkpoint.story]:
		for key in ["contract_version","spec_hash","game_hash"]:
			if not story.get(key) is String: return false
		if view.runtime.modules != null:
			var probe = preload("res://core/runtime.gd").new()
			if not probe.configure(view.runtime.game).ok or not view.codec.load_into(probe,story).ok: return false
		elif not view.codec.validate_shape(view.runtime,story).ok: return false
	if s.extensions.size()!=extensions.size(): return false
	if view.module_host != null:
		var m = s.extensions.get("modules")
		if not m is Dictionary or m.get("finite") != s.story.get("state"): return false
		var shape: Dictionary = view.module_host.capture_state()
		var clean: Dictionary = m.duplicate(true)
		clean.finite = shape.finite
		if not shaped(clean,shape) or m.active_id != "" or not m.pending.is_empty() or not m.combat.is_empty() or not m.course.is_empty() or m.course_roll_age != -1: return false
	for key in extensions:
		if not s.extensions.has(key): return false
	return true

func validate_movie(value: Variant) -> Dictionary:
	if not value is Dictionary or not value.get("header") is Dictionary or not value.get("frames") is Array or not value.get("hashes") is Array: return {"ok":false,"reason":"invalid movie shape"}
	var h: Dictionary = value.header
	if not Profile.integer(h.get("version")) or not Profile.integer(h.get("tick_rate")) or int(h.version) != 1 or int(h.tick_rate) != 60: return {"ok":false,"reason":"unsupported movie version/tick rate"}
	if not h.get("game_hash") is String or not h.get("build_hash") is String: return {"ok":false,"reason":"invalid header hash types"}
	if h.game_hash != view.runtime.game.game_hash or h.build_hash != build_hash(): return {"ok":false,"reason":"movie game/build hash mismatch"}
	if not Profile.integer(h.get("seed")) or not h.get("initial") is Dictionary: return {"ok":false,"reason":"invalid seed/initial state"}
	if not Profile.validate(h.get("profile")).ok: return {"ok":false,"reason":"invalid recorded profile"}
	for k in ["story","player","actions","camera","menu_open","menu_index","inventory","page_index","focus_id","target_id","checkpoint","belt","extensions"]:
		if not h.initial.has(k): return {"ok":false,"reason":"incomplete initial state"}
	if not valid_initial(h.initial): return {"ok":false,"reason":"invalid initial controller/module state"}
	if value.frames.is_empty() or value.frames.size() > 216000: return {"ok":false,"reason":"movie tick count out of bounds"}
	for frame in value.frames:
		if not frame is Dictionary: return {"ok":false,"reason":"invalid input frame"}
		for k in frame:
			if k not in ["digital","buttons","analog","camera","heading"]: return {"ok":false,"reason":"unknown input field"}
		if frame.has("heading"):
			var hd = frame.heading
			if not hd is Array or hd.size() != 2 or not finite_number(hd[0]) or absf(float(hd[0])) > 3.2 or not (hd[1] is int or hd[1] is float) or not float(hd[1]) in [0.0,1.0]: return {"ok":false,"reason":"invalid view heading"}
		for key in ["digital","buttons"]:
			if not frame.get(key,[]) is Array: return {"ok":false,"reason":"invalid held actions"}
			for action in frame.get(key,[]):
				if action not in Profile.BUTTONS + Profile.DIRECTIONS + ["confirm"]: return {"ok":false,"reason":"unknown recorded action"}
		for key in ["analog","camera"]:
			var a = frame.get(key,[0,0])
			if not a is Array or a.size()!=2: return {"ok":false,"reason":"invalid axis"}
			for n in a:
				if not (n is int or n is float) or not is_finite(float(n)) or absf(n)>1: return {"ok":false,"reason":"axis outside range"}
	var prior := 0
	for row in value.hashes:
		if not row is Dictionary or not Profile.integer(row.get("tick")) or int(row.tick)<=prior or int(row.tick)>value.frames.size() or int(row.tick)-prior>60 or not row.get("hash") is String or row.hash.length()!=64: return {"ok":false,"reason":"invalid/sparse state hashes"}
		prior = int(row.tick)
	if prior != value.frames.size(): return {"ok":false,"reason":"missing final hash"}
	return {"ok":true}

func load_movie(file_path: String, auto_quit := true) -> Dictionary:
	if not FileAccess.file_exists(file_path) or FileAccess.get_file_as_bytes(file_path).size()>64*1024*1024: return {"ok":false,"reason":"missing/oversized movie"}
	return begin_playback(Wire.read_json(file_path),auto_quit)

func begin_playback(value: Variant, auto_quit := false) -> Dictionary:
	var valid := validate_movie(value)
	if not valid.ok: return valid
	if recording: return {"ok":false,"reason":"recording is active"}
	movie = value.duplicate(true)
	view.actions.configure(movie.header.profile)
	view.player.tuning = view.actions.profile.tuning.duplicate()
	view.actions.set_source("replay")
	var restored := restore_state(movie.header.initial)
	if not restored.ok: return restored
	view.set_physics_process(true); view.player.set_physics_process(true)
	view.actions.frame_provider = next_frame
	cursor = 0; observed = []; result = {}; finished = false; playing = true; quit_on_finish = auto_quit
	return {"ok":true}

func next_frame() -> Dictionary:
	if not playing or cursor >= movie.frames.size(): return {}
	return movie.frames[cursor]

func _physics_process(_delta: float) -> void:
	if recording:
		movie.frames.append(view.actions.last_frame.duplicate(true)); cursor += 1
		if cursor % 60 == 0: movie.hashes.append(checkpoint_hash())
	elif playing:
		cursor += 1
		for expected in movie.hashes:
			if int(expected.tick) == cursor:
				var actual := digest(state())
				observed.append({"tick":cursor,"hash":actual})
				if actual != expected.hash:
					var current := state()
					var changed := {}
					for key in expected.get("fields",{}):
						if expected.fields[key] != digest(current[key]): changed[key] = current[key]
					finish({"ok":false,"tick":cursor,"expected":expected.hash,"actual":actual,"reason":"first divergent state checkpoint","actual_fields":changed}); return
		if cursor >= movie.frames.size(): finish({"ok":true,"ticks":cursor,"hashes":observed})

func finish(value: Dictionary) -> void:
	playing = false; finished = true; result = value
	view.actions.frame_provider = Callable()
	# Keep the final sampled state immutable while the caller inspects the receipt.
	view.set_physics_process(false); view.player.set_physics_process(false)
	print("MOVIE VERIFY ",JSON.stringify(result,"",true,true))
	if view.options.has("replay_report"):
		var f := FileAccess.open(view.options.replay_report,FileAccess.WRITE)
		if f != null: f.store_string(JSON.stringify(result,"",true,true)); f.close()
	if quit_on_finish: view.quit_cleanly(0 if result.ok else 1)
