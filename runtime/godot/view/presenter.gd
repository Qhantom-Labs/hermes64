extends Node
## Thin presentation adapter. All logical actions pass through runtime.step().
signal room_entered(room_id: String)
signal camera_cut(camera_id: String)
signal state_changed(result: Dictionary)
signal ending_reached(ending_id: String)
const Runtime = preload("res://core/runtime.gd")
const Wire = preload("res://core/wire.gd")
const SaveCodec = preload("res://core/save_codec.gd")
const Room = preload("res://view/room.gd")
const Player = preload("res://view/player.gd")
const Assets = preload("res://view/assets.gd")
var runtime
var codec = SaveCodec.new()
var resolver = Assets.new()
var room_root: Node3D
var camera: Camera3D
var camera_index := 0
var player
var action_buttons: Dictionary = {}
var followers: Dictionary = {}
var viewport: SubViewport
var surface: TextureRect
var world: Node3D
var status_label: Label
var title_label: Label
var text_label: Label
var action_list: VBoxContainer
var options := {}
var theme: Dictionary = {}
var last_text := ""
var frame_samples := []
var build_samples := []
var cut_count := 0
var save_path := ""
var ui_root: Control
var n64_ui
var text_pages := []
var page_index := 0
var menu_open := false
var menu_index := 0
var ui_actions := []
var sounds
var world_env: WorldEnvironment
var actions
var contextual = preload("res://input/context.gd").new()
var belt = preload("res://input/toolbelt.gd").new()
var controls_hud
var key_overlay # UI5: integer-scale pause menu, keycap prompt and corner hint (input/key_overlay.gd)
var simulation_enabled := true
var focus_id := ""
var current_candidate := {}
var checkpoint := {}
var replay
var module_host
# Read pages before re-interacting; this is presentation state, not story state.
var narration_pending := false
var follow_camera
var room_transition
var entry_error := ""
var transition_action := ""
var transition_prior_simulation := true
var transition_process_gates := []
var transition_hud_gates := []
var transition_look_pending := false
var scene_cards
# GAPS2 G9: metadata.presentation.text_boxes=false (arena_run_v1 / story-file games) shows no room description,
# narration, event or ending text box; subtitles/titles/labels come only from scene cards. Absent = old behaviour.
var text_boxes := true

func boxed(text: String) -> String:
	return text if text_boxes else ""

func finalize_room_entry() -> Dictionary:
	var placed: Dictionary = player.place_in_room(room_root)
	if not placed.ok:
		entry_error = str(placed.reason)
		simulation_enabled=false; player.simulation_enabled=false; player.enabled=false
		push_error("FEEL2 unsafe entry: "+entry_error)
		return placed
	room_root.update_interaction_targets(player.position)
	return placed

func begin_room_transition(id: String, source_room: Dictionary) -> void:
	if room_transition == null or not id.begins_with("move:"): return
	var door_id: String=id.get_slice(":",2)
	for door in source_room.doors:
		if door.id != door_id: continue
		var at: Vector3=room_root.target_anchors.get(id,Room.door_position(door,source_room.grid_size))
		var outward: Vector3={"north":Vector3.FORWARD,"south":Vector3.BACK,"west":Vector3.LEFT,"east":Vector3.RIGHT}.get(door.wall,Vector3.BACK)
		if not room_transition.begin(world,drawing_camera(),player.get_node_or_null("visual"),at,outward,actions.profile.options.reduced_motion): return
		transition_action=id; transition_prior_simulation=simulation_enabled
		transition_hud_gates=[]
		for hud in [n64_ui,controls_hud,key_overlay,module_host.hud if module_host != null else null]:
			if is_instance_valid(hud): transition_hud_gates.append([hud,hud.visible]); hud.visible=false
		lock_transition_input()
		return

func lock_transition_input() -> void:
	simulation_enabled=false; player.simulation_enabled=false; player.enabled=false
	actions.set_context("pause")

func transition_entry() -> void:
	# Regions set their validated checkpoint after commit_portal returns. Ordinary
	# doors instead reapply their reciprocal entry after actor bridge subscribers.
	if not (module_host != null and runtime.modules.catalogue.has("regions")):
		var source: Dictionary=runtime.rooms[transition_action.get_slice(":",1)]
		var dest: Dictionary=runtime.rooms[runtime.state.location]
		for door in source.doors:
			if door.id != transition_action.get_slice(":",2): continue
			for arrival in dest.doors:
				if arrival.id == door.to_door:
					var at: Vector3=room_root.target_anchors.get("move:"+dest.id+":"+arrival.id,Room.door_position(arrival,dest.grid_size))
					player.position=Vector3(at.x,0.1,at.z).lerp(Vector3(dest.grid_size[0]/2.0,0.1,dest.grid_size[1]/2.0),0.17)
	if not finalize_room_entry().ok: return
	lock_transition_input()
	if follow_camera != null:
		# Puzzle uses authored framing but still needs its presentation samples
		# reseeded under black, before the first destination reveal frame.
		follow_camera.reset(); simulation_enabled=true
		follow_camera._physics_process(0.0); simulation_enabled=false
	n64_ui.hide_dialog()

func transition_freeze() -> void:
	transition_process_gates=[]
	var nodes: Array=[self,actions,player,replay,module_host,follow_camera]
	for child in get_children():
		if child.get_script()!=null and child.get_script().resource_path.ends_with("actors/bridge.gd"): nodes.append(child)
	for node in nodes:
		if is_instance_valid(node):
			transition_process_gates.append([node,node.is_physics_processing()])
			node.set_physics_process(false)

func transition_black() -> void:
	if transition_look_pending: apply_room_look(); transition_look_pending=false
	if DisplayServer.get_name() != "headless": await RenderingServer.frame_post_draw
	else: await get_tree().process_frame
	# SCENES: an authored travel shot plays inside the held black; the canonical pipeline stays frozen.
	if scene_cards != null: await scene_cards.travel(transition_action)
	if is_instance_valid(room_transition) and room_transition.phase=="black": room_transition.reveal(boxed(runtime.rooms[runtime.state.location].name))

