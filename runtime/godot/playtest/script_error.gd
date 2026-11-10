extends Node
## Deliberate runtime script-error control, never included in release staging.
func _ready() -> void:
	var missing = null
	missing.nonexistent_method()
