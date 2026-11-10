extends CharacterBody3D
## Fixed 60 Hz locomotion. Intent, velocity, facing and held visual poses stay separate.
const Profile = preload("res://input/profile.gd")
const SolidNavigation = preload("res://view/solid_navigation.gd")
const DT := 1.0 / 60.0
var tuning: Dictionary = Profile.defaults().tuning
var actions
var camera_basis := Basis.IDENTITY
var latched_basis := Basis.IDENTITY
var last_input := Vector2.ZERO
var latched := false
var enabled := true
var simulation_enabled := true
var bounds := Vector2(12, 10)
var focus_point: Variant = null
var actual_velocity := Vector3.ZERO
var desired_velocity := Vector3.ZERO
var was_enabled := true
var facing_yaw := 0.0
var speed_limit := INF # Module ceiling; locomotion remains the sole normal mover.
var room_navigation
var room_placement := {}
var boundary_inset := PackedVector2Array()

## Generic fallback: keep the capsule centre inside the room's walkable floor
## outline (inset by its radius). Projection to the nearest edge point slides.
func clamp_to_floor_outline() -> void:
	if boundary_inset.size() < 3: return
	var p := Vector2(position.x,position.z)
	if Geometry2D.is_point_in_polygon(p,boundary_inset): return
	var best := INF
	var nearest := p
	for i in boundary_inset.size():
		var q := Geometry2D.get_closest_point_to_segment(p,boundary_inset[i],boundary_inset[(i+1)%boundary_inset.size()])
		if p.distance_squared_to(q) < best: best = p.distance_squared_to(q); nearest = q
	position.x = nearest.x; position.z = nearest.y

## Call AFTER the presenter/module chooses an entry or retry position. Correct
## overlapping legacy spawns, never ordinary motion or recorded hash comparisons.
func place_in_room(room) -> Dictionary:
	room_navigation = SolidNavigation.new()
	var size: Array = room.data.grid_size
	bounds = Vector2(float(size[0]),float(size[1]))
	var outline: PackedVector2Array = room.get("boundary_outline") if room.get("boundary_outline") != null else PackedVector2Array()
	room_navigation.configure(room.solid_definitions,bounds,float(tuning.capsule_radius_m)+float(tuning.safe_margin_m),float(tuning.capsule_height_m),float(tuning.bounds_margin_m),outline)
	# MOVE: deterministic floor-outline boundary (inset by the capsule radius).
	boundary_inset = PackedVector2Array()
	if outline.size() >= 3:
		var best_area := 0.0
		for poly in Geometry2D.offset_polygon(outline,-float(tuning.capsule_radius_m)):
			if Geometry2D.is_polygon_clockwise(poly) != Geometry2D.is_polygon_clockwise(outline): continue
			var area := 0.0
			for i in poly.size(): area += poly[i].cross(poly[(i+1)%poly.size()])
			if absf(area) > best_area: best_area = absf(area); boundary_inset = poly
	var before := position
	var safe: Vector3 = room_navigation.safe_spawn(before)
	if safe == Vector3.INF:
		room_placement = {"ok":false,"reason":"no capsule-clear room-entry point within 2m","from":before}
		return room_placement
	if safe != before:
		position = safe.snapped(Vector3.ONE*float(tuning.position_quantum_m))
		velocity = Vector3.ZERO; actual_velocity = Vector3.ZERO
	room_placement = {"ok":true,"adjusted":position != before,"from":before,"to":position}
	return room_placement

func set_facing_yaw(value: float) -> void:
	facing_yaw = Vector2(value,0).x # Canonical float32, like the physical vectors.
	# Keep the symmetric collision capsule axis-aligned. Rotating it for a visual
	# yaw introduces recovery noise despite its nominal rotational symmetry.
	var visual := get_node_or_null("visual")
	if visual != null: visual.rotation.y = facing_yaw + (PI if visual.get_meta("real_character",false) else 0.0)

