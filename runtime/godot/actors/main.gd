extends "res://main.gd"
## Inherits the real main.gd capture_all pipeline without a second screenshot renderer.
func boot(game: Dictionary, opts: Dictionary = {}) -> Dictionary:
	resolver = preload("res://actors/assets.gd").new()
	var result: Dictionary = super.boot(game, opts)
	if result.ok:
		var bridge = preload("res://actors/bridge.gd").new()
		add_child(bridge)
		bridge.attach(self)
		if not finalize_room_entry().ok: return {"ok":false,"reason":entry_error}
		checkpoint = physical_checkpoint()
	return result

func capture(path: String) -> bool:
	var ok: bool = await super.capture(path)
	var rows := []
	var candidates: Array = room_root.get_children() + [player.get_node_or_null("visual")]
	for n in candidates:
		if n == null or not n.get_meta("real_character",false): continue
		var box: AABB = room_root.world_aabb(n)
		var p: Vector3 = n.global_position
		var low := Vector2(INF,INF)
		var high := Vector2(-INF,-INF)
		for corner in 8:
			var point := camera.unproject_position(box.get_endpoint(corner))
			low = low.min(point)
			high = high.max(point)
		var pixels := high - low
		rows.append({"node":str(n.name),"character":n.get_meta("character_id"),"position":[p.x,p.y,p.z],"yaw":n.global_rotation_degrees.y,"height_m":box.size.y,"screen_extent_px":[absf(pixels.x),absf(pixels.y)],"in_frustum":camera.is_position_in_frustum(box.get_center()),"clip":n.clip,"pose_fps":n.pose_fps})
	var f := FileAccess.open(path.get_basename()+"-characters.json",FileAccess.WRITE)
	f.store_string(JSON.stringify({"room":runtime.state.location,"actors":rows},"	"))
	f.close()
	return ok
