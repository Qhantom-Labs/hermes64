extends SceneTree
## L3 texture slots: view/slots.gd swaps the slot atlas on surfaces of the slot's material role (already built and
## added later), hands the emblem sheet to the room's sky_signal presentation, and does nothing without
## theme.texture_slots. Known-bad: a wrong sha256 is refused (no swap).
const Slots = preload("res://view/slots.gd")
const Mat = preload("res://look/n64_mat.gd")
var passed := 0
var failed := 0
func expect(ok: bool, label: String) -> void:
	if ok: passed += 1
	else: failed += 1
	print("PASS " if ok else "FAIL ", label)
func _initialize() -> void:
	call_deferred("run")
func surface(role: String) -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = BoxMesh.new()
	var m := ShaderMaterial.new()
	m.shader = Mat.shader()
	m.set_meta("role", role)
	mi.set_surface_override_material(0, m)
	return mi
func png(path: String, c: Color) -> String:
	var img := Image.create(8, 8, false, Image.FORMAT_RGB8)
	img.fill(c)
	img.save_png(path)
	return FileAccess.get_sha256(path)
func run() -> void:
	var dir := OS.get_user_data_dir()
	var atlas := dir.path_join("slots_probe_atlas.png")
	var sheet := dir.path_join("slots_probe_sheet.png")
	var sha_a := png(atlas, Color(1, 0, 0))
	var sha_s := png(sheet, Color(0, 1, 0))
	var pres := {"sky_signal": {"position": [0, 10, -20]}}
	var room := Node3D.new()
	root.add_child(room)
	var book := surface("book")
	var wall := surface("wall")
	room.add_child(book)
	room.add_child(wall)
	var same: Dictionary = Slots.apply(room, {}, pres)
	expect(is_same(same, pres), "no texture_slots: presentation returned untouched")
	expect(not book.get_surface_override_material(0).get_meta("texture_slot", false), "no texture_slots: no swap")
	var theme := {"texture_slots": {"atlases": {"book": {"path": atlas, "sha256": sha_a, "slots": ["poster"]}},
		"sheets": {"emblem_sky": {"path": sheet, "sha256": sha_s, "consumer": "sky_signal"}}}}
	var out: Dictionary = Slots.apply(room, theme, pres)
	expect(str(out.sky_signal.get("texture", "")) == sheet, "sky_signal gets the emblem sheet")
	expect(not pres.sky_signal.has("texture"), "game presentation data is not mutated (copy)")
	var m: ShaderMaterial = book.get_surface_override_material(0)
	expect(m.get_meta("texture_slot", false), "book surface swapped")
	var t = m.get_shader_parameter("tex_nearest")
	expect(t != null and t.get_image().get_pixel(0, 0).r > 0.9, "swapped texture is the slot atlas")
	expect(not wall.get_surface_override_material(0).get_meta("texture_slot", false), "other roles untouched")
	var late := surface("book")
	room.add_child(late)
	expect(late.get_surface_override_material(0).get_meta("texture_slot", false), "surface added after apply is swapped")
	var own := {"sky_signal": {"position": [0, 10, -20], "texture": "res://own.png"}}
	expect(str(Slots.apply(room, theme, own).sky_signal.texture) == "res://own.png", "a room's own texture wins")
	var detached := Node3D.new()      # the presenter builds a room before adding it to the world
	var d1 := surface("book")
	detached.add_child(d1)
	Slots.apply(detached, theme, {})
	var d2 := surface("book")
	detached.add_child(d2)
	expect(d1.get_surface_override_material(0).get_meta("texture_slot", false), "detached room: built mesh swapped")
	root.add_child(detached)
	expect(d2.get_surface_override_material(0).get_meta("texture_slot", false), "detached room: mesh built after apply swapped on entering the tree")
	var room2 := Node3D.new()
	root.add_child(room2)
	var b2 := surface("book")
	room2.add_child(b2)
	var bad := {"texture_slots": {"atlases": {"book": {"path": atlas, "sha256": "0".repeat(64), "slots": []}}}}
	Slots.apply(room2, bad, {})
	expect(not b2.get_surface_override_material(0).get_meta("texture_slot", false), "known-bad: wrong sha256 -> no swap")
	print("slots_probe failed=%d passed=%d" % [failed, passed])
	quit(1 if failed else 0)
