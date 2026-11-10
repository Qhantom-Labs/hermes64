extends SceneTree
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
var failures := []
var view
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func frame(digital := []) -> void:
	view.actions.submit_frame({"digital":digital})
	await physics_frame
	await process_frame
func run() -> void:
	view = View.new(); root.add_child(view)
	if not view.has_method("context_candidate"):
		check(false,"contextual primary route missing"); view.queue_free(); await process_frame; quit(1); return
	var result: Dictionary = view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","save":"res://../controls-save.json","test":true})
	check(result.ok,"boot last_light")
	check(view.checkpoint.position == view.replay.vec(view.player.position),"initial checkpoint follows authored actor spawn")
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	view.n64_ui.hide_dialog()
	await frame() # register the actual native room bodies before choosing a ray
	var anchor: Vector3=view.room_root.target_anchors.ferryman
	var target:=Vector3.ZERO
	var direction:=Vector3.ZERO
	for dir in [Vector3.BACK,Vector3.RIGHT,Vector3.FORWARD,Vector3.LEFT,Vector3(1,0,1).normalized(),Vector3(-1,0,1).normalized()]:
		view.room_root.update_interaction_targets(anchor+dir*4.0)
		var edge: Vector3=view.room_root.target_positions.ferryman
		var clear:=true
		for reach in [2.1,2.5,2.7]:
			var pos: Vector3=Vector3(edge.x,0.001,edge.z)+dir*reach
			if not view.player.room_navigation.point_clear(pos): clear=false
		view.player.position=Vector3(edge.x,0.001,edge.z)+dir*2.1
		view.room_root.update_interaction_targets(view.player.position)
		if clear and view.context_candidate().get("id","")=="interact:talk_ferryman":
			target=Vector3(edge.x,0.001,edge.z); direction=dir; break
	check(direction!=Vector3.ZERO,"R07 has a capsule-clear unobstructed actor-edge fixture")
	view.player.position = target + direction*2.1
	await frame()
	var candidate: Dictionary = view.context_candidate()
	check(candidate.get("id","") == "interact:talk_ferryman","R07 primary chooses nearby actor")
	await frame(["focus"])
	check(view.focus_id == "interact:talk_ferryman","R07 focus acquire")
	view.player.position = target + direction*2.5
	await frame(["focus"])
	check(view.focus_id != "","R07 focus release hysteresis")
	view.player.position = target + direction*2.7
	await frame(["focus","primary"])
	check(view.focus_id == "" and view.runtime.state.dialogue.ferry_words == "","R07 out-of-range E refuses")
	await frame(); await frame()
	view.player.position = target + direction*2.1
	await frame()
	check(view.runtime.state.dialogue.ferry_words == "greeting","R07 buffered E dispatches when reach becomes legal")
	check(not view.menu_open,"E is context, not full menu")
	await frame(["move_up"]); var p: Vector3 = view.player.position
	await frame(["secondary","move_up"])
	await frame(["move_up"])
	check(view.player.position.distance_to(p)<0.001,"M09 modal exit rejects stale movement")
	await frame(); await frame(["action_menu"])
	check(view.menu_open,"Tab full menu fallback")
	var before: Dictionary = view.runtime.state.duplicate(true)
	await frame(["menu"])
	check(view.belt.paused,"Esc pauses instead of quitting")
	for i in 10: await frame(["move_up","primary"])
	check(view.runtime.state == before,"pause prevents story effects")
	await frame(); await frame(["menu"]); await frame()
	view.menu_open = false; view.sync_input_context()
	check(view.save_game().ok,"checkpoint save")
	var saved: Vector3 = view.player.position
	view.player.position += Vector3(1,0,0)
	check(view.load_game().ok and view.player.position.distance_to(saved)<0.001,"checkpoint restores physical position")
	view.player.position += Vector3(1,0,0)
	for i in 36: await frame(["reset"])
	check(view.player.position.distance_to(saved)<0.05,"hold-R retries checkpoint")
	check(not view.belt.enabled,"dev off by default")
	await frame(["dev_pause"])
	check(not view.belt.paused,"dev keys inert without flag")
	view.player.velocity = Vector3(1,0,0)
	view.belt.enabled = true
	await frame(); await frame(["dev_pause"])
	check(view.belt.paused,"dev pause")
	var sim: int = view.belt.sim_tick
	var paused_at: Vector3 = view.player.position
	await frame(["move_right"])
	check(view.player.position == paused_at,"dev pause holds physical state")
	await frame(["dev_step","move_right"])
	check(view.belt.sim_tick == sim+1,"frame-step advances exactly one simulation tick")
	check(view.player.position != paused_at,"frame-step advances actual player simulation")
	await frame(["dev_step"])
	check(view.belt.sim_tick == sim+1,"held frame-step does not repeat")
	print("CONTROLS CONTEXT failures=",JSON.stringify(failures))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
