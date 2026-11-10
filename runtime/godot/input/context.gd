extends RefCounted
## Presentation selection only; dispatch remains the authoritative story boundary.
var target_id := ""
var uses := {}
var idle_ticks := 0
var alpha := 1.0

func position_for(view, id: String) -> Variant:
	if view.module_host != null and (id.begins_with("challenge:start:") or id.begins_with("checkpoint:")):
		var at: Vector3 = view.module_host.anchor(id)
		return null if at == Vector3.INF else at
	var positions: Dictionary = view.room_root.target_positions
	if positions.has(id): return positions[id]
	if id.begins_with("interact:"):
		for interaction in view.runtime.game.interactions:
			if "interact:" + interaction.id == id: return positions.get(interaction.target)
	return null

func visible_target(view, point: Vector3) -> bool:
	var start: Vector3 = view.player.global_position + Vector3.UP * 0.8
	var end := Vector3(point.x,start.y,point.z)
	if start.distance_to(end) < 0.01: return true
	var query := PhysicsRayQueryParameters3D.create(start,end)
	query.exclude = [view.player.get_rid()]
	return view.world.get_world_3d().direct_space_state.intersect_ray(query).is_empty()

func candidates(view) -> Array:
	var out := []
	var tuning: Dictionary = view.actions.profile.tuning
	for action in view.runtime.actions(view.runtime.state):
		if view.module_host != null and not view.module_host.allows_action(action.id): continue
		var at = position_for(view,action.id)
		if at == null: continue
		var distance := Vector2(view.player.position.x-at.x,view.player.position.z-at.z).length()
		var radius: float = tuning.focus_release_m if action.id == target_id else tuning.focus_acquire_m
		if distance > radius or absf(at.y-view.player.position.y) > tuning.interaction_height_m: continue
		if not visible_target(view,at): continue
		out.append({"id":action.id,"kind":action.kind,"position":at,"distance":distance,"icon":icon_for(action.kind)})
	out.sort_custom(func(a,b): return a.id < b.id if is_equal_approx(a.distance,b.distance) else a.distance < b.distance)
	return out

func select(view) -> Dictionary:
	var choices := candidates(view)
	if target_id != "":
		for candidate in choices:
			if candidate.id == target_id: return candidate
		target_id = ""
	return choices[0] if not choices.is_empty() else {}

func update(view) -> Dictionary:
	if not view.actions.is_pressed("focus") or view.actions.just_pressed("secondary"): target_id = ""
	var candidate := select(view)
	if view.actions.is_pressed("focus") and not candidate.is_empty(): target_id = candidate.id
	idle_ticks += 1
	var mastered := int(uses.get(candidate.get("icon",""),0)) >= int(view.actions.profile.tuning.prompt_fade_after_uses)
	var show := not mastered or idle_ticks >= int(view.actions.profile.tuning.prompt_idle_ticks)
	alpha = move_toward(alpha,1.0 if show else 0.0,1.0/float(view.actions.profile.tuning.prompt_fade_ticks))
	return candidate

func used(verb: String) -> void:
	uses[verb] = int(uses.get(verb,0))+1
	idle_ticks = 0

static func icon_for(kind: String) -> String:
	return {"move":"door","talk":"talk","recall":"talk","collect":"take","take":"take","use":"use","inspect":"look","look":"look","climb":"climb","attack":"attack"}.get(kind,"look")
