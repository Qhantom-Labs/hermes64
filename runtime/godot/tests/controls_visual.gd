extends SceneTree
const View=preload("res://playtest/view.gd")
const Wire=preload("res://core/wire.gd")
var view
func _initialize() -> void: call_deferred("run")
func frame() -> void:
	view.actions.submit_frame({})
	await physics_frame; await process_frame
func run() -> void:
	view=View.new(); root.add_child(view)
	view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true})
	view.actions.set_source("bot"); view.n64_ui.hide_dialog()
	view.player.position=view.room_root.target_positions.ferryman+Vector3(0,0,2.1)
	for i in 10: await frame()
	var candidate: Dictionary=view.current_candidate
	if candidate.is_empty(): printerr("FAIL no target for visual probe"); await view.quit_cleanly(1); return
	var folder: String=ProjectSettings.globalize_path("res://../controls-visual")
	DirAccess.make_dir_recursive_absolute(folder)
	var passed: bool=await view.capture_low(folder.path_join("prompt.png"))
	for i in 3: view.contextual.used(candidate.icon)
	for i in 30: await frame()
	passed=passed and view.contextual.alpha<0.001 and await view.capture_low(folder.path_join("faded.png"))
	view.actions.submit_frame({"digital":["menu"]}); await physics_frame; await process_frame
	passed=passed and await view.capture_low(folder.path_join("settings.png"))
	print("CONTROLS VISUAL passed=",passed," folder=",folder)
	await view.quit_cleanly(0 if passed else 1)
