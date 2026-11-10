extends SceneTree
const Presenter = preload("res://view/presenter.gd")
const Player = preload("res://view/player.gd")
const Wire = preload("res://core/wire.gd")
var passed := 0
var failed := 0
func expect(ok: bool, text: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", text)
func clipped_ancestor(node: Node) -> bool:
	var parent = node.get_parent()
	while parent != null:
		if parent is ScrollContainer and parent.clip_contents: return true
		parent = parent.get_parent()
	return false
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var p = Player.new()
	expect(p.direction(Vector2(1, 0)).is_equal_approx(Vector3.RIGHT), "camera-relative right movement")
	p.direction(Vector2(0, -1))
	p.camera_cut(Basis(Vector3.UP, PI / 2))
	expect(p.direction(Vector2(0, -1)).is_equal_approx(Vector3.FORWARD), "held direction survives camera cut")
	p.direction(Vector2.ZERO)
	expect(p.direction(Vector2(0, -1)).is_equal_approx(Vector3.LEFT), "release adopts new camera basis")
	p.free()
	# Headless display servers may expose a square dummy window; pin the intended
	# widescreen presentation explicitly, as the rendered/window-resize matrix does.
	root.size = Vector2i(1280,720)
	await process_frame
	var view = Presenter.new()
	root.add_child(view)
	var game = Wire.read_json(ProjectSettings.globalize_path("res://../evidence/last-light-1/game.json"))
	var booted = view.boot(game, {"test": true})
	expect(booted.ok, "compiled game boots real presentation")
	if booted.ok:
		expect(view.viewport.size == Vector2i(427, 240), "widescreen world adds horizontal pixels; keeps 240 scanlines (actual %s, root %s)" % [view.viewport.size,root.get_visible_rect().size])
		expect(view.room_root.name == "fog_street", "room from start location")
		expect(view.camera.position.is_equal_approx(Vector3(6, 8, 16)), "authored camera anchor applied")
		expect(view.room_root.get_node_or_null("props/ferry_bell") != null, "asset-ref prop exists")
		expect(view.action_buttons.has("interact:talk_ferryman"), "legal interactions rendered as usable UI")
		view.action_buttons["interact:talk_ferryman"].pressed.emit()
		expect(view.runtime.state.dialogue.ferry_words == "greeting", "UI action invokes authoritative runtime")
		expect(view.action_buttons.has("choose:ferry_words:greeting:stair"), "dialogue choice UI available")
		view.dispatch("cancel:ferry_words")
		var before = view.runtime.state.tide.duplicate(true)
		for i in 15: await process_frame
		expect(view.runtime.state.tide == before, "rendered frames do not advance tide")
		expect(view.dispatch("move:fog_street:boathouse_path").ok and view.room_root.name == "boathouse", "room transition rebuilds presentation")
		view.dispatch("interact:take_oil")
		expect(view.status_label.text.contains("Sealed lamp oil"), "inventory name visible")
		view.status_label.text = "Long inventory entry\n".repeat(40)
		view.text_label.text = "Long dialogue content ".repeat(300)
		view.sync_n64_ui()
		expect(view.text_pages.size() > 1, "N64 bitmap UI paginates long dialogue without discarding pages")
		expect(view.n64_ui.font != null and view.n64_ui.dlg_on, "LOOK bitmap font/dialogue wired to real state")
		await process_frame
		expect(clipped_ancestor(view.status_label), "arbitrarily long inventory text has clipped scroll region")
		expect(clipped_ancestor(view.text_label), "arbitrarily long dialogue text has clipped scroll region")
		view.dispatch("wait")
		expect(view.runtime.state.tide.tick == 1, "wait UI advances discrete timer")
	view.queue_free()
	await process_frame
	var thaw = Wire.read_json(ProjectSettings.globalize_path("res://../evidence/thaw-2/game.json"))
	view = Presenter.new()
	root.add_child(view)
	view.boot(thaw, {"test": true})
	view.dispatch("collect:cat_purl")
	expect(view.followers.size() == 1 and view.followers.has("cat_purl"), "one found cat produces one follower")
	var c: Dictionary = view.runtime.collections.cat_purl
	expect(view.room_root.get_node_or_null("actor_" + c.character) == null, "found follower removed from resident placeholder to avoid duplication")
	for did in view.runtime.state.dialogue:
		if view.runtime.state.dialogue[did] != "": view.dispatch("cancel:" + did)
	view.dispatch("recall:cat_purl")
	expect(view.followers.size() == 1, "recall never duplicates follower")
	view.queue_free()
	await process_frame
	print("PRESENTATION SUMMARY passed=%d failed=%d" % [passed, failed])
	quit(0 if failed == 0 else 1)
