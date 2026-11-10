extends RefCounted
## Finite region bindings; door guards alone own ability/key gates.
var runtime
var links := {}
func configure(value) -> void:
	runtime = value
	links = runtime.modules.entities("regions", "links")
func eligible(action: String, position: Vector3, anchor: Vector3) -> bool:
	if position.distance_to(anchor) > 1.1: return false
	if not action.begins_with("move:"): return false
	return runtime.actions(runtime.state).any(func(a): return a.id == action)
func arrival(room_id: String) -> Vector3:
	for region in runtime.modules.regions.values():
		if region.room == room_id:
			var p: Array = runtime.modules.checkpoints[region.checkpoint].position_m
			return Vector3(p[0], p[1], p[2])
	return Vector3.INF