func transition_finished() -> void:
	for gate in transition_process_gates:
		if is_instance_valid(gate[0]): gate[0].set_physics_process(gate[1])
	transition_process_gates=[]
	for gate in transition_hud_gates:
		if is_instance_valid(gate[0]): gate[0].visible=gate[1]
	transition_hud_gates=[]
	simulation_enabled=transition_prior_simulation and entry_error==""
	sync_input_context()
	# The raw neutral fence already proved release. Do not require a second
	# release in the next canonical frame or swallow the first fresh press.
	actions.raw_previous=[]; actions.held.clear(); actions.edges.clear()
	actions.buffers.clear(); actions.blocked_move=false
	transition_action=""
	if scene_cards != null: scene_cards.room_ready(runtime.state.location)

func exploration_camera() -> Camera3D:
	return follow_camera.current() if follow_camera != null else camera

func drawing_camera() -> Camera3D:
	return viewport.get_camera_3d()


func world_environment() -> WorldEnvironment:
	return world_env

func boot(game: Dictionary, opts: Dictionary = {}) -> Dictionary:
	options = opts
	process_physics_priority = -50
	actions = get_node("/root/Actions")
	actions.restore({})
	if options.get("test",false): actions.configure({"version":1})
	belt.configure(options)
	runtime = Runtime.new()
	var result: Dictionary = runtime.configure(game)
	if not result.ok: return result
	var pres_meta = game.metadata.get("presentation", {})
	text_boxes = not (pres_meta is Dictionary and pres_meta.get("text_boxes", true) == false)
	resolver.root = options.get("asset_root", "")
	resolver.mapping = options.get("asset_map", {})
	save_path = options.get("save", ProjectSettings.globalize_path("res://../saves/slot1.json"))
	var pack_path: String = options.get("pack", "res://packs/%s/view.json" % game.metadata.get("style_pack", "default"))
	var loaded_theme = Wire.read_json(pack_path)
	if not loaded_theme is Dictionary:
		loaded_theme = Wire.read_json("res://packs/default/view.json")
	theme = loaded_theme
	var bindings = Wire.read_json(options.get("bindings", "res://bindings.json"))
	if bindings is Dictionary: resolver.configure(bindings, theme)
	else: resolver.configure({"assets":options.get("asset_map",{}),"characters":[]},theme)
	build_screen()
	sounds = preload("res://view/audio.gd").new()
	add_child(sounds)
	sounds.boot("res://audio.json")
	player = Player.new()
	world.add_child(player)
	enter_room("")
	var protagonist: Dictionary = runtime.characters.get(game.metadata.get("protagonist", ""), {})
	var visual = resolver.character(protagonist)
	if visual != null: player.add_child(visual)
	else: visual = room_root.person(player, protagonist.get("params", {}))
	visual.name = "visual"
	last_text = boxed(runtime.rooms[runtime.state.location].description)
	refresh()
	checkpoint = physical_checkpoint()
	controls_hud = preload("res://input/hud.gd").new()
	controls_hud.presenter = self
	viewport.add_child(controls_hud)
	var key_layer := CanvasLayer.new()
	key_layer.layer = 2
	add_child(key_layer)
	key_overlay = preload("res://input/key_overlay.gd").new()
	key_layer.add_child(key_overlay)
	key_overlay.setup(self)
	replay = preload("res://input/movie.gd").new()
	add_child(replay)
	replay.attach(self)
	if runtime.modules != null:
		module_host = preload("res://modules/host.gd").install(self, actions)
		if module_host.binding_error != "": return {"ok":false,"reason":module_host.binding_error}
		module_host.control_claimed.connect(module_claimed)
		module_host.control_released.connect(module_released)
		module_host.story_event.connect(module_event)
		replay.register_state("modules",module_host.capture_state,module_host.restore_state)
		checkpoint = physical_checkpoint()
	follow_camera = preload("res://view/follow_camera.gd").new()
	add_child(follow_camera)
	follow_camera.attach(self)
	room_transition=preload("res://view/room_transition.gd").new()
	viewport.add_child(room_transition)
	room_transition.set_width(viewport.size.x)
	room_transition.entry_requested.connect(transition_entry)
	room_transition.freeze_requested.connect(transition_freeze)
	room_transition.black_reached.connect(transition_black)
	room_transition.finished.connect(transition_finished)
	room_transition.release_provider=func(): return actions.sample_live() if actions.source=="live" else {}
	room_transition.release_dead_zone=float(actions.profile.tuning.dead_zone_pad)
	scene_cards=preload("res://view/scene_cards.gd").new()
	add_child(scene_cards)
	scene_cards.attach(self)
	preload("res://view/goal_cue.gd").install(self)   # FEEL4: next-goal marker (arena_run_v1/premise games)
	preload("res://input/controls_hint.gd").install(self)   # FEEL4: keycap controls hint (arena_run_v1/premise games)
	if not finalize_room_entry().ok: return {"ok":false,"reason":entry_error}
	return {"ok": true}

func module_claimed(_owner: String, _generation: int) -> void:
	contextual.target_id = ""; focus_id = ""; current_candidate = {}
	player.focus_point = null
	actions.buffers.clear()
	module_host.prepare_motion()

func module_released(_generation: int) -> void:
	player.focus_point = null
	contextual.target_id = ""; focus_id = ""; current_candidate = {}
	actions.buffers.clear()

