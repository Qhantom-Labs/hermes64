extends Node
## Frame-phase timestamp marker for the physical playtest drivers. SceneTree
## priorities are global, so markers at -1000/+1000 bracket every physics and
## process callback of a frame. Harness-only; playtest/ is never exported.
var sink
var label := ""
func _physics_process(_delta: float) -> void:
	sink.frame_mark(label)
func _process(_delta: float) -> void:
	sink.frame_mark(label)