func _ready() -> void:
	if actions == null: actions = get_node_or_null("/root/Actions")
	if actions != null: tuning = actions.profile.tuning.duplicate()
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = tuning.capsule_radius_m
	capsule.height = tuning.capsule_height_m
	shape.shape = capsule
	shape.position.y = capsule.height * 0.5
	add_child(shape)
	floor_snap_length = tuning.floor_snap_m
	floor_max_angle = deg_to_rad(tuning.slope_max_deg)
	safe_margin = tuning.safe_margin_m
	floor_constant_speed = true

static func horizontal_basis(value: Basis) -> Basis:
	var right := Vector3(value.x.x,0,value.x.z).normalized()
	if right.length_squared() < 0.01: right = Vector3.RIGHT
	var back := right.cross(Vector3.UP).normalized()
	return Basis(right,Vector3.UP,back)

## MOVE: basis of the fixed-tick camera the player actually sees, from the
## recorded frame heading. null for bot/legacy frames (authored basis path).
static func yaw_basis(yaw: float) -> Basis:
	return Basis(Vector3(cos(yaw),0,-sin(yaw)),Vector3.UP,Vector3(sin(yaw),0,cos(yaw)))

func frame_heading() -> Variant:
	if actions == null: return null
	var h = actions.last_frame.get("heading")
	if h is Array and h.size() == 2: return h
	return null

## Basis that currently maps W/A/S/D (observer/test helper; no side effects).
func move_basis() -> Basis:
	if latched: return horizontal_basis(latched_basis)
	var h = frame_heading()
	return yaw_basis(float(h[0])) if h != null else horizontal_basis(camera_basis)

func direction(input: Vector2) -> Vector3:
	if latched and (input.length() < tuning.latch_release_magnitude or absf(input.angle_to(last_input)) > tuning.latch_direction_rad):
		latched = false
	var h = frame_heading()
	if h != null:
		# Console-standard latch: a held direction keeps the world heading of
		# the view at press time. Re-latch on press/release/direction change, or
		# continuously during a deliberate orbit/recenter (h[1] == 1).
		if input.length() >= tuning.latch_release_magnitude and (not latched or int(h[1]) == 1):
			latched_basis = yaw_basis(float(h[0])); latched = true
		var view_basis := latched_basis if latched else yaw_basis(float(h[0]))
		last_input = input
		return (view_basis.x * input.x + view_basis.z * input.y).limit_length()
	var basis := horizontal_basis(latched_basis if latched else camera_basis)
	last_input = input
	return (basis.x * input.x + basis.z * input.y).limit_length()

func camera_cut(basis: Basis) -> void:
	if last_input.length() > tuning.latch_release_magnitude and not latched and frame_heading() == null:
		latched_basis = camera_basis
		latched = true
	camera_basis = horizontal_basis(basis)

func target_speed(magnitude: float) -> float:
	var cap: float = tuning.walk_modifier_cap
	if magnitude <= cap:
		return float(tuning.walk_speed_mps) * pow(magnitude/cap, float(tuning.magnitude_curve_power))
	return lerpf(tuning.walk_speed_mps,tuning.run_speed_mps,pow((magnitude-cap)/(1.0-cap),float(tuning.magnitude_curve_power)))

func _physics_process(_delta: float) -> void:
	motion_tick()

