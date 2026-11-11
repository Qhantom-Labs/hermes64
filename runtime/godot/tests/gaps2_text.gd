extends SceneTree
## GAPS2 G9 native check on the staged game (res://game.json): with metadata.presentation.text_boxes=false no room
## description, event label or ending text box opens (boot, door, restore, module event); the same game with the key
## removed (an older game) opens the description box: the known-bad control. Writes res://../gaps2-text.json.
const Presenter = preload("res://view/presenter.gd")
const Wire = preload("res://core/wire.gd")
var rows := {}

func _initialize() -> void: call_deferred("run")

func frame() -> void:
	await physics_frame
	await process_frame

func probe(label: String, game: Dictionary) -> void:
	var view = Presenter.new()
	root.add_child(view)
	var booted: Dictionary = view.boot(game, {"test": true, "scenes": "off"})
	for i in 3: await frame()
	var row := {"booted": booted.ok, "text_boxes": view.text_boxes, "boot_text": view.last_text, "boot_box": view.n64_ui.dlg_on}
	view.module_event("challenge_failed", {})
	row["event_text"] = view.last_text
	view.restore_checkpoint(view.checkpoint)
	await frame()
	row["restore_text"] = view.last_text
	row["restore_box"] = view.n64_ui.dlg_on
	row["description"] = view.runtime.rooms[view.runtime.state.location].description
	rows[label] = row
	root.remove_child(view)
	view.queue_free()
	await frame()

func run() -> void:
	root.size = Vector2i(1280, 720)
	await process_frame
	var game = Wire.read_json("res://game.json")
	await probe("off", game.duplicate(true))
	var older: Dictionary = game.duplicate(true)
	older.metadata.presentation.erase("text_boxes")
	await probe("absent", older)
	var f := FileAccess.open(ProjectSettings.globalize_path("res://../gaps2-text.json"), FileAccess.WRITE)
	f.store_string(JSON.stringify(rows, "  ", true))
	f.close()
	print("GAPS2_TEXT ", JSON.stringify(rows))
	quit(0)