func module_event(kind: String, payload: Dictionary) -> void:
	# Observable presentation event, not a story command or analysis outcome.
	if sounds != null: sounds.on_event(kind, payload)   # AUDIOPIPE: boss/wave/event music + voice hooks
	if key_overlay != null: key_overlay.on_event(kind)   # UI5: corner hint when a move first matters
	# Boss beats (COMBAT lane) are hooks for dialogue/region data; mid-fight they show no UI (the combat stage plays
	# the burst, cue and hit-stop) and must not reopen the narration panel. encounter_cleared follows the defeat.
	if kind in ["boss_phase", "boss_defeated"]:
		set_meta("last_module_event", {"kind": kind, "payload": payload.duplicate(true)})
		return
	var labels := {"encounter_cleared":"Arena cleared", "course_completed":"Course complete", "challenge_failed":"Retrying checkpoint", "checkpoint_ready":"Checkpoint ready", "region_unlocked":"Region reached"}
	var quiet: bool = (kind == "encounter_cleared" and module_host != null and module_host.get("quiet_clear") == true) or not text_boxes
	if labels.has(kind) and not quiet:
		last_text = labels[kind]
		text_label.text = last_text
	# The checkpoint icon is a promise: only flash it when a real safe checkpoint
	# was taken (hold-R then returns here, never to a pre-challenge state).
	if kind in ["checkpoint_ready","course_completed","encounter_cleared"] and preload("res://modules/save_codec.gd").new().safe(runtime,runtime.state):
		checkpoint = physical_checkpoint()
		belt.checkpoint_ticks = int(actions.profile.tuning.checkpoint_icon_ticks)
	sync_n64_ui()
	# A 1.1.0 fight ends on its own defeat beat: no text panel pops up over it (the HUD and checkpoint icon still update).
	if kind == "challenge_started" or quiet: n64_ui.hide_dialog()
	set_meta("last_module_event",{"kind":kind,"payload":payload.duplicate(true)})

func label_at(parent: Node, pos: Vector2, size: Vector2, font_size: int) -> Label:
	var label := Label.new()
	label.position = pos
	label.size = size
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", Color.from_string(theme.palette.ui_text, Color.WHITE))
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	parent.add_child(label)
	return label

func scrolling_text(pos: Vector2, size: Vector2, font_size: int) -> Label:
	var scroll := ScrollContainer.new()
	scroll.position = pos
	scroll.size = size
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	ui_root.add_child(scroll)
	var label := label_at(scroll, Vector2.ZERO, Vector2.ZERO, font_size)
	label.custom_minimum_size.x = size.x - 16
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.size_flags_vertical = Control.SIZE_SHRINK_BEGIN
	return label

func build_screen() -> void:
	viewport = SubViewport.new()
	viewport.size = Vector2i(320, 240)
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	# N64 look convention (theme "n64".output): polygon-edge antialiasing like the RDP's coverage AA; legacy packs
	# without the convention keep aliased edges and the nearest-neighbour upscale exactly as before.
	var out_cfg: Dictionary = theme.get("n64", {}).get("output", {})
	viewport.msaa_3d = Viewport.MSAA_4X if str(out_cfg.get("edge_aa", "none")) == "msaa_4x" else Viewport.MSAA_DISABLED
	add_child(viewport)
	world = Node3D.new()
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color.from_string(theme.fog.color, Color.GRAY)
	world.add_child(environment)
	world_env = environment
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-55, -30, 0)
	world.add_child(light)
	ui_root = Control.new()
	add_child(ui_root)
	var bg := ColorRect.new()
	bg.color = Color.from_string(theme.palette.ui_bg, Color.BLACK)
	bg.size = Vector2(960, 720)
	ui_root.add_child(bg)
	var image := TextureRect.new()
	image.position = Vector2(16, 70)
	image.size = Vector2(640, 480)
	image.texture = viewport.get_texture()
	image.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	ui_root.add_child(image)
	title_label = label_at(ui_root, Vector2(16, 8), Vector2(920, 42), 24)
	text_label = scrolling_text(Vector2(16, 563), Vector2(640, 137), 17)
	status_label = scrolling_text(Vector2(672, 64), Vector2(272, 150), 15)
	var scroll := ScrollContainer.new()
	scroll.position = Vector2(672, 220)
	scroll.size = Vector2(272, 414)
	ui_root.add_child(scroll)
	action_list = VBoxContainer.new()
	action_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(action_list)
	var help := label_at(ui_root, Vector2(672, 644), Vector2(272, 66), 13)
	help.text = "WASD move · C camera\nTab/Enter or click an action\nF5 save · F9 load · R restart"
	# Keep accessible action controls for bots; the shipped screen is the LOOK lane 320x240 UI.
	ui_root.visible = false
	surface = TextureRect.new()
	surface.size = Vector2(960,720)
	surface.texture = viewport.get_texture()
	# the 320x240 frame is shown 3x; the convention's bilinear upscale gives the soft TV-like output (no sharpening)
	surface.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR if str(out_cfg.get("upscale_filter", "nearest")) == "bilinear" else CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(surface)
	preload("res://look/pack.gd").current = theme
	n64_ui = preload("res://look/ui.gd").new()
	viewport.add_child(n64_ui)
	get_viewport().size_changed.connect(resize_screen)
	resize_screen()

func resize_screen() -> void:
	var rect: Vector2 = get_viewport().get_visible_rect().size
	if rect.y <= 0: return
	surface.size = rect
	# Keep 240 scanlines and the existing filtering; add horizontal pixels, never
	# stretch a 4:3 picture. At 720p the low-res frame is still upscaled 3x.
	viewport.size = Vector2i(maxi(240,roundi(240.0*rect.x/rect.y)),240)
	n64_ui.set_width(viewport.size.x)
	if room_transition != null: room_transition.set_width(viewport.size.x)
	if runtime != null and text_label != null and not runtime.state.is_empty(): sync_n64_ui()

