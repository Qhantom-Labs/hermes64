extends SceneTree
const Adapter = preload("res://modules/input_adapter.gd")
class FakeActions:
	extends RefCounted
	var movement := Vector2.ONE
	var pressed := true
	func get_move() -> Vector2: return movement
	func is_pressed(name: String) -> bool: return pressed if name == "primary" else false
	func just_pressed(name: String) -> bool: return pressed if name == "primary" else false
var failures := []
func _initialize() -> void:
	var a = Adapter.new()
	if not a.has_method("begin_tick"):
		print("FAIL provider boundary sampler missing")
		quit(1)
		return
	var source = FakeActions.new()
	a.provider = source
	a.clear()
	if a.just_pressed("primary") or a.get_move() != Vector2.ZERO: failures.append("ownership clears provider-held intent")
	source.pressed = false; source.movement = Vector2.ZERO
	a.begin_tick()
	source.pressed = true
	a.begin_tick()
	if not a.just_pressed("primary"): failures.append("fresh provider edge after neutral works")
	print("MODULE_PROVIDER checks=2 failures=%d" % failures.size())
	for f in failures: print("FAIL ",f)
	quit(0 if failures.is_empty() else 1)
