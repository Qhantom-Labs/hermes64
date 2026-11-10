extends RefCounted
## Combat camera challenge profile (COMBAT lane). Presentation only: it never touches the authored cameras,
## `player.camera_basis` or anything hashed. When a combat attempt starts the view eases (smoothstep over
## camera.blend_ticks physics ticks, 0.5 s by default) from the room's authored fixed camera into a closer combat
## framing, and eases back after the attempt ends. The framing keeps the authored camera's yaw within camera.lean_deg
## (so camera-relative controls, which stay on the authored basis, read the same), sits behind/above the fighters at
## camera.pitch_deg, and pulls back just enough to keep the player and the focus target in frame. No shake ever; reduced motion (Actions option) cuts instead of
## blending and follows with a wider dead zone. Collision: the eye is pulled in front of static geometry (layer 1)
## between it and the fighters, and kept under an interior shell's ceiling.
var presenter
var cam: Camera3D
var profile := {}
var active := false
var weight := 0.0
var centre := Vector3.ZERO
var has_centre := false
var reduced := false
var lean := 0.0
var lean_side := 0.0
## Extra pitch while the fighters line up along the view (eased like the lean).
var lift := 0.0
## Visual scale of the focus target (1 = a player-sized enemy; the boss stand-in is 1.9).
var target_size := 1.0
## Last framing, for tests and the capture harness (never hashed).
var last := {}

func attach(view) -> void:
	presenter = view

func configure(p: Dictionary) -> void:
	profile = p.get("camera", {})

func start() -> void:
	if not bool(profile.get("enabled", true)): return
	active = true
	has_centre = false
	lean_side = 0.0
	lift = 0.0

func stop() -> void:
	active = false

func base_camera() -> Camera3D:
	if presenter == null: return null
	return presenter.exploration_camera() if presenter.has_method("exploration_camera") else presenter.camera

func setting(key: String, fallback):
	if reduced and profile.get("reduced_motion", {}).has(key): return profile.reduced_motion[key]
	return profile.get(key, fallback)

## Cut back to the authored camera at once (room change, load, teardown).
func reset() -> void:
	active = false
	weight = 0.0
	has_centre = false
	release()

func release() -> void:
	if is_instance_valid(cam):
		cam.current = false
		cam.queue_free()
	cam = null
	if presenter != null and is_instance_valid(presenter.camera): base_camera().current = true

## The camera actually drawing the frame (the combat camera while blended in, else the authored one).
func current() -> Camera3D:
	if presenter!=null:
		var follow=presenter.get("follow_camera")
		if follow!=null and is_instance_valid(follow.render_camera) and follow.render_camera.current: return follow.render_camera
	if is_instance_valid(cam) and cam.current: return cam
	return base_camera()

## One physics tick. `player` and `focus` (null when nothing is targeted) are world positions; `others` are the
## other live fighters near the player (kept in frame when the distance range allows).
func tick(player: Vector3, focus, reduce_motion := false, others: Array = [], focus_size := 1.0) -> void:
	reduced = reduce_motion
	target_size = maxf(focus_size, 0.5)
	var authored: Camera3D = base_camera()
	if authored == null or not is_instance_valid(authored): return
	var blend := int(setting("blend_ticks", 30))
	if active: weight = 1.0 if blend <= 0 else minf(1.0, weight + 1.0 / float(blend))
	else: weight = 0.0 if blend <= 0 else maxf(0.0, weight - 1.0 / float(blend))
	# Exactly blend_ticks steps each way (no float drift leaving a 31st tick).
	if weight > 0.99999: weight = 1.0
	elif weight < 0.00001: weight = 0.0
	if weight <= 0.0:
		if cam != null: release()
		return
	if not is_instance_valid(cam):
		cam = Camera3D.new()
		cam.name = "combat_camera"
		presenter.world.add_child(cam)
	for property in ["environment", "attributes", "cull_mask", "near", "far", "keep_aspect"]:
		cam.set(property, authored.get(property))
	var frame := framing(authored, player, focus, others)
	var s := smoothstep(0.0, 1.0, weight)
	var a: Transform3D = authored.global_transform
	var b: Transform3D = frame.transform
	var qa := a.basis.get_rotation_quaternion()
	var qb := b.basis.get_rotation_quaternion()
	cam.global_transform = Transform3D(Basis(qa.slerp(qb, s)), a.origin.lerp(b.origin, s))
	cam.fov = lerpf(authored.fov, float(frame.fov), s)
	if not cam.current: cam.current = true
	last = {"weight": weight, "eased": s, "distance": frame.distance, "pitch_deg": frame.pitch_deg, "lean_deg": rad_to_deg(lean),
		"lift_deg": rad_to_deg(lift),
		"origin": [cam.global_position.x, cam.global_position.y, cam.global_position.z], "centre": [centre.x, centre.y, centre.z],
		"pulled_in": frame.pulled_in, "ceiling": frame.ceiling, "fov": cam.fov}

