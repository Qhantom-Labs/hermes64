extends SceneTree
const ActionsType=preload("res://input/actions.gd")
var failures:=[]
var checks:=0
func check(ok: bool,label: String) -> void:
	checks+=1
	if not ok: failures.append(label);printerr("FAIL ",label)
func _initialize() -> void:
	var plain=ActionsType.new();var orbit=ActionsType.new()
	plain.configure({"version":1});orbit.configure({"version":1})
	for i in 60:
		var digital: Array=["move_up","run"] if i<40 else []
		plain.advance({"digital":digital})
		orbit.advance({"digital":digital+["camera_left","camera_down","camera_recenter"],"buttons":["camera_right"],"camera":[1,0.5]})
		check(plain.get_move()==orbit.get_move(),"right-stick orbit cannot take keyboard movement device at tick %d"%i)
		check(JSON.stringify(plain.snapshot(),"",true,true)==JSON.stringify(orbit.snapshot(),"",true,true),"orbit commands never alter canonical input/replay state at tick %d"%i)
	plain.free();orbit.free()
	print("CONTROLS ORBIT INPUT ",JSON.stringify({"checks":checks,"failures":failures}))
	quit(0 if failures.is_empty() else 1)
