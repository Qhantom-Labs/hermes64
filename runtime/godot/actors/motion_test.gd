extends "res://view/player.gd"
## Test-only observer: measure completed native physics steps, not pre-step signals.
signal stepped
var seconds := 0.0
var steps := 0
func _physics_process(delta: float) -> void:
	super._physics_process(delta)
	seconds += delta
	steps += 1
	stepped.emit()