## Combat framing for this tick: yaw from the authored camera, centre between player and focus (smoothed with a
## dead zone), distance fitted to the fighters' spread within [min, max].
func framing(authored: Camera3D, player: Vector3, focus, others: Array = []) -> Dictionary:
	var fwd := -authored.global_transform.basis.z
	fwd.y = 0.0
	fwd = fwd.normalized() if fwd.length() > 0.001 else Vector3(0, 0, -1)
	var right := Vector3(-fwd.z, 0.0, fwd.x)
	# Lean and lift: when the player and the focus target line up along the view (one body would cover the other:
	# the target beyond the player, or a target standing between the camera and the player), orbit the view up to
	# lean_deg toward the side that separates them and raise it up to overlap_pitch_deg (a steeper view spreads ground
	# positions apart on screen). Big robots widen the window (their bodies cover more). Bounded and eased, with
	# hysteresis on the side; controls stay on the authored camera basis. Reduced motion: neither.
	var target_lean := 0.0
	var target_lift := 0.0
	var lean_max := deg_to_rad(float(setting("lean_deg", 10.0)))
	var lift_max := deg_to_rad(float(setting("overlap_pitch_deg", 0.0)))
	if focus is Vector3 and (lean_max > 0.0 or lift_max > 0.0):
		var v: Vector3 = focus - player
		var a := v.dot(right)
		var b := v.dot(fwd)
		if absf(b) > 0.2:
			if lean_side == 0.0 or absf(a) > 0.6: lean_side = 1.0 if a >= 0.0 else -1.0
			var cover := 2.5 * maxf(1.0, target_size)
			var align := clampf(absf(b) / 1.5, 0.0, 1.0) * clampf(1.0 - absf(a) / cover, 0.0, 1.0)
			# Screen separation grows as a + b * lean: lean with the lateral side when the target is beyond the
			# player, against it when the target is in front.
			target_lean = lean_side * signf(b) * lean_max * align
			target_lift = lift_max * align
	var rate := float(setting("follow_rate", 0.14))
	lean = target_lean if not has_centre else lean + (target_lean - lean) * rate
	lift = target_lift if not has_centre else lift + (target_lift - lift) * rate
	if absf(lean) > 0.0001:
		fwd = fwd.rotated(Vector3.UP, lean)
		right = Vector3(-fwd.z, 0.0, fwd.x)
	var w := float(profile.get("target_weight", 0.4))
	var desired := player
	if focus is Vector3: desired = player.lerp(focus, w)
	# Spread of everything that should stay in frame, measured from the desired centre.
	var lateral := 0.0
	var depth := 0.0
	var points := [player] + ([focus] if focus is Vector3 else [])
	var near_r := float(profile.get("others_radius_m", 4.0))
	for p in others:
		if p is Vector3 and Vector2(p.x - player.x, p.z - player.z).length() <= near_r: points.append(p)
	for p in points:
		var sep: Vector3 = p - desired
		lateral = maxf(lateral, absf(sep.dot(right)))
		depth = maxf(depth, -sep.dot(fwd))
	if not has_centre:
		centre = desired
		has_centre = true
	else:
		var delta := desired - centre
		var dz := float(setting("dead_zone_m", 0.3))
		if delta.length() > dz:
			centre += (delta - delta.normalized() * dz) * float(setting("follow_rate", 0.14))
	var fov := float(profile.get("fov_deg", 50.0))
	var half_h := deg_to_rad(fov) * 0.5
	var dimensions: Vector2 = presenter.world.get_viewport().get_visible_rect().size
	var half_w: float = atan(tan(half_h) * dimensions.x / dimensions.y)
	var distance := float(profile.get("distance_m", 5.2))
	# Big robots keep their whole body in frame: the margin grows with the target's visual scale.
	var margin := float(profile.get("fit_margin_m", 1.1)) + 0.6 * maxf(0.0, target_size - 1.0)
	distance = maxf(distance, (lateral + margin) / tan(half_w) + depth)
	distance = clampf(distance, float(profile.get("min_distance_m", 3.4)), float(profile.get("max_distance_m", 8.5)))
	var pitch := deg_to_rad(float(profile.get("pitch_deg", 33.0))) + lift
	var look := centre + Vector3.UP * float(profile.get("look_height_m", 0.85))
	# Fit full bodies in the VERTICAL frustum too. A far focus pulls the centre
	# forward: fitting only lateral spread/depth can leave the player's centre
	# visible while cropping its feet at the bottom of a widescreen frame.
	var forward := fwd*cos(pitch)-Vector3.UP*sin(pitch)
	var up := fwd*sin(pitch)+Vector3.UP*cos(pitch)
	for point in points:
		var height := 1.5*target_size if focus is Vector3 and point == focus else 1.5
		for y in [0.05,height]:
			var offset: Vector3 = point+Vector3.UP*y-look
			distance=maxf(distance,absf(offset.dot(up))/(tan(half_h)*0.82)-offset.dot(forward))
	distance=clampf(distance,float(profile.get("min_distance_m",3.4)),float(profile.get("max_distance_m",8.5)))
	var eye := look - fwd * distance * cos(pitch) + Vector3.UP * distance * sin(pitch)
	var ceiling := false
	var shell: Dictionary = presenter.room_root.shell_info if presenter.room_root != null else {}
	if not shell.is_empty() and not presenter.room_root.presentation.get("exterior", false):
		var top := float(shell.get("meta", {}).get("height", 3.0)) - float(profile.get("ceiling_margin_m", 0.35))
		if eye.y > top:
			eye.y = maxf(look.y + 0.2, top)
			ceiling = true
	var pulled := false
	var space = presenter.world.get_world_3d().direct_space_state if presenter.world.is_inside_tree() else null
	if space != null:
		var query := PhysicsRayQueryParameters3D.create(look, eye, 1)
		query.exclude = [presenter.player.get_rid()]
		var hit: Dictionary = space.intersect_ray(query)
		if not hit.is_empty():
			var back: Vector3 = (look - hit.position).normalized()
			eye = hit.position + back * 0.3
			pulled = true
	var basis := Basis.looking_at(look - eye, Vector3.UP) if (look - eye).length() > 0.01 else authored.global_transform.basis
	# A pack's distance ceiling (or a wall) can prevent further dollying out.
	# Widen within the existing 35..75 degree readability range rather than crop
	# a fighter. Reduced motion uses a stable wide lens, never zoom pumping.
	var tangent := tan(deg_to_rad(fov)*0.5)
	for point in points:
		var height := 1.5*target_size if focus is Vector3 and point == focus else 1.5
		for y in [0.05,height]:
			var offset: Vector3 = point+Vector3.UP*y-eye
			var depth_to_eye := maxf(0.05,-offset.dot(basis.z))
			tangent=maxf(tangent,absf(offset.dot(basis.y))/(depth_to_eye*0.82))
			tangent=maxf(tangent,absf(offset.dot(basis.x))/(depth_to_eye*dimensions.x/dimensions.y*0.9))
	fov = 75.0 if reduced else minf(75.0,rad_to_deg(2.0*atan(tangent)))
	return {"transform": Transform3D(basis, eye), "fov": fov, "distance": eye.distance_to(look),
		"pitch_deg": rad_to_deg(asin(clampf((eye.y - look.y) / maxf(eye.distance_to(look), 0.001), -1.0, 1.0))),
		"pulled_in": pulled, "ceiling": ceiling}

func dispose() -> void:
	release()
	presenter = null
