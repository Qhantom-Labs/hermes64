extends SceneTree
## Self-contained controller tests. No game fixture, presenter stub, or input injection.
const Player = preload("res://view/player.gd")
const Character = preload("res://actors/character.gd")
const Movie = preload("res://input/movie.gd")
const PixelFont = preload("res://look/pixel_font.gd")
const Pack = preload("res://look/pack.gd")
var transition_script
var checks := 0
var failures := []
var cases := []
var cadence := []
var actions

class ReceiptObserver extends Node:
	var receipt: Callable
	var observed := false
	func _physics_process(_delta: float) -> void:
		if not observed:
			observed = true
			receipt.call()

func check(ok: bool, label: String) -> void:
	checks += 1
	print("PASS " if ok else "FAIL ", label)
	if not ok: failures.append(label)

func _initialize() -> void:
	call_deferred("run")

func make_fixture() -> Dictionary:
	var viewport := SubViewport.new()
	viewport.size = Vector2i(427, 240)
	viewport.own_world_3d = true
	root.add_child(viewport)
	var world := Node3D.new()
	world.name = "source_world"
	viewport.add_child(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_color = Color("334455")
	world.add_child(environment)
	var light := DirectionalLight3D.new()
	world.add_child(light)
	var player = Player.new()
	player.name = "canonical_player"
	player.actions = actions
	world.add_child(player)
	player.set_physics_process(false)
	player.simulation_enabled = false
	player.position = Vector3(4, 0.1, 4)
	var visual = Character.new()
	visual.name = "visual"
	visual.set_meta("real_character", true)
	visual.manual_clock = true
	visual.position = Vector3(0.07, 0, 0.04)
	visual.scale = Vector3.ONE * 1.1
	player.add_child(visual)
	var mesh := MeshInstance3D.new()
	mesh.mesh = CapsuleMesh.new()
	visual.add_child(mesh)
	var marker := Node3D.new()
	marker.name = "stride_marker"
	visual.add_child(marker)
	var animation := AnimationPlayer.new()
	animation.name = "clips"
	animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	visual.add_child(animation)
	var library := AnimationLibrary.new()
	for clip_name in ["idle", "walk"]:
		var clip := Animation.new()
		clip.length = 1.0
		clip.loop_mode = Animation.LOOP_LINEAR
		var track := clip.add_track(Animation.TYPE_VALUE)
		clip.track_set_path(track, NodePath("stride_marker:position"))
		clip.track_insert_key(track, 0.0, Vector3.ZERO)
		clip.track_insert_key(track, 1.0, Vector3.RIGHT if clip_name == "walk" else Vector3.ZERO)
		library.add_animation(clip_name, clip)
	animation.add_animation_library("", library)
	visual.animation = animation
	visual.play_clip("idle")
	var camera := Camera3D.new()
	camera.name = "source_camera"
	world.add_child(camera)
	camera.position = Vector3(4, 3, 9)
	camera.look_at(player.global_position + Vector3.UP)
	camera.current = true
	var fx = transition_script.new()
	viewport.add_child(fx)
	fx.set_width(viewport.size.x)
	fx.set_process(false)
	fx.set_physics_process(false)
	return {"viewport":viewport,"world":world,"player":player,"visual":visual,
		"camera":camera,"fx":fx,"environment":environment,
		"exit":Vector3(4.07, 0.1, 3.7)}

func start(f: Dictionary, reduced := false) -> bool:
	var ok: bool = f.fx.begin(f.world, f.camera, f.visual, f.exit, Vector3.FORWARD, reduced)
	check(ok, "real controller begins" + (" reduced" if reduced else ""))
	return ok

func canonical(f: Dictionary) -> Dictionary:
	var p = f.player
	return {"actions":actions.snapshot(),"position":Movie.vec(p.position),
		"velocity":Movie.vec(p.velocity),"actual":Movie.vec(p.actual_velocity),
		"desired":Movie.vec(p.desired_velocity),"yaw":p.facing_yaw,
		"basis":Movie.basis(p.camera_basis),"latch_basis":Movie.basis(p.latched_basis),
		"last_input":[p.last_input.x,p.last_input.y],"latched":p.latched}

func script_free(node: Node) -> bool:
	if node.get_script() != null: return false
	for child in node.get_children():
		if not script_free(child): return false
	return true

func complete_fade(f: Dictionary, title := "North Gate") -> bool:
	f.fx.advance(0.22)
	check(f.fx.phase == "black", "fade-out reaches explicit black barrier")
	if f.fx.phase != "black": return false
	var ok: bool = f.fx.reveal(title)
	check(ok, "black barrier accepts reveal")
	if not ok: return false
	f.fx.advance(0.18)
	return f.fx.phase == "release"

func test_clone() -> void:
	var f := make_fixture()
	actions.advance({"digital":["move_up","primary"]})
	var before := Movie.digest(canonical(f))
	var original_transform: Transform3D = f.visual.global_transform
	check(not f.fx.active() and f.fx.phase == "idle" and f.fx.fade == 0.0, "controller starts transparent and inactive")
	check(f.fx.mouse_filter == Control.MOUSE_FILTER_IGNORE and f.fx.focus_mode == Control.FOCUS_NONE, "overlay cannot steal UI focus or clicks")
	if not start(f): f.viewport.free(); return
	var ghost = f.fx.ghost_viewport
	var visual = f.fx.ghost_visual
	check(ghost != null and visual != null, "captures a real source-room viewport and visual")
	if ghost == null or visual == null: f.viewport.free(); return
	check(ghost.find_world_3d() != f.viewport.find_world_3d(), "ghost uses an isolated physics/render world")
	check(visual != f.visual and visual.global_transform.is_equal_approx(original_transform), "ghost starts on the visible source actor, not the canonical body")
	check(script_free(ghost.get_child(0)), "every cloned gameplay/actor script is removed")
	check(ghost.get_camera_3d() != f.camera and ghost.get_camera_3d().global_transform.is_equal_approx(f.camera.global_transform), "exit copy retains the actual drawing camera")
	var ghost_env = ghost.get_child(0).find_children("*", "WorldEnvironment", true, false)[0]
	check(ghost_env.environment != f.environment.environment, "entry look changes cannot alias the ghost Environment resource")
	f.fx.advance(0.11)
	check(f.fx.fade > 0.0 and f.fx.fade < 1.0 and visual.global_position.z < original_transform.origin.z, "actor visibly travels toward exit during fade-out")
	check(visual.global_basis.z.normalized().dot(Vector3.FORWARD) > 0.99, "real actor faces the exit without changing canonical facing")
	check(visual.get_node("stride_marker").position != Vector3.ZERO, "ghost samples the real walk AnimationPlayer")
	check(f.visual.get_node("stride_marker").position == Vector3.ZERO, "ghost walk animation does not animate the original actor")
	var held_pose: Vector3 = visual.get_node("stride_marker").position
	f.fx.advance(0.001)
	check(visual.get_node("stride_marker").position == held_pose, "walk poses hold between 15 Hz samples")
	f.fx.advance(0.099)
	check(visual.global_position.z < f.exit.z and f.fx.fade < 1.0, "walk crosses the actual exit plane while still partly visible")
	check(f.visual.global_transform.is_equal_approx(original_transform), "source visual transform remains untouched")
	check(Movie.digest(canonical(f)) == before, "all canonical physical fields and Action tick/hash remain unchanged")
	f.viewport.free()

func test_timeline() -> void:
	var f := make_fixture()
	var events := []
	f.fx.black_reached.connect(func(): events.append("black"))
	f.fx.finished.connect(func(): events.append("finished"))
	if not start(f): f.viewport.free(); return
	check(not f.fx.reveal("Too early"), "cannot reveal before opaque black")
	check(not f.fx.begin(f.world, f.camera, f.visual, f.exit, Vector3.FORWARD), "reentrant begin is refused")
	for delta in [-1.0, NAN, INF]: f.fx.advance(delta)
	check(f.fx.fade == 0.0, "invalid presentation deltas do not move the timeline")
	f.fx.advance(50.0)
	check(f.fx.phase == "black" and f.fx.fade == 1.0 and events == ["black"], "large delta reaches black exactly once, never skips the barrier")
	check(f.fx.ghost_viewport == null and f.fx.ghost_visual == null, "source copy is disposed at black")
	f.fx.advance(50.0)
	check(f.fx.phase == "black" and f.fx.fade == 1.0 and events == ["black"], "room build can hold at black without advancing canonical time")
	if f.fx.phase != "black": f.viewport.free(); return
	check(f.fx.reveal("North Gate"), "destination name starts reveal")
	check(f.fx.fade == 1.0 and not f.fx.reveal("Duplicate"), "reveal starts opaque and cannot be repeated")
	f.fx.advance(0.09)
	check(is_equal_approx(f.fx.fade, 0.5), "fade-in exposes the already-framed destination")
	check(not f.fx.release_input({}, 0.18), "neutral input cannot unlock a half-faded transition")
	f.fx.advance(0.09)
	check(f.fx.phase == "release" and f.fx.fade == 0.0 and f.fx.active(), "transparent destination still fences held controls")
	check(events == ["black"], "visual fade completion alone does not unlock input")
	check(f.fx.release_input({}, 0.18), "neutral input completes transition")
	check(not f.fx.active() and events == ["black","finished"], "finished emits once after both fade and input fence")
	check(not f.fx.release_input({}, 0.18), "repeated release cannot emit a second finished")
	check(not f.fx.card_layout().is_empty(), "brief room name can outlive the input lock")
	f.viewport.free()

func test_boundaries() -> void:
	var f := make_fixture()
	var events := []
	f.fx.entry_requested.connect(func(): events.append("entry"))
	f.fx.freeze_requested.connect(func(): events.append("freeze"))
	var observer := ReceiptObserver.new()
	observer.process_physics_priority = 100
	observer.receipt = func(): events.append("movie")
	root.add_child(observer)
	f.fx.set_physics_process(true)
	if not start(f): observer.free(); f.viewport.free(); return
	for i in 5:
		await physics_frame
		await process_frame
		if "freeze" in events: break
	check(events == ["entry","movie","freeze"], "real physics priorities finalize entry before Movie, freeze only after its trigger receipt")
	for i in 2: await physics_frame; await process_frame
	check(events == ["entry","movie","freeze"], "canonical boundary signals are one-shot, not fade ticks")
	observer.free()
	f.viewport.free()

func test_reduced() -> void:
	var f := make_fixture()
	var skeleton := Skeleton3D.new()
	skeleton.name = "held_source_pose"
	skeleton.add_bone("thigh")
	f.visual.add_child(skeleton)
	skeleton.set_bone_pose_rotation(0, Quaternion(Vector3.RIGHT, 0.4))
	var source_pose := skeleton.get_bone_pose(0)
	var before := Movie.digest(canonical(f))
	if not start(f, true): f.viewport.free(); return
	var visual = f.fx.ghost_visual
	check(visual != null and visual.get_node("held_source_pose").get_bone_pose(0).is_equal_approx(source_pose), "reduced exit copy preserves the actor's held skeleton pose")
	var origin: Vector3 = visual.global_position if visual != null else Vector3.INF
	f.fx.advance(0.03)
	check(is_equal_approx(f.fx.fade, 0.5), "reduced motion reaches half-black in 30 ms")
	check(visual != null and visual.global_position == origin, "reduced motion has no forced actor travel")
	f.fx.advance(0.03)
	check(f.fx.phase == "black" and f.fx.fade == 1.0, "reduced fade-out is 60 ms")
	if f.fx.phase == "black":
		f.fx.reveal("Quiet Entry")
		f.fx.advance(0.06)
		check(f.fx.phase == "release" and f.fx.fade == 0.0, "reduced fade-through-black is 120 ms, still release-gated")
	check(Movie.digest(canonical(f)) == before, "reduced-motion timeline preserves canonical state")
	f.viewport.free()

func test_release_fence() -> void:
	var f := make_fixture()
	if not start(f) or not complete_fade(f): f.viewport.free(); return
	var before := Movie.digest(canonical(f))
	var held_frames := [
		{"digital":["primary"]}, {"digital":["dodge"]}, {"digital":["move_up"]},
		{"digital":["action_menu"]}, {"digital":["reset"]}, {"digital":["quick_load"]},
		{"buttons":["primary"]}, {"analog":[0.3,0]}, {"camera":[0,-0.4]},
		{"analog":[0.15,0.15]}, {"digital":""}, {"buttons":{}},
		{"analog":[0]}, {"analog":["0",0]}, {"analog":[NAN,0]},
		{"camera":[0,INF]}, {"unknown_field":true}
	]
	for frame in held_frames:
		check(not f.fx.release_input(frame, 0.18) and f.fx.active(), "raw held/malformed frame cannot leak at arrival: " + str(frame))
	for dead_zone in [-0.1, NAN, INF, 1.0]:
		check(not f.fx.release_input({}, dead_zone), "invalid release dead zone fails closed: " + str(dead_zone))
	check(Movie.digest(canonical(f)) == before, "release polling consumes no Action frame or canonical hash")
	check(f.fx.release_input({"digital":[],"buttons":[],"analog":[0.05,-0.08],"camera":[0.02,0]}, 0.18), "real neutral pad drift inside the configured dead zone unlocks")
	f.viewport.free()

func test_card() -> void:
	var saved_theme: Dictionary = Pack.current
	Pack.current = {"ui":{"text":"#f2d58a","ink":"#0b0d12"}}
	var f := make_fixture()
	if not start(f) or not complete_fade(f, "Room Name ".repeat(100)):
		f.viewport.free(); Pack.current = saved_theme; return
	for width in [240,320,384,427]:
		f.fx.set_width(width)
		var layout: Dictionary = f.fx.card_layout()
		check(not layout.is_empty(), "name card exists at internal width " + str(width))
		if layout.is_empty(): continue
		var measured: int = PixelFont.get_font().measure(layout.text)
		check(layout.text.ends_with("...") and measured <= width-32, "long title uses fitted bitmap ellipsis without wrapping")
		check(layout.position.x >= 16 and layout.position.x + measured <= width-16 and layout.position.x == roundf(layout.position.x), "name is centred on integer pixels inside viewport margins")
		check(layout.color == Color("f2d58a") and layout.position.y == 32, "name uses the existing pack's text colour and one quiet top row")
		check(f.fx.size == Vector2(width,240), "fade covers the aspect-aware 240-scanline viewport")
	check(f.fx.find_children("*", "Label", true, false).is_empty() and f.fx.find_children("*", "Panel", true, false).is_empty(), "room title adds no bubble, Label, panel, or choices")
	f.fx.release_input({}, 0.18)
	f.fx.advance(0.68)
	check(f.fx.card_layout().is_empty() and not f.fx.active(), "room card expires after 850 ms, without extending input lock")
	f.fx.set_width(1)
	check(f.fx.size == Vector2(240,240), "undersized resize respects the runtime's minimum internal width")
	f.fx.cancel()
	if start(f) and complete_fade(f, "  River\n  Pass\t "):
		check(f.fx.card_layout().get("text", "") == "River Pass", "authored whitespace is a single unobtrusive title line")
	f.viewport.free()
	Pack.current = saved_theme

func test_live_input_control() -> void:
	# A passing integration control, not a claim of a new behavioral RED:
	# raw InputMap sampling must exercise the same release fence without ticks.
	var f := make_fixture()
	if not start(f) or not complete_fade(f): f.viewport.free(); return
	var before := Movie.digest(canonical(f))
	for row in [[KEY_E,"primary"],[KEY_W,"move_up"],[KEY_SPACE,"dodge"],
		[KEY_TAB,"action_menu"],[KEY_R,"reset"],[KEY_C,"camera_cycle"]]:
		var event := InputEventKey.new()
		event.physical_keycode = row[0]
		event.keycode = row[0]
		event.pressed = true
		Input.parse_input_event(event)
		Input.flush_buffered_events()
		var raw: Dictionary = actions.sample_live()
		check(row[1] in raw.digital, "real InputMap sample sees held " + row[1])
		check(not f.fx.release_input(raw, actions.profile.tuning.dead_zone_pad), "real held input stays fenced: " + row[1])
		var release := InputEventKey.new()
		release.physical_keycode = row[0]
		release.keycode = row[0]
		release.pressed = false
		Input.parse_input_event(release)
		Input.flush_buffered_events()
	check(f.fx.release_input(actions.sample_live(), actions.profile.tuning.dead_zone_pad), "actual released InputMap unlocks without a synthetic Action frame")
	check(Movie.digest(canonical(f)) == before, "InputMap release sampling leaves canonical Action/player hashes untouched")
	f.viewport.free()

func test_guards_cleanup() -> void:
	var f := make_fixture()
	var foreign := make_fixture()
	for args in [
		[f.world,foreign.camera,f.visual,f.exit,Vector3.FORWARD],
		[f.world,f.camera,foreign.visual,f.exit,Vector3.FORWARD],
		[f.world,f.camera,f.player,f.exit,Vector3.FORWARD],
		[f.world,f.camera,f.visual,Vector3.INF,Vector3.FORWARD],
		[f.world,f.camera,f.visual,f.exit,Vector3.UP],
		[f.world,f.camera,f.visual,f.exit,Vector3(NAN,0,0)]
	]:
		check(not f.fx.begin.callv(args) and not f.fx.active(), "invalid source/exit cannot start a transition")
	check(f.fx.begin(f.world, f.camera, null, f.exit, Vector3.FORWARD), "missing visual still permits a clean fade-only transition")
	f.fx.cancel()
	check(not f.fx.active() and f.fx.fade == 0.0 and f.fx.ghost_viewport == null, "cancel clears all overlay/ghost state")
	check(f.fx.begin(f.world, f.camera, f.visual, Vector3(40,0.1,40), Vector3.RIGHT), "remote action-menu portal can use a fade-only view")
	var ghost = f.fx.ghost_visual
	var at: Vector3 = ghost.global_position if ghost != null else Vector3.INF
	f.fx.advance(0.11)
	check(ghost != null and ghost.global_position == at, "remote exit never slides an actor across the whole room")
	f.fx.cancel()
	if start(f):
		var reference: WeakRef = weakref(f.fx.ghost_viewport)
		f.fx.cancel()
		f.fx._physics_process(1.0/60.0)
		f.fx.free()
		await process_frame
		check(reference.get_ref() == null, "cancel/free releases the isolated world, with no retained scene")
	foreign.viewport.free()
	f.viewport.free()
	var detached := make_fixture()
	if start(detached):
		detached.world.free()
		detached.fx.advance(0.11)
		check(detached.fx.ghost_visual != null and detached.fx.fade > 0.0, "normal synchronous enter_room can free the source while its exit view walks")
		detached.fx.advance(0.11)
		check(detached.fx.phase == "black", "independent source view finishes after original room teardown")
	detached.viewport.free()

func test_cadence() -> void:
	for fps in [30,60,144]:
		var f := make_fixture()
		var before := Movie.digest(canonical(f))
		if not start(f): f.viewport.free(); continue
		var elapsed := 0.0
		var samples := 0
		for i in 200:
			f.fx.advance(1.0/float(fps)); elapsed += 1.0/float(fps); samples += 1
			if f.fx.phase == "black": break
		check(f.fx.phase == "black", "render cadence reaches black at " + str(fps))
		if f.fx.phase == "black": f.fx.reveal("North Gate")
		for i in 200:
			f.fx.advance(1.0/float(fps)); elapsed += 1.0/float(fps); samples += 1
			if f.fx.phase == "release": break
		check(f.fx.phase == "release" and elapsed >= 0.3 and elapsed <= 0.5, "normal fade stays within 300–500 ms at " + str(fps))
		check(Movie.digest(canonical(f)) == before, "cadence changes no canonical tick/hash at " + str(fps))
		check(f.fx.release_input({}, 0.18), "playback-neutral fence requires no physical input at " + str(fps))
		cadence.append({"fps":fps,"samples":samples,"seconds":elapsed,"canonical_hash":before})
		f.viewport.free()

func run() -> void:
	actions = root.get_node("Actions")
	actions.set_physics_process(false)
	actions.configure({"version":1})
	actions.set_source("bot")
	check(ResourceLoader.exists("res://view/room_transition.gd"), "room transition controller exists (wiring RED only if absent)")
	if not failures.is_empty(): finish(); return
	transition_script = load("res://view/room_transition.gd")
	check(transition_script != null and transition_script.can_instantiate(), "real controller script loads")
	if not failures.is_empty(): finish(); return
	var requested := ""
	var args := OS.get_cmdline_user_args()
	if args.size() == 2 and args[0] == "--case": requested = args[1]
	for row in [["clone",test_clone],["timeline",test_timeline],["boundaries",test_boundaries],
		["reduced",test_reduced],["release",test_release_fence],["card",test_card],
		["live_input_control",test_live_input_control],["guards",test_guards_cleanup],["cadence",test_cadence]]:
		if requested != "" and requested != row[0]: continue
		cases.append(row[0])
		print("CASE ",row[0])
		await row[1].call()
	check(not cases.is_empty(), "at least one controller case executed")
	finish()

func finish() -> void:
	PixelFont._inst = null
	print("FEEL2_TRANSITION ",JSON.stringify({"checks":checks,"cases":cases,"failures":failures,"cadence":cadence},"",true,true))
	quit(0 if failures.is_empty() else 1)