func enter_room(from_action: String) -> void:
	var started := Time.get_ticks_usec()
	if room_root != null:
		world.remove_child(room_root)
		room_root.queue_free()
	room_root = Room.new()
	room_root.theme = theme
	var room: Dictionary = runtime.rooms[runtime.state.location]
	room_root.build(room, runtime, resolver)
	world.add_child(room_root)
	room_root.settle()
	room_root.frame_people()
	room_root.ensure_accent()
	room_root.blob_shadows()
	if room_transition != null and room_transition.active(): transition_look_pending=true
	else: apply_room_look()
	if sounds != null: sounds.on_scene(runtime.state.location)   # AUDIOPIPE: per-scene music (presentation only)
	for entry in room_root.camera_nodes:
		if entry.node.position.distance_to(entry.target) > 0.01:
			entry.node.look_at(entry.target)
	player.bounds = Vector2(room.grid_size[0], room.grid_size[1])
	player.position = Vector3(room.grid_size[0] / 2.0, 0.1, room.grid_size[1] * 0.7)
	var centre := Vector3(room.grid_size[0] / 2.0, 0.1, room.grid_size[1] / 2.0)
	if not room_root.shell_info.is_empty() and not room_root.camera_nodes.is_empty():
		# enclosed shell + inside camera: start in the middle ground, not at the lens
		var cam_pos: Vector3 = room_root.camera_nodes[0].node.position
		player.position = centre.lerp(Vector3(cam_pos.x, 0.1, cam_pos.z), 0.2)
	var authored_start: Array = room_root.presentation.get("player_start", [])
	if authored_start.size() == 3:
		player.position = Room.vector(authored_start) + Vector3.UP * 0.1
	if from_action.begins_with("move:"):
		var parts := from_action.split(":")
		var old: Dictionary = runtime.rooms[parts[1]]
		for door in old.doors:
			if door.id == parts[2]:
				for destination in room.doors:
					if destination.id == door.to_door:
						var at: Vector3 = room_root.target_positions.get("move:" + room.id + ":" + destination.id, Room.door_position(destination, room.grid_size))
						player.position = Vector3(at.x, 0.1, at.z).lerp(centre, 0.17)
	contextual.target_id = ""
	focus_id = ""; current_candidate = {}
	player.focus_point = null
	player.velocity = Vector3.ZERO
	player.actual_velocity = Vector3.ZERO
	player.last_input = Vector2.ZERO
	player.latched = false
	camera_index = -1
	var preferred: String = room_root.presentation.get("camera", "")
	var initial_camera := 0
	for i in room_root.camera_nodes.size():
		if room_root.camera_nodes[i].id == preferred: initial_camera = i
	select_camera(initial_camera)
	if follow_camera != null:
		follow_camera.enabled = true; follow_camera.anchor_steps = 0; follow_camera.reset()
	warm_room_shaders()
	build_samples.append((Time.get_ticks_usec() - started) / 1000.0)
	room_entered.emit(runtime.state.location)
	if room_transition == null or not room_transition.active(): finalize_room_entry()

## GL Compatibility (the exported builds' renderer) compiles each material variant the
## first time it is drawn: 70-400 ms stalls on macOS OpenGL whenever a new object first
## enters the camera's view. On a room's first entry, draw the whole world once off-screen
## from a top-down orthographic camera (same World3D, same viewport settings), so those
## compiles land in the room-entry frame instead of mid-walk. Never displayed; no state.
var warmed_rooms := {}
func warm_room_shaders() -> void:
	if RenderingServer.get_current_rendering_method() != "gl_compatibility" or DisplayServer.get_name() == "headless": return
	var id: String = runtime.state.location
	if warmed_rooms.has(id): return
	warmed_rooms[id] = true
	var box := AABB()
	var found := false
	for n in world.find_children("*", "VisualInstance3D", true, false):
		if not n.is_visible_in_tree(): continue
		var b: AABB = n.global_transform * n.get_aabb()
		box = box.merge(b) if found else b
		found = true
	if not found: return
	var warm := SubViewport.new()
	warm.name = "shader_warmup"
	warm.world_3d = viewport.find_world_3d()
	warm.size = viewport.size
	for property in ["msaa_3d", "screen_space_aa", "use_debanding", "use_hdr_2d", "transparent_bg", "scaling_3d_mode", "scaling_3d_scale", "positional_shadow_atlas_size", "use_taa", "use_occlusion_culling", "mesh_lod_threshold"]:
		warm.set(property, viewport.get(property))
	warm.render_target_update_mode = SubViewport.UPDATE_ONCE
	var cam := Camera3D.new()
	cam.projection = Camera3D.PROJECTION_ORTHOGONAL
	cam.size = maxf(box.size.x, box.size.z) + 2.0
	cam.near = 0.05
	cam.far = box.size.y + 22.0
	cam.position = Vector3(box.get_center().x, box.end.y + 10.0, box.get_center().z)
	cam.rotation = Vector3(-PI / 2.0, 0.0, 0.0)
	var active := viewport.get_camera_3d()
	if active != null:
		for property in ["environment", "attributes", "cull_mask"]:
			cam.set(property, active.get(property))
	warm.add_child(cam)
	add_child(warm)
	cam.current = true
	RenderingServer.frame_post_draw.connect(func(): if is_instance_valid(warm): warm.queue_free(), CONNECT_ONE_SHOT)

