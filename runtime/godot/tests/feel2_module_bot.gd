extends "res://playtest/module_runner.gd"
## Same physical combat/course bot and production Actions/menu executor. Only its
## between-module planner shares the new solid geometry; no obstacle exemptions.
const SolidNavigation = preload("res://view/solid_navigation.gd")

func target(id: String):
	view.room_root.update_interaction_targets(view.player.position)
	return super.target(id)

func route(at: Vector3) -> PackedVector2Array:
	var nav = SolidNavigation.new()
	var size: Array = view.room_root.data.grid_size
	nav.configure(view.room_root.solid_definitions,Vector2(size[0],size[1]),float(view.player.tuning.capsule_radius_m)+float(view.player.tuning.safe_margin_m),float(view.player.tuning.capsule_height_m),float(view.player.tuning.bounds_margin_m),view.room_root.get("boundary_outline") if view.room_root.get("boundary_outline")!=null else PackedVector2Array())
	var points := nav.route(view.player.position,at,0.65,false)
	var out := PackedVector2Array()
	for p in points: out.append(Vector2(p.x,p.z))
	return out
