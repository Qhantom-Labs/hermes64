extends SceneTree
class Resolver:
	extends RefCounted
	var characters := []
func _initialize() -> void:
	var bindings = preload("res://modules/bindings.gd").new()
	var resolver = Resolver.new()
	var passed: bool = bindings.configure(null,resolver)
	passed = passed and not bindings.configure({"api_version":"999","bindings":{}},resolver)
	passed = passed and not bindings.configure({"api_version":"1.0.0","bindings":{"player":{"character_id":"unbound","sha256":"fake"}}},resolver)
	print("MODULE_BINDINGS checks=3 failures=%d" % (0 if passed else 1))
	quit(0 if passed else 1)
