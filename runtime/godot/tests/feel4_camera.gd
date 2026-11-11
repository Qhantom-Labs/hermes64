extends SceneTree
## FEEL4 camera-turn measurement. Boots the real game (main.tscn), passes the opening card with Enter, then drives
## real key events (the live path: frames carry the drawn camera heading) through fixed scenarios on the roof and
## records, every rendered frame at --fixed-fps 60, the drawn (render) camera yaw, the fixed-tick follow yaw and its
## velocity, eye position, collision pull-ins and player travel. Presentation measurement only.
##   --output=<json>   --frames=<dir> (optional: 320x240 frames, every 2nd rendered frame, of the --clip scenarios)
##   --clip=<id,id>    scenarios to film (default corner)
const SCENARIOS := [
	["corner", [[["w"], 60], [["w", "a"], 90], [["w"], 60], [["w", "d"], 90], [["w"], 60], [[], 50]]],
	["zigzag", [[["w"], 30], [["w", "a"], 15], [["w", "d"], 15], [["w", "a"], 15], [["w", "d"], 15], [["w", "a"], 15], [["w", "d"], 15], [["w", "a"], 15], [["w", "d"], 15], [["w"], 30], [[], 40]]],
	["reverse", [[["w"], 60], [["s"], 60], [["w"], 60], [[], 40]]],
	["tap_turn", [[["a"], 6], [[], 24], [["d"], 6], [[], 24], [["s"], 6], [[], 24], [["w"], 6], [[], 40]]],
	["diagonal", [[["w", "a"], 150], [[], 40]]],
	["strafe", [[["a"], 90], [["d"], 90], [[], 40]]],
	["orbit_keys", [[["l"], 60], [[], 90], [["j"], 30], [[], 90]]],
	["mouse_drag", [[["drag:20"], 30], [[], 90]]],
	["mouse_flick", [[["drag:160"], 3], [[], 100]]],
	["run_orbit", [[["w"], 40], [["w", "drag:12"], 40], [["w"], 60], [[], 40]]],
]
const KEYS := {"w": KEY_W, "a": KEY_A, "s": KEY_S, "d": KEY_D, "j": KEY_J, "l": KEY_L}
var dragging := false

func mouse(down: bool) -> void:
	var e := InputEventMouseButton.new(); e.button_index = MOUSE_BUTTON_LEFT; e.pressed = down; e.position = Vector2(400, 300)
	Input.parse_input_event(e)
	dragging = down

func drag(px: float) -> void:
	var e := InputEventMouseMotion.new(); e.position = Vector2(400, 300); e.relative = Vector2(px, 0); e.button_mask = MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(e)
var view
var output := ""
var frames_dir := ""
var clip_ids := ["corner"]
var held := {}

func _initialize() -> void:
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--output="): output = arg.trim_prefix("--output=")
		if arg.begins_with("--frames="): frames_dir = arg.trim_prefix("--frames=")
		if arg.begins_with("--clip="): clip_ids = Array(arg.trim_prefix("--clip=").split(","))
	call_deferred("run")

func key(code: int, down: bool) -> void:
	var e := InputEventKey.new(); e.physical_keycode = code; e.keycode = code; e.pressed = down
	Input.parse_input_event(e)

func hold(keys: Array) -> void:
	for k in KEYS:
		var want: bool = k in keys
		if want != bool(held.get(k, false)):
			key(KEYS[k], want); held[k] = want
	var px := 0.0
	for k in keys:
		if str(k).begins_with("drag:"): px = float(str(k).trim_prefix("drag:"))
	if px != 0.0 and not dragging: mouse(true)
	if px == 0.0 and dragging: mouse(false)
	set_meta("drag_px", px)

func ticks(n: int) -> void:
	for i in n: await physics_frame

func run() -> void:
	view = load("res://main.tscn").instantiate(); root.add_child(view)
	await ticks(30)
	for i in 60:
		if view.actions.context == "gameplay" and (view.scene_cards == null or str(view.scene_cards.phase) == "idle"): break
		key(KEY_ENTER, true); await ticks(3); key(KEY_ENTER, false); await ticks(6)
	await ticks(30)
	var fc = view.follow_camera
	var result := {"scenarios": [], "fixed_fps": Engine.physics_ticks_per_second}
	for sc in SCENARIOS:
		# Same start for every scenario: roof centre, standing, camera settled (probe-only position write).
		hold([])
		view.player.position = Vector3(10.5, view.player.position.y, 12.0)
		view.player.velocity = Vector3.ZERO
		await ticks(5)
		fc.ready_centre = false; fc.reset_presentation = true; fc.yaw_velocity = 0.0; fc.wanted_yaw = fc.yaw
		await ticks(150)
		var rows := []
		var frame_i := 0
		for step in sc[1]:
			hold(step[0])
			for t in int(step[1]):
				if float(get_meta("drag_px", 0.0)) != 0.0: drag(float(get_meta("drag_px")))
				await process_frame
				var r: Dictionary = fc.render_last
				var v: Vector3 = view.player.actual_velocity
				rows.append({"yaw": float(r.get("yaw", 0.0)), "fixed_yaw": fc.yaw, "yaw_v": fc.yaw_velocity, "pulled": bool(fc.last.get("pulled_in", false)),
					"eye": r.get("eye", [0, 0, 0]), "vx": v.x, "vz": v.z, "keys": step[0], "facing": view.player.facing_yaw})
				if frames_dir != "" and sc[0] in clip_ids and frame_i % 2 == 0:
					await view.capture_low(frames_dir.path_join("%s-%04d.png" % [sc[0], frame_i / 2]))
				frame_i += 1
		hold([])
		result.scenarios.append({"id": sc[0], "frames": rows})
		print("FEEL4_CAMERA scenario ", sc[0], " frames=", rows.size())
	var f := FileAccess.open(output, FileAccess.WRITE); f.store_string(JSON.stringify(result)); f.close()
	print("FEEL4_CAMERA done")
	view.queue_free()
	await ticks(3)
	quit(0)