## Pack look rig for the current room (no-op for legacy packs without a "look" block).
func apply_room_look() -> void:
	const Rig = preload("res://look/rig.gd")
	if not Rig.has_look(theme):
		# SCALE: a scaled room of a legacy-look pack pushes the pack fog out with the room (presentation "fog":
		# {near, far, optional color, max}; the rest of the legacy look stays the pack's). Rooms without it are untouched.
		var scaled_fog: Dictionary = room_root.presentation.get("fog", {})
		if not scaled_fog.is_empty():
			var pack_fog: Dictionary = theme.get("fog", {})
			var fc := Color.from_string(str(scaled_fog.get("color", pack_fog.get("color", "#333344"))), Color.GRAY)
			RenderingServer.global_shader_parameter_set("n64_fog_color", Vector4(fc.r, fc.g, fc.b, 1))
			RenderingServer.global_shader_parameter_set("n64_fog", Vector4(float(scaled_fog.get("near", pack_fog.get("near", 6))), float(scaled_fog.get("far", pack_fog.get("far", 28))), 1, float(scaled_fog.get("max", 1.0))))
			if scaled_fog.has("sky_fog_scale"):
				for n in room_root.get_children():
					if str(n.get_meta("placed", "")) != "backdrop": continue
					for mi in n.find_children("*", "MeshInstance3D", true, false) + ([n] if n is MeshInstance3D else []):
						for i in mi.mesh.get_surface_count():
							var m = mi.get_surface_override_material(i)
							if m is ShaderMaterial and str(m.get_meta("role", "")) == "sky": m.set_shader_parameter("fog_scale", float(scaled_fog.sky_fog_scale))
		return
	if not Rig.has_profile(theme, room_root.profile_name()):
		# partial look block (e.g. exterior-only): this room keeps the legacy pack look exactly
		resolver.legacy_globals(0.0)
		world_env.environment.background_color = Color.from_string(theme.fog.color, Color.GRAY)
		room_root.set_meta("look_profile", "legacy")
		room_root.set_meta("fog_color", theme.fog.color)
		return
	room_root.gather_lights()
	var p: Dictionary = Rig.profile(theme, room_root.profile_name(), room_root.presentation.get("look", {}))
	if p.has("room") and not (p.room as Dictionary).has("centre"):
		p.room["centre"] = [float(room_root.data.grid_size[0]) / 2.0, float(room_root.data.grid_size[1]) / 2.0]
	Rig.apply(p, room_root.lights)
	var bg := Rig.col(p.get("background", p.get("fog", {}).get("color", theme.fog.color)))
	world_env.environment.background_color = Rig.graded(bg, p)
	room_root.set_meta("look_profile", room_root.profile_name())
	room_root.set_meta("fog_color", Rig.graded(Rig.col(p.get("fog", {}).get("color", theme.fog.color)), p).to_html(false))

## N64 look convention fog.sky_horizon = [from, to] (sin of view elevation, relative to the top of the far
## silhouettes seen from the current camera): the painted sky melts into the fog colour right above the far terrain,
## so the visible horizon and the fogged distance share one colour (no-op without the convention or a backdrop).
func fit_sky_horizon() -> void:
	const Rig = preload("res://look/rig.gd")
	var shz = Rig.conv.get("fog", {}).get("sky_horizon", null)
	if not (shz is Array and shz.size() == 2) or room_root == null or not is_instance_valid(camera): return
	var cam := camera.global_position
	var top := -1.0
	for n in room_root.get_children():
		if not str(n.get_meta("placed", "")) in ["vista", "yard"]: continue
		var a: AABB = Room.world_aabb(n)
		if a.size == Vector3.ZERO: continue
		var c := a.get_center()
		var dist := Vector2(c.x - cam.x, c.z - cam.z).length() + maxf(a.size.x, a.size.z) * 0.5
		var h := a.end.y - cam.y
		top = maxf(top, h / sqrt(dist * dist + h * h))
	top = maxf(top, 0.0)
	room_root.set_meta("sky_horizon", top)
	for n in room_root.get_children():
		if str(n.get_meta("placed", "")) != "backdrop": continue
		for mi in n.find_children("*", "MeshInstance3D", true, false) + ([n] if n is MeshInstance3D else []):
			for i in mi.mesh.get_surface_count():
				var m = mi.get_surface_override_material(i)
				if m is ShaderMaterial and str(m.get_meta("role", "")) == "sky":
					m.set_shader_parameter("horizon_fog", Vector2(top + float(shz[0]), top + float(shz[1])))

func select_camera(index: int) -> void:
	if room_root.camera_nodes.is_empty(): return
	camera_index = posmod(index, room_root.camera_nodes.size())
	var entry: Dictionary = room_root.camera_nodes[camera_index]
	camera = entry.node
	camera.current = true
	fit_sky_horizon()
	player.camera_cut(camera.basis)
	cut_count += 1
	camera_cut.emit(entry.id)

func dispatch(id: String) -> Dictionary:
	if module_host != null:
		if not module_host.allows_action(id): return {"ok":false,"reason":"physical module gate"}
		if id.begins_with("move:") and runtime.modules.catalogue.has("regions"): return module_host.travel(id)
	return commit_portal(id)

func commit_portal(id: String) -> Dictionary:
	var before: Dictionary = runtime.state.duplicate(true)
	var result: Dictionary = runtime.step(id)
	if not result.ok:
		last_text = boxed(result.reason)
		refresh()
		return result
	if sounds != null:
		sounds.trigger()
		sounds.on_action(id)
	var from_menu := menu_open
	menu_open = false
	page_index = 0
	last_text = boxed(result.text)
	# Finishing a conversation closes it, rather than displaying the chosen reply as
	# another nearby interaction. Informational interactions get a dismissible modal.
	if before.dialogue.values().any(func(v): return v != "") and not dialogue_active(): last_text = ""
	narration_pending = not from_menu and id.begins_with("interact:") and not dialogue_active() and runtime.endings(runtime.state).is_empty() and not last_text.strip_edges().is_empty()
	if dialogue_active() and not from_menu: menu_index = 0
	if before.location != runtime.state.location:
		begin_room_transition(id,runtime.rooms[before.location])
		enter_room(id)
		if last_text == "": last_text = boxed(runtime.rooms[runtime.state.location].description)
	elif before.get("collected", []) != runtime.state.get("collected", []):
		var pos: Vector3 = player.position
		enter_room("")
		player.position = pos
		if not finalize_room_entry().ok: return {"ok":false,"reason":entry_error}
	refresh()
	state_changed.emit(result)
	if result.endings.size() == 1: ending_reached.emit(result.endings[0])
	if not result.endings.is_empty() and sounds != null: sounds.on_results()
	return result

