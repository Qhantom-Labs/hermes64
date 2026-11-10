extends RefCounted
## NEW-CLIPS seam. Real clips are phase-locked: the host picks the key from the fixed-tick combat
## state (`show`), so a clip clock never drives gameplay. An actor without the clips falls back to
## conspicuous labelled POSE TEST poses on the existing rig, never to a silent idle.
const REQUIRED = ["idle_combat", "swing", "hurt", "death", "roll", "block"]
const FPS := 15.0
var placeholder := false
var missing := []
var actor
var held_pose := ""
var shown := ""
var weapon: Node3D = null
var hidden_props := []
var face_cells := {}
func bind(value, required: Array = REQUIRED) -> void:
	release_weapon()
	actor = value
	held_pose = ""
	shown = ""
	missing.clear()
	if actor == null: placeholder = true; missing = required.duplicate(); return
	for clip in required:
		if not has_clip(clip): missing.append(clip)
	placeholder = not missing.is_empty()
	actor.set_meta("module_animation_owner", true)
	actor.set_meta("module_pose_placeholder", placeholder)
	if not placeholder and actor.get("manual_clock") != null: actor.manual_clock = true
func has_clip(clip: String) -> bool:
	return actor != null and actor.get("animation") != null and actor.animation.has_animation(clip)
## Exact key time k/15 s, as the actor's own 15 fps sampler uses (Godot's key lookup matches a key
## time approximately, so float32 key times still hit). The actor makes every clip LOOP_LINEAR, where a
## seek to the clip length wraps to key 0; the last key is sampled 1 µs before it, inside the lookup's
## match tolerance and below the wrap.
static func key_time(key: int, length := 1.0) -> float:
	return minf(float(key) / FPS, length - 0.000001)
const OPTIONAL_FALLBACK = {"swing2":"swing", "swing3":"swing", "charge":"swing", "dash_attack":"swing", "parry":"block"}
func resolve_clip(clip: String) -> String:
	return OPTIONAL_FALLBACK.get(clip, clip) if not has_clip(clip) else clip
func show(clip: String, key: int) -> void:
	if actor == null or not is_instance_valid(actor): return
	clip = resolve_clip(clip)
	actor.set_meta("module_clip", clip)
	actor.set_meta("module_key", key)
	if has_clip(clip):
		var token := clip + ":" + str(key)
		if token == shown: return
		shown = token
		actor.manual_clock = true
		actor.play_clip(clip)
		actor.animation.seek(key_time(key, actor.animation.get_animation(clip).length), true)
		if not face_cells.is_empty(): actor.expression(int(face_cells.get(clip, 0)))
		return
	shown = ""
	pose_placeholder(clip)
## Compatibility entry (pre-MERGE3 callers): the first key of the clip.
func play(clip: String) -> void:
	show(clip, 0)
func pose_placeholder(clip: String) -> void:
	if held_pose == clip: return
	held_pose = clip
	# Test-only original held poses, not a claim of delivered combat animation.
	if actor.get("skeleton") == null: return
	if actor.get("animation") != null: actor.animation.stop()
	actor.clip = ""
	var skeleton: Skeleton3D = actor.skeleton
	skeleton.reset_bone_poses()
	for name in ["upper_arm_l", "upper_arm_r", "spine", "pelvis"]:
		var index := skeleton.find_bone(name)
		if index < 0: continue
		var angles := Vector3.ZERO
		if name.begins_with("upper_arm"):
			angles.x = -0.7 if clip == "idle_combat" else -1.25
			if clip == "swing": angles.z = -0.8 if name.ends_with("r") else 0.4
		if name == "spine": angles.x = {"hurt":0.4, "death":1.2, "roll":1.0, "block":-0.2}.get(clip, 0.0)
		skeleton.set_bone_pose_rotation(index, Quaternion.from_euler(angles))
## The weapon rides a BoneAttachment3D on hand_r with the documented grip (rotation common to the
## cast, translation per character). Stance props in the hands are hidden while combat owns the actor.
func attach_weapon(node: Node3D, grip: Dictionary, rotation: Array, bone := "hand_r") -> bool:
	release_weapon()
	if actor == null or node == null or actor.get("skeleton") == null: return false
	var skeleton: Skeleton3D = actor.skeleton
	if skeleton.find_bone(bone) < 0: return false
	for prop in actor.find_children("kit_acc_hand_*", "Node3D", true, false):
		if prop.visible:
			prop.visible = false
			hidden_props.append(prop)
	var attachment := BoneAttachment3D.new()
	attachment.name = "combat_weapon"
	attachment.bone_name = bone
	skeleton.add_child(attachment)
	attachment.add_child(node)
	var t: Array = grip.get("translation", [0, 0, 0])
	node.transform = Transform3D(Basis(Quaternion(rotation[0], rotation[1], rotation[2], rotation[3])), Vector3(t[0], t[1], t[2]))
	weapon = attachment
	return true
func release_weapon() -> void:
	for prop in hidden_props:
		if is_instance_valid(prop): prop.visible = true
	hidden_props.clear()
	if weapon != null and is_instance_valid(weapon): weapon.free()
	weapon = null
func release() -> void:
	held_pose = ""
	shown = ""
	release_weapon()
	if actor == null or not is_instance_valid(actor): return
	actor.set_meta("module_animation_owner", false)
	if actor.get("skeleton") != null: actor.skeleton.reset_bone_poses()
	if actor.has_method("play_clip"): actor.play_clip("idle")
