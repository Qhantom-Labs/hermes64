extends Node3D
## Presentation-only actor. World motion belongs to Player/follower controllers, never the clip clock.
var model: Node3D
var skeleton: Skeleton3D
var animation: AnimationPlayer
var pose_fps := 15.0
var pose_speed := 1.0
var manual_clock := false
var clock := 0.0
var pose_elapsed := 0.0
var pose_tick := -1
var sample_time := 0.0
var clip := ""
var materials := []
var faces := []
var ground_offset := 0.0
var base_expression := 0
func configure(scene: Node3D, row: Dictionary) -> void:
	model = scene
	add_child(model)
	set_meta("real_character", true)
	set_meta("character_id", row.character_id)
	set_meta("placeholder", false)
	for n in model.find_children("*", "Skeleton3D", true, false): skeleton = n
	for n in model.find_children("*", "AnimationPlayer", true, false): animation = n
	if animation != null:
		animation.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
		for name in animation.get_animation_list():
			var a := animation.get_animation(name)
			# Cached character instances share Animation resources: write only when the value
			# differs, because every write emits `changed` to every mixer using the clip.
			if a.loop_mode != Animation.LOOP_LINEAR: a.loop_mode = Animation.LOOP_LINEAR
			for i in a.get_track_count():
				if a.track_get_interpolation_type(i) != Animation.INTERPOLATION_NEAREST: a.track_set_interpolation_type(i, Animation.INTERPOLATION_NEAREST)
	# GLB is already Y-up, metres, floor-origin; retain optional small authored correction only.
	ground_offset = float(row.get("ground_offset",0.0))
	model.position.y = ground_offset
	var shadow := MeshInstance3D.new()
	shadow.name = "shadow_blob"
	var radius := 0.24 if row.source_rig == "quad16_v1" else 0.32
	var vertices := PackedVector3Array([Vector3.ZERO])
	var normals := PackedVector3Array([Vector3.UP])
	var indices := PackedInt32Array()
	for i in 12:
		var angle := TAU * float(i) / 12.0
		vertices.append(Vector3(cos(angle)*radius,0,sin(angle)*radius))
		normals.append(Vector3.UP)
		indices.append_array(PackedInt32Array([0,1+i,1+(i+1)%12]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_INDEX] = indices
	var disk := ArrayMesh.new()
	disk.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,arrays)
	shadow.mesh = disk
	shadow.position.y = 0.012
	shadow.scale.z = 0.7
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.cull_mode = BaseMaterial3D.CULL_DISABLED
	m.albedo_color = Color(0.04,0.04,0.08,0.28)
	shadow.material_override = m
	shadow.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(shadow)
	play_clip("idle")
func play_clip(value: String) -> void:
	if animation == null: return
	if not animation.has_animation(value): value = "idle"
	if value == clip: return
	clip = value
	clock = 0.0
	pose_elapsed = 0.0
	pose_tick = -1
	sample_time = 0.0
	# Godot's glTF import keeps a channel only where it leaves the rest pose, so a bone a clip holds at rest has no
	# track in it and would keep the previous clip's pose (a leg stays bent after sit -> idle). Start every clip from
	# rest so each plays exactly as authored.
	if skeleton != null: skeleton.reset_bone_poses()
	animation.play(clip)
	animation.seek(0.0, true)
func advance_pose(delta: float) -> void:
	if animation == null or clip == "": return
	clock += delta * pose_speed
	pose_elapsed += delta
	var next_tick := floori((pose_elapsed+0.000001)*pose_fps)
	if next_tick == pose_tick: return
	pose_tick = next_tick
	var length := animation.get_animation(clip).length
	var held := floorf((clock + 0.000001) * pose_fps) / pose_fps
	sample_time = fmod(held, length) if length > 0.0 else 0.0
	animation.seek(sample_time, true)
	if clip == "talk" and not faces.is_empty() and int(faces[0].cols) * int(faces[0].rows) >= 4:
		expression(2 + int(floor(clock * 5)) % 2)
	elif not faces.is_empty():
		expression(1 if fmod(clock, 4.0) > 3.85 else base_expression)
func _process(delta: float) -> void:
	if not manual_clock: advance_pose(delta)
func face_velocity(velocity: Vector3) -> void:
	if Vector2(velocity.x,velocity.z).length() > 0.01:
		rotation.y = atan2(velocity.x, velocity.z)
func expression(cell: int) -> void:
	for face in faces:
		var cols: int = face.cols
		var rows: int = face.rows
		var chosen := clampi(cell,0,cols*rows-1)
		# glTF V is down; Blender's atlas cells were indexed bottom-up.
		face.material.set_shader_parameter("uv_offset", Vector2(float(chosen % cols) / cols, float(rows - 1 - chosen / cols) / rows))
