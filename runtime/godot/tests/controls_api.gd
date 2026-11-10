extends SceneTree
var failed := 0
func check(value: bool, label: String) -> void:
	if not value:
		failed += 1
		printerr("FAIL ", label)
func _initialize() -> void:
	if not ResourceLoader.exists("res://input/actions.gd"):
		printerr("FAIL controls action provider missing")
		quit(1)
		return
	var script = load("res://input/actions.gd")
	var actions = script.new()
	check(actions.get_move() == Vector2.ZERO, "neutral before first tick")
	actions.advance({"digital":["primary"]})
	check(actions.is_pressed("primary"), "held canonical action")
	check(actions.just_pressed("primary"), "rising canonical edge")
	check(actions.just_pressed("primary"), "edge reads are idempotent")
	actions.advance({"digital":["primary"]})
	check(not actions.just_pressed("primary"), "held has no second edge")
	actions.advance({})
	check(not actions.is_pressed("primary"), "omitted input releases")
	check(not actions.is_pressed("unknown"), "unknown name safe")
	actions.free()
	print("CONTROLS API failures=", failed)
	quit(0 if failed == 0 else 1)
