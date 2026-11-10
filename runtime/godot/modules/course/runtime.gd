extends RefCounted
## Fixed tick, ordered swept spheres. No ghost, wall clock or animation timing.
var track := {}
var countdown := 0
var elapsed := 0
var history := []
var result := ""
var speed := 0.0
var invalid_motion := 0
static func vector(a: Array) -> Vector3:
	return Vector3(a[0], a[1], a[2])
static func crosses(a: Vector3, b: Vector3, centre: Vector3, radius: float) -> bool:
	var d := b - a
	var t := clampf((centre - a).dot(d) / d.length_squared(), 0.0, 1.0) if d.length_squared() > 0.0000001 else 0.0
	return (a + d * t).distance_to(centre) <= radius
func begin(data: Dictionary, ceiling: float) -> void:
	track = data.duplicate(true)
	countdown = track.countdown_ticks
	elapsed = 0
	history = []
	result = ""
	speed = ceiling
	invalid_motion = 0
func tick(before: Vector3, after: Vector3, paused := false) -> Array:
	var events := []
	if paused or result != "": return events
	if countdown > 0:
		countdown -= 1
		return events
	elapsed += 1
	if elapsed > track.time_limit_ticks:
		result = "failed"
		return events
	if before.distance_to(after) > speed / 60.0 + 0.002:
		invalid_motion += 1
		result = "failed"
		return events
	# Consume in order along the segment; a later sphere never credits a skipped one.
	var cursor := before
	while history.size() < track.checkpoints.size():
		var cp: Dictionary = track.checkpoints[history.size()]
		var centre := vector(cp.position_m)
		if not crosses(cursor, after, centre, float(cp.radius_m)): break
		# Moving away across a gate from its far side is not a forward crossing.
		var prior := vector(track.start_position_m) if history.is_empty() else vector(track.checkpoints[history.size()-1].position_m)
		if (after - before).dot(centre - prior) <= 0.0: break
		history.append(cp.id)
		events.append({"checkpoint": cp.id, "index": history.size()-1, "elapsed_ticks": elapsed})
		cursor = centre
	if history.size() == track.checkpoints.size(): result = "completed"
	return events
func snapshot() -> Dictionary:
	return {"countdown": countdown, "elapsed": elapsed, "history": history.duplicate(), "result": result, "invalid_motion": invalid_motion}
