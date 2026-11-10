extends SceneTree
const Presenter = preload("res://view/presenter.gd")
const Wire = preload("res://core/wire.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var game: Dictionary = Wire.read_json(ProjectSettings.globalize_path("res://../evidence/last-light-1/game.json"))
	var view = Presenter.new()
	root.add_child(view)
	view.boot(game, {"pack": "res://packs/ruins_harbor/view.json"})
	expect(view.room_root.real_piece_count > 0 and view.resolver.loaded.has("_floor"), "manifest-selected GLB floor replaces primitive proxy")
	expect(view.theme.fog.color == "#35291f", "pack data selects shader fog configuration")
	expect(view.runtime.game == game, "CONTROL visual pack leaves compiled game and semantics unchanged")
	view.queue_free()
	await process_frame
	var thaw: Dictionary = Wire.read_json(ProjectSettings.globalize_path("res://../evidence/thaw-2/game.json"))
	view = Presenter.new()
	root.add_child(view)
	view.boot(thaw)
	var cid: String = thaw.metadata.protagonist
	var actor = view.player.get_node_or_null("visual")
	expect(actor != null and actor.get_meta("character_params", {}).get("suit", {}).get("hood", "") == "silver_faceless", "authored protagonist hood preserved by visual adapter")
	var collectible: Dictionary = view.runtime.collections.cat_purl
	var prop_id: String = thaw.metadata.collectible_prop_ids.cat_purl
	var prop_position := Vector3.ZERO
	for prop in view.runtime.rooms.pod_bay.props:
		if prop.id == prop_id: prop_position = Vector3(prop.position[0], prop.position[1], prop.position[2])
	var cat = view.room_root.get_node_or_null("actor_" + collectible.character)
	expect(cat != null and cat.position == prop_position, "authored collectible prop anchor positions character")
	expect(view.room_root.get_node_or_null("props/" + prop_id) == null, "character-bound collectible has no duplicate prop proxy")
	view.dispatch("collect:cat_purl")
	expect(view.room_root.get_node_or_null("props/" + prop_id) == null and view.followers.size() == 1, "collected actor stays single visible follower")
	view.queue_free()
	await process_frame
	print("THEME SUMMARY passed=%d failed=%d" % [passed, failed])
	quit(0 if failed == 0 else 1)