func motion_tick() -> void:
	if not simulation_enabled: actual_velocity = Vector3.ZERO; return
	if not enabled or actions == null:
		velocity = Vector3.ZERO; actual_velocity = Vector3.ZERO; desired_velocity = Vector3.ZERO
		latched = false; last_input = Vector2.ZERO; was_enabled = false
		return
	was_enabled = true
	var input: Vector2 = actions.get_move()
	var raw: Vector2 = actions.get_raw_move()
	# A one-tick real neutral releases the cut latch, regardless of the virtual-stick tail.
	if raw.length() < tuning.latch_release_magnitude: latched = false
	var dir := direction(input)
	var speed := minf(target_speed(input.length()),speed_limit)
	if focus_point != null: speed = minf(speed,tuning.focus_speed_mps)
	desired_velocity = dir.normalized() * speed
	var horizontal := Vector3(velocity.x,0,velocity.z)
	var braking := desired_velocity.length() < horizontal.length() or horizontal.dot(desired_velocity) < 0.0
	horizontal = horizontal.move_toward(desired_velocity,float(tuning.brake_mps2 if braking else tuning.accel_mps2)*DT)
	velocity.x = horizontal.x; velocity.z = horizontal.z
	# Flat support already has floor_snap adhesion. A diagonal downward sweep
	# made native capsule recovery change horizontal velocity with render cadence.
	# Keep ground pull on slopes and gravity in air, not into an exact flat floor.
	velocity.y = (0.0 if get_floor_normal().is_equal_approx(Vector3.UP) else -float(tuning.ground_pull_mps)) if is_on_floor() else velocity.y - float(tuning.gravity_mps2)*DT
	var before := position
	assist_step(horizontal * DT)
	move_and_slide()
	# A flat support plane defines an exact resting height. Native capsule recovery
	# otherwise oscillates within safe_margin according to collision insertion order.
	if is_on_floor() and get_floor_normal().is_equal_approx(Vector3.UP):
		var ground_query := PhysicsRayQueryParameters3D.create(global_position+Vector3.UP*floor_snap_length,global_position-Vector3.UP*floor_snap_length)
		ground_query.exclude = [get_rid()]
		var ground := get_world_3d().direct_space_state.intersect_ray(ground_query)
		if not ground.is_empty() and ground.normal.is_equal_approx(Vector3.UP):
			position.y = ground.position.y + safe_margin
			velocity.y = 0.0
	position.x = clampf(position.x,tuning.bounds_margin_m,bounds.x-tuning.bounds_margin_m)
	position.z = clampf(position.z,tuning.bounds_margin_m,bounds.y-tuning.bounds_margin_m)
	clamp_to_floor_outline()
	# Canonicalize the simulated position, NOT just the hash: removes sub-margin
	# native recovery drift when a replay recreates a collision space (0.1 mm proposal).
	position = position.snapped(Vector3.ONE * float(tuning.position_quantum_m))
	actual_velocity = (position-before)/DT
	var aim: Vector3 = (focus_point-position) if focus_point != null else dir
	aim.y = 0
	if aim.length() > 0.0001:
		var cap: float = tuning.turn_moving_deg_s if Vector2(actual_velocity.x,actual_velocity.z).length() > tuning.still_speed_mps else tuning.turn_still_deg_s
		# Authoritative scalar never round-trips through Node3D's float transform
		# decomposition, whose cache invalidation differs with rendering/query order.
		set_facing_yaw(rotate_toward(facing_yaw,atan2(-aim.x,-aim.z),deg_to_rad(cap)*DT))

func assist_step(motion: Vector3) -> void:
	var height: float = tuning.step_height_m
	if height <= 0 or not is_on_floor() or motion.length() < 0.0001: return
	var obstruction := KinematicCollision3D.new()
	if not test_move(global_transform,motion,obstruction): return
	if obstruction.get_normal().dot(Vector3.UP) >= cos(floor_max_angle): return
	var lifted := global_transform.translated(Vector3.UP * height)
	if test_move(global_transform,Vector3.UP*height) or test_move(lifted,motion): return
	# Probe the top beyond the capsule's rounded nose. A swept capsule's edge
	# normal is not the tread normal and rejects even a low stair at low speed.
	var nose := global_position + motion.normalized() * (float(tuning.capsule_radius_m) + motion.length() + safe_margin)
	var query := PhysicsRayQueryParameters3D.create(nose + Vector3.UP*(height+safe_margin),nose-Vector3.UP*floor_snap_length)
	query.exclude = [get_rid()]
	var landing := get_world_3d().direct_space_state.intersect_ray(query)
	if landing.is_empty() or landing.normal.dot(Vector3.UP) < cos(floor_max_angle): return
	var rise: float = landing.position.y - global_position.y
	if rise > safe_margin and rise <= height + safe_margin: position.y += rise + safe_margin