func refresh() -> void:
	var st: Dictionary = runtime.state
	var ends: Array = runtime.endings(st)
	title_label.text = runtime.game.title + " / " + runtime.rooms[st.location].name
	var info := PackedStringArray()
	var tide: Dictionary = runtime.game.tide.states[runtime.tide_indices[st.tide.state]]
	info.append("%s · %d/%d waits" % [tide.label, st.tide.tick, tide.duration])
	info.append("Inventory")
	if st.inventory.is_empty(): info.append("—")
	for item in runtime.game.items:
		if st.inventory.has(item.id): info.append(item.name)
	var derived: Dictionary = runtime.derived(st)
	for group in runtime.game.get("collectible_groups", []):
		info.append("%s: %d/%d" % [group.name, derived.counts[group.id], group.required])
	status_label.text = "\n".join(info)
	text_label.text = last_text
	var active := false
	for did in st.dialogue:
		if st.dialogue[did] != "":
			active = true
			text_label.text = runtime.nodes[did][st.dialogue[did]].text
	if ends.size() == 1:
		for ending in runtime.game.endings:
			if ending.id == ends[0]: text_label.text = boxed(ending.text)
		title_label.text += " / " + ends[0]
	elif ends.size() > 1:
		text_label.text = "CONTRACT ERROR: ambiguous terminal " + str(ends)
	player.enabled = not active and ends.is_empty()
	for child in action_list.get_children():
		action_list.remove_child(child)
		child.queue_free()
	action_buttons.clear()
	for action in runtime.actions(st):
		var button := Button.new()
		button.text = action.label
		button.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		button.custom_minimum_size = Vector2(252, 44)
		button.add_theme_font_size_override("font_size", 15)
		button.tooltip_text = action.kind
		button.pressed.connect(func(): dispatch(action.id))
		action_list.add_child(button)
		action_buttons[action.id] = button
	refresh_followers()
	sync_n64_ui()
	sync_input_context()

func sync_n64_ui() -> void:
	if n64_ui == null: return
	var st: Dictionary = runtime.state
	var room: Dictionary = runtime.rooms[st.location]
	var counts: Dictionary = runtime.derived(st).counts
	var labels := PackedStringArray()
	for group in runtime.game.get("collectible_groups", []): labels.append("%s %d/%d" % [group.name,counts[group.id],group.required])
	n64_ui.location_text = room.name
	n64_ui.counter_text = "  ".join(labels)
	n64_ui.set_prompt(false) # Target-attached controls HUD owns the only input prompt.
	var inventory := []
	for item in runtime.game.items:
		if st.inventory.has(item.id): inventory.append({"id":item.id,"name":item.name,"icon":item.get("icon","gear")})
	n64_ui.inv_set(inventory)
	ui_actions = runtime.actions(st)
	var lines: PackedStringArray = n64_ui.font.wrap(text_label.text,280)
	text_pages.clear()
	for i in range(0,lines.size(),3): text_pages.append("\n".join(lines.slice(i,mini(i+3,lines.size()))))
	if text_pages.is_empty(): text_pages.append("")
	page_index = clampi(page_index,0,text_pages.size()-1)
	var choices := []
	if menu_open or (dialogue_active() and page_index == text_pages.size()-1):
		var available: Array = ui_actions if menu_open else conversation_actions()
		menu_index = posmod(menu_index,maxi(1,available.size()))
		var start: int = (menu_index / 4) * 4
		for i in range(start,mini(start+4,available.size())): choices.append(available[i].label)
		n64_ui.show_line("ACTIONS %d/%d" % [menu_index+1,available.size()],n64_ui.C_LAMP,text_pages[page_index],choices)
		n64_ui.skip_typing()
		n64_ui.dlg_sel = menu_index % 4
	else:
		if text_label.text.strip_edges().is_empty(): n64_ui.hide_dialog()
		else: n64_ui.show_line("%s %d/%d" % [runtime.game.title,page_index+1,text_pages.size()],n64_ui.C_LAMP,text_pages[page_index],[])
	var endings: Array = runtime.endings(st)
	if endings.size() == 1 and text_boxes:
		var titles: Dictionary = runtime.game.metadata.get("presentation", {}).get("ending_titles", {})
		n64_ui.show_line(titles.get(endings[0],str(endings[0]).replace("_"," ").capitalize()),n64_ui.C_LAMP,text_pages[page_index],[])
	n64_ui.queue_redraw()
	# Module simulation pauses in a menu, so its HUD will not invalidate itself.
	# Refresh cached drawing commands when the dialogue/header layout changes.
	if module_host != null and module_host.hud != null: module_host.hud.queue_redraw()

func refresh_followers() -> void:
	for cid in runtime.collections:
		var c: Dictionary = runtime.collections[cid]
		var follows: bool = c.follower_flag != "" and runtime.state.collected.has(cid)
		if follows and not followers.has(cid):
			var character: Dictionary = runtime.characters.get(c.character, {})
			var cat = resolver.character(character)
			if cat != null: world.add_child(cat)
			else: cat = room_root.person(world, character.get("params", {}), true)
			cat.name = "follower_" + cid
			cat.position = player.position + Vector3(0.7, 0, 0.7)
			followers[cid] = cat
		elif not follows and followers.has(cid):
			followers[cid].queue_free()
			followers.erase(cid)

func _physics_process(_delta: float) -> void:
	if runtime == null or room_root == null or entry_error!="" or (room_transition != null and room_transition.active()): return
	var delta := 1.0 / 60.0
	input_tick()
	if controls_hud != null: controls_hud.queue_redraw()
	if not simulation_enabled: return
	frame_samples.append(delta * 1000.0)
	if frame_samples.size() > 3600: frame_samples.pop_front()
	var index := 0
	for cid in followers:
		var angle := index * 2.39996
		var distance := 0.9 + 0.16 * index
		var target: Vector3 = player.position + Vector3(cos(angle), 0, sin(angle)) * distance
		followers[cid].position = followers[cid].position.lerp(target, minf(1, delta * 5))
		index += 1
	if room_root.camera_nodes.size() > 1:
		var current_distance: float = Vector2(player.position.x - room_root.camera_nodes[camera_index].target.x, player.position.z - room_root.camera_nodes[camera_index].target.z).length()
		for i in room_root.camera_nodes.size():
			var point: Vector3 = room_root.camera_nodes[i].target
			if Vector2(player.position.x - point.x, player.position.z - point.z).length() + float(actions.profile.tuning.camera_hysteresis_m) < current_distance:
				select_camera(i)
				break

