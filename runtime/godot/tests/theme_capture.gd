extends SceneTree
const Presenter = preload("res://view/presenter.gd")
const Wire = preload("res://core/wire.gd")
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		quit(2)
		return
	var game: Dictionary = Wire.read_json(args[0])
	var captures := []
	for pack in ["polar_pod", "ruins_harbor"]:
		var view = Presenter.new()
		root.add_child(view)
		var result: Dictionary = view.boot(game, {"pack": "res://packs/%s/view.json" % pack})
		if not result.ok or view.runtime.game != game:
			quit(1)
			return
		for i in 12: await process_frame
		var path := args[1].path_join(pack + ".png")
		if not await view.capture(path):
			quit(1)
			return
		captures.append({"pack": pack, "path": path, "game_hash": view.runtime.game.game_hash})
		view.queue_free()
		await process_frame
	var file := FileAccess.open(args[1].path_join("comparison.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"captures": captures, "new_pack_core_edits": 0, "scope": "palette/fog/head/coat primitive presentation preset only, not a finished kit theme"}, "\t"))
	file.close()
	print("THEME CONTRAST captures=", captures.size(), " same_compiled_game=true new_pack_core_edits=0")
	quit()
