extends SceneTree
## ROOF: room presentation "sky_signal" (generated in-engine: disc + placeholder star, halo, optional beam, optional
## texture slot) and the room-level rain hook. Presentation only; any game can use either.
const Room = preload("res://view/room.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var room = Room.new()
	room.theme = {}
	root.add_child(room)
	expect(room.sky_signal({}) == null, "no sky_signal -> nothing built")
	var cfg := {"position": [0, 20, -30], "size_m": 10.0, "points": 5, "beam_from": [0, -5, -10]}
	var sig: Node3D = room.sky_signal(cfg)
	expect(sig != null and sig.get_meta("placed", "") == "sky", "sky_signal builds a 'sky' node (structural for the audit)")
	expect(sig.get_node_or_null("sign") != null and sig.get_node_or_null("beam") != null, "disc+emblem mesh and beam")
	expect(sig.get_node_or_null("emblem") == null, "no texture -> placeholder star, no textured quad")
	var tris: int = room.triangle_count(sig)
	# disc 24 + rim 48 + star 10 + halo quad 2 + beam 4
	expect(tris == 88, "triangle cost is fixed and small: %d" % tris)
	var six = room.sky_signal({"position": [0, 20, -30], "points": 6})
	expect(room.triangle_count(six.get_node("sign")) == 24 + 48 + 12, "star point count is data")
	var img := Image.create(16, 16, false, Image.FORMAT_RGBA8)
	img.fill(Color(1, 1, 1, 1))
	var path := OS.get_user_data_dir().path_join("sky_signal_test.png")
	img.save_png(path)
	var tex = room.sky_signal({"position": [0, 20, -30], "texture": path})
	expect(tex.get_node_or_null("emblem") != null, "texture slot: a loadable image replaces the star with a textured quad")
	expect(room.triangle_count(tex.get_node("sign")) == 72, "texture slot: disc without star")
	var miss = room.sky_signal({"position": [0, 20, -30], "texture": "/no/such/file.png"})
	expect(miss.get_node_or_null("emblem") == null, "missing texture falls back to the placeholder star")
	var Weather = preload("res://view/weather.gd")
	expect(not Weather.config_from({}, {"weather": {"rain": {"enabled": true, "streaks": 50}}}).is_empty(), "room rain block turns rain on")
	print("sky_signal_test passed=%d failed=%d" % [passed, failed])
	quit(1 if failed else 0)