func save_game() -> Dictionary:
	if module_host != null and not preload("res://modules/save_codec.gd").new().safe(runtime,runtime.state):
		return {"ok":false,"reason":"checkpoint only; active attempt is not saved"}
	if actions.source == "replay":
		checkpoint = physical_checkpoint()
		belt.checkpoint_ticks = int(actions.profile.tuning.checkpoint_icon_ticks)
		return {"ok":true,"save":checkpoint.story}
	var value: Dictionary = codec.pack(runtime)
	DirAccess.make_dir_recursive_absolute(save_path.get_base_dir())
	var file := FileAccess.open(save_path + ".tmp", FileAccess.WRITE)
	if file == null: return {"ok": false, "reason": "save open failed"}
	file.store_string(JSON.stringify(value, "\t", true))
	file.close()
	var error := DirAccess.rename_absolute(save_path + ".tmp", save_path)
	if error == OK:
		checkpoint = physical_checkpoint()
		var extra := FileAccess.open(save_path + ".controls.json",FileAccess.WRITE)
		if extra != null: extra.store_string(JSON.stringify(checkpoint,"",true)); extra.close()
		belt.checkpoint_ticks = int(actions.profile.tuning.checkpoint_icon_ticks)
	return {"ok": error == OK, "save": value}

func load_game() -> Dictionary:
	if actions.source == "replay":
		var loaded := restore_checkpoint(checkpoint)
		return loaded
	var value = Wire.read_json(save_path)
	if not value is Dictionary: return {"ok": false, "reason": "missing or invalid save"}
	var result: Dictionary = codec.load_into(runtime, value)
	if result.ok:
		var extra = Wire.read_json(save_path + ".controls.json")
		if extra is Dictionary and extra.get("story",{}) == value:
			result = restore_checkpoint(extra)
		else:
			enter_room(""); refresh()
		if module_host != null and not (extra is Dictionary and extra.get("story",{}) == value): module_host.restore_checkpoint()
		checkpoint = physical_checkpoint()
		belt.checkpoint_ticks = int(actions.profile.tuning.checkpoint_icon_ticks)
	return result

func dialogue_active() -> bool:
	return runtime.state.dialogue.values().any(func(v): return v != "")

func conversation_actions() -> Array:
	# The oracle's sorted legal list includes cancel and wait before choices. Keep
	# that list intact for Tab/replay menus, but don't make E mean "cancel" in talk.
	var choices: Array = ui_actions.filter(func(a): return a.kind == "choose")
	choices.append_array(ui_actions.filter(func(a): return a.kind == "cancel"))
	return choices

func confirm_edge() -> bool:
	# Enter/Space map to confirm in a modal. E held across gameplay -> dialogue
	# synthesizes a confirm edge next tick, but must not count as a SECOND press.
	return actions.just_pressed("primary") or (actions.just_pressed("confirm") and not actions.is_pressed("primary"))

func sync_input_context() -> void:
	if room_transition != null and room_transition.active():
		lock_transition_input(); return
	var mode := "pause" if belt.settings_open else ("menu" if menu_open else ("dialogue" if dialogue_active() or narration_pending else ("inventory" if n64_ui.inv_open else "gameplay")))
	actions.set_context(mode)
	if sounds != null: sounds.on_menu(mode == "pause" or mode == "menu")
	player.enabled = mode == "gameplay" and runtime.endings(runtime.state).is_empty()
	player.simulation_enabled = simulation_enabled
	if module_host != null: module_host.prepare_motion()

func context_candidate() -> Dictionary:
	room_root.update_interaction_targets(player.position)
	return contextual.select(self)

func input_tick() -> void:
	if entry_error!="" or (room_transition != null and room_transition.active()): return
	room_root.update_interaction_targets(player.position)
	simulation_enabled = belt.advance(actions)
	sync_input_context()
	if actions.just_pressed("quick_save"): save_game()
	if actions.just_pressed("quick_load"): load_game()
	if belt.enabled and actions.just_pressed("screenshot"):
		capture(options.get("screenshots","user://screenshots").path_join("tick-%08d.png" % actions.tick))
	if belt.enabled and actions.just_pressed("dev_record") and replay != null: replay.toggle_record()
	if belt.settings_open:
		pause_settings()
		return
	if not simulation_enabled: return
	if actions.just_pressed("reset"):
		if module_host == null or not module_host.claim_reset(): retry_checkpoint()
		return
	if actions.just_pressed("action_menu"):
		menu_open = not menu_open; menu_index = 0
		sync_n64_ui(); sync_input_context()
		return
	if actions.just_pressed("secondary"):
		if menu_open: menu_open = false; sync_n64_ui()
		elif dialogue_active():
			for action in ui_actions:
				if action.id.begins_with("cancel:"): dispatch(action.id); break
		else: narration_pending = false; n64_ui.inv_open = false; n64_ui.hide_dialog()
		contextual.target_id = ""; focus_id = ""; player.focus_point = null
		sync_input_context()
		return
	if actions.just_pressed("inventory") and not dialogue_active() and not menu_open:
		n64_ui.inv_toggle(); sync_input_context(); return
	if menu_open:
		if actions.just_pressed("nav_up"): menu_index -= 1; sync_n64_ui()
		if actions.just_pressed("nav_down"): menu_index += 1; sync_n64_ui()
		if confirm_edge():
			if not ui_actions.is_empty(): dispatch(ui_actions[posmod(menu_index,ui_actions.size())].id)
		sync_input_context()
		return
	if dialogue_active() or narration_pending:
		var choices := conversation_actions()
		if page_index == text_pages.size()-1 and dialogue_active():
			if actions.just_pressed("nav_up"): menu_index -= 1; sync_n64_ui()
			if actions.just_pressed("nav_down"): menu_index += 1; sync_n64_ui()
		if confirm_edge():
			if page_index+1 < text_pages.size(): page_index += 1; sync_n64_ui()
			elif dialogue_active() and not choices.is_empty(): dispatch(choices[posmod(menu_index,choices.size())].id)
			else: narration_pending = false; n64_ui.hide_dialog()
		sync_input_context()
		return
	if n64_ui.inv_open:
		if actions.just_pressed("nav_left"): n64_ui.inv_sel = maxi(0,n64_ui.inv_sel-1)
		if actions.just_pressed("nav_right"): n64_ui.inv_sel = mini(n64_ui.inv_items.size()-1,n64_ui.inv_sel+1)
		return
	if module_host != null and (module_host.active_id != "" or module_host.owns_input()):
		# Combat owns E/Q/Z/Space; course owns Space; a puzzle room owns WASD/E/Z. Tab/Esc/I were handled above.
		current_candidate = {}
		return
	current_candidate = contextual.update(self)
	focus_id = contextual.target_id
	player.focus_point = current_candidate.position if focus_id != "" and not current_candidate.is_empty() else null
	if actions.consume_buffer("primary",not current_candidate.is_empty()):
		var selected := current_candidate.duplicate()
		var result := dispatch(selected.id)
		if result.ok: contextual.used(selected.icon)
	elif actions.just_pressed("primary") and n64_ui.dlg_on:
		# Presentation typing never gates gameplay or replay timing.
		if page_index+1 < text_pages.size(): page_index += 1; sync_n64_ui()
		else: n64_ui.hide_dialog()
	# C inspects authored anchors, then returns to follow after a complete cycle.
	if actions.just_pressed("camera_cycle"): follow_camera.cycle()
	sync_input_context()

