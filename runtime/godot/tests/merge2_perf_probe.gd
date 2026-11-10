extends Node
## Timestamp marker for tests/merge2_perf.gd. Node priorities are global in the
## SceneTree, so markers at chosen priorities bracket each production consumer
## without editing it. Harness-only; tests/ is never exported.
var sink
var label := ""
func _physics_process(_delta: float) -> void:
	sink.mark("ph:" + label)
func _process(_delta: float) -> void:
	sink.mark("pr:" + label)