func pause_settings() -> void:
	var changed := false
	var cfg := {"version":1,"preset":actions.profile.preset,"options":actions.profile.options.duplicate(),"bindings":actions.profile.bindings.duplicate(true),"tuning":actions.profile.tuning.duplicate()}
	if actions.just_pressed("primary"):
		cfg.options.focus_mode = "toggle" if cfg.options.focus_mode == "hold" else "hold"; changed = true
	if actions.just_pressed("run" if actions.profile.bindings.has("run") else "walk"):
		cfg.options.run_mode = {"auto":"hold","hold":"toggle","toggle":"auto"}[cfg.options.run_mode]; changed = true
	if actions.just_pressed("secondary"): cfg.options.reduced_motion = not cfg.options.reduced_motion; changed = true
	if actions.just_pressed("action_menu"):
		var legacy: bool=not cfg.bindings.has("run")
		cfg.preset = "right" if cfg.preset == "left" else "left"; cfg.erase("bindings"); changed = true
		if legacy:
			cfg.bindings=preload("res://input/profile.gd").validate({"version":1,"preset":cfg.preset}).profile.bindings
			cfg.bindings.erase("run"); cfg.bindings.erase("camera_recenter")
			cfg.bindings.walk=[{"key":KEY_SHIFT}]
			cfg.bindings.camera_up=[{"key":KEY_I},{"axis":JOY_AXIS_RIGHT_Y,"sign":-1}]
			if cfg.preset=="right": cfg.bindings.dodge=[{"key":KEY_ALT},{"button":JOY_BUTTON_RIGHT_SHOULDER}]
	if changed:
		# Replays change the profile in memory, never write the user's settings.
		if actions.source == "live": actions.save_remap(cfg)
		else: actions.configure(cfg)

func physical_checkpoint() -> Dictionary:
	return {"story":codec.pack(runtime),"position":[player.position.x,player.position.y,player.position.z],"yaw":player.facing_yaw,"camera":camera_index}

func restore_checkpoint(value: Dictionary) -> Dictionary:
	var result: Dictionary = codec.load_into(runtime,value.get("story",{}))
	if not result.ok: return result
	enter_room("")
	var pos = value.get("position",[])
	if pos is Array and pos.size() == 3 and pos.all(func(v): return (v is float or v is int) and is_finite(float(v))):
		player.position = Vector3(pos[0],pos[1],pos[2])
	player.set_facing_yaw(float(value.get("yaw",0.0)))
	select_camera(int(value.get("camera",0)))
	player.velocity = Vector3.ZERO; player.actual_velocity = Vector3.ZERO
	if module_host != null:
		module_host.restore_checkpoint()
	if not finalize_room_entry().ok: return {"ok":false,"reason":entry_error}
	menu_open = false; page_index = 0; narration_pending = false; n64_ui.inv_open = false
	last_text = boxed(runtime.rooms[runtime.state.location].description)
	refresh(); sync_input_context()
	return result

func retry_checkpoint() -> void:
	if not checkpoint.is_empty(): restore_checkpoint(checkpoint)
	belt.checkpoint_ticks = int(actions.profile.tuning.checkpoint_icon_ticks)

func _exit_tree() -> void:
	preload("res://look/pixel_font.gd")._inst = null
	resolver.clear_caches()

func quit_cleanly(exit_code: int = 0) -> void:
	if replay != null and replay.recording: replay.stop_record()
	if is_instance_valid(sounds): await sounds.shutdown()
	get_tree().quit(exit_code)

func capture(path: String) -> bool:
	if DisplayServer.get_name() == "headless": return false
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	if image == null or image.is_empty(): return false
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var error := image.save_png(path)
	var low := viewport.get_texture().get_image()
	if low != null and not low.is_empty(): low.save_png(path.get_basename() + "-world.png")
	return error == OK

## Internal 320x240 frame only (style-gate evidence; no window upscale).
func capture_low(path: String) -> bool:
	if DisplayServer.get_name() == "headless": return false
	await RenderingServer.frame_post_draw
	var low := viewport.get_texture().get_image()
	if low == null or low.is_empty(): return false
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	return low.save_png(path) == OK
