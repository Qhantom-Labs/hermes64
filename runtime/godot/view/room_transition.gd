extends Control
## FEEL2 presentation-only room envelope. Presenter owns canonical action/pause.
signal entry_requested()
signal freeze_requested()
signal black_reached()
signal finished()
const PixelFont = preload("res://look/pixel_font.gd")
const Pack = preload("res://look/pack.gd")
const H := 240
const THROUGH_M := 0.35
const MAX_WALK_M := 2.0
const OUT_SECONDS := 0.22
const IN_SECONDS := 0.18
const QUICK_SECONDS := 0.06
const POSE_FPS := 15.0
const CARD_SECONDS := 0.85
const CARD_FADE_IN := 0.08
const CARD_FADE_OUT := 0.15
var phase := "idle"
var fade := 0.0
var ghost_viewport: SubViewport
var ghost_visual: Node3D
var _width := 320
var _reduced := false
var _elapsed := 0.0
var _ghost_start := Transform3D.IDENTITY
var _ghost_end := Vector3.ZERO
var _walk := false
var _walk_animation: AnimationPlayer
var _pose_key := -1
var _entry_pending := false
var _freeze_pending := false
var _room_name := ""
var _card_left := 0.0
var release_provider: Callable
var release_dead_zone := 0.18

class FreezeTail extends Node:
	var transition
	func _physics_process(_delta: float) -> void:
		transition._freeze_boundary()

func _ready() -> void:
	process_physics_priority = 90
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	focus_mode = Control.FOCUS_NONE
	z_index = 100
	texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	set_width(_width)
	var tail := FreezeTail.new()
	tail.name = "transition_tick_tail"
	tail.process_physics_priority = 200
	tail.transition = self
	add_child(tail)

func begin(source_world: Node3D, source_camera: Camera3D, source_visual: Node3D, exit_world: Vector3, outward: Vector3, reduced_motion := false) -> bool:
	if active() or not is_instance_valid(source_world) or not is_instance_valid(source_camera): return false
	if not source_world.is_inside_tree() or not source_world.is_ancestor_of(source_camera): return false
	if not exit_world.is_finite() or not outward.is_finite(): return false
	var direction := Vector3(outward.x, 0, outward.z)
	if direction.length_squared() < 0.000001: return false
	direction = direction.normalized()
	if source_visual != null:
		if not is_instance_valid(source_visual) or source_visual is PhysicsBody3D or not source_world.is_ancestor_of(source_visual): return false
	var copy: Node3D = source_world.duplicate(0) as Node3D
	if copy == null: return false
	# A render-only exit does not need live collision bodies whose queued
	# disposal depends on render cadence.
	# Preserve child indices for camera/visual lookup using inert Node3D shells.
	for kind in ["CollisionShape3D","CollisionPolygon3D","CollisionObject3D"]:
		for node in copy.find_children("*",kind,true,false):
			var shell:=Node3D.new()
			shell.name=node.name; shell.transform=node.transform
			node.replace_by(shell); node.free()
	copy.process_mode = Node.PROCESS_MODE_DISABLED
	# Scripts/signals/groups are deliberately not duplicated. Native animation
	# mixers are manual, and the ghost has an entirely separate World3D.
	for node in copy.find_children("*", "WorldEnvironment", true, false):
		if node.environment != null: node.environment = node.environment.duplicate(true)
	for node in copy.find_children("*", "AnimationPlayer", true, false):
		node.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
	for node in copy.find_children("*", "Camera3D", true, false): node.current = false
	ghost_viewport = SubViewport.new()
	ghost_viewport.name = "room_exit_view"
	ghost_viewport.size = Vector2i(_width, H)
	ghost_viewport.own_world_3d = true
	ghost_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	var source_viewport := source_world.get_viewport()
	for property in ["msaa_3d", "screen_space_aa", "use_debanding", "use_hdr_2d", "transparent_bg", "scaling_3d_mode", "scaling_3d_scale", "positional_shadow_atlas_size", "use_taa", "mesh_lod_threshold"]:
		ghost_viewport.set(property, source_viewport.get(property))
	ghost_viewport.add_child(copy)
	add_child(ghost_viewport)
	var camera: Camera3D = _clone_node(source_world,copy,source_camera) as Camera3D
	camera.current = true
	ghost_visual = _clone_node(source_world,copy,source_visual) as Node3D if source_visual != null else null
	_reduced = reduced_motion
	_elapsed = 0.0
	_room_name = ""
	_card_left = 0.0
	_walk = false
	_walk_animation = null
	_pose_key = -1
	if ghost_visual != null:
		_ghost_start = ghost_visual.global_transform
		_ghost_end = Vector3(exit_world.x + direction.x * THROUGH_M, _ghost_start.origin.y, exit_world.z + direction.z * THROUGH_M)
		_walk = not _reduced and _ghost_start.origin.distance_to(_ghost_end) <= MAX_WALK_M
		if _walk:
			for node in ghost_visual.find_children("*", "Skeleton3D", true, false): node.reset_bone_poses()
			for node in ghost_visual.find_children("*", "AnimationPlayer", true, false):
				if node.has_animation("walk"):
					_walk_animation = node
					_walk_animation.play("walk")
					_walk_animation.seek(0.0, true)
					break
	phase = "out"
	fade = 0.0
	_entry_pending = true
	_freeze_pending = true
	queue_redraw()
	return true

# Node.duplicate sanitizes autogenerated @names, so name paths are not stable.
# Ordered child indices are stable in the script-free, immutable scene copy.
func _clone_node(source: Node, copy: Node, original: Node) -> Node:
	var indices := []
	var node := original
	while node != source:
		indices.push_front(node.get_index())
		node=node.get_parent()
	var clone := copy
	for index in indices: clone=clone.get_child(index)
	return clone

func active() -> bool:
	return phase != "idle"

func reveal(room_name: String) -> bool:
	if phase != "black": return false
	_room_name = " ".join(room_name.replace("\r", " ").replace("\n", " ").replace("	", " ").split(" ", false))
	_card_left = CARD_SECONDS if not _room_name.is_empty() else 0.0
	_elapsed = 0.0
	phase = "in"
	fade = 1.0
	queue_redraw()
	return true

func release_input(raw_frame: Dictionary, dead_zone: float) -> bool:
	if phase != "release" or not is_finite(dead_zone) or dead_zone < 0.0 or dead_zone >= 1.0: return false
	for key in raw_frame:
		# MOVE: "heading" is recorded view state, not a held input; it never blocks release.
		if key not in ["digital", "buttons", "analog", "camera", "heading"]: return false
	for key in ["digital", "buttons"]:
		var held = raw_frame.get(key, [])
		if not held is Array or not held.is_empty(): return false
	for key in ["analog", "camera"]:
		var axes = raw_frame.get(key, [0, 0])
		if not axes is Array or axes.size() != 2: return false
		for value in axes:
			if not (value is float or value is int) or not is_finite(float(value)) or absf(float(value)) > 1.0: return false
		if Vector2(axes[0], axes[1]).length() > dead_zone: return false
	phase = "idle"
	_entry_pending = false
	_freeze_pending = false
	queue_redraw()
	finished.emit()
	return true

func cancel() -> void:
	_dispose_ghost()
	phase = "idle"
	fade = 0.0
	_elapsed = 0.0
	_room_name = ""
	_card_left = 0.0
	_entry_pending = false
	_freeze_pending = false
	queue_redraw()

func set_width(width: int) -> void:
	_width = maxi(240, width)
	size = Vector2(_width, H)
	if is_instance_valid(ghost_viewport): ghost_viewport.size = Vector2i(_width, H)
	queue_redraw()

func advance(delta: float) -> void:
	if not is_finite(delta) or delta <= 0.0: return
	_card_left = maxf(0.0, _card_left - delta)
	if phase == "out":
		var duration := QUICK_SECONDS if _reduced else OUT_SECONDS
		_elapsed = minf(_elapsed + delta, duration)
		fade = _elapsed / duration
		if _walk and is_instance_valid(ghost_visual):
			var key := floori((_elapsed + 0.000001) * POSE_FPS)
			if is_instance_valid(_walk_animation) and key != _pose_key:
				_pose_key = key
				var length := _walk_animation.get_animation("walk").length
				_walk_animation.seek(fmod(float(key) / POSE_FPS, length) if length > 0.0 else 0.0, true)
			var direction := _ghost_end - _ghost_start.origin
			var real_actor: bool = ghost_visual.get_meta("real_character", false)
			var yaw := atan2(direction.x, direction.z) if real_actor else atan2(-direction.x, -direction.z)
			var basis := Basis(Vector3.UP, yaw) * Basis.from_scale(_ghost_start.basis.get_scale())
			ghost_visual.global_transform = Transform3D(basis, _ghost_start.origin.lerp(_ghost_end, fade))
		if _elapsed >= duration - 0.0000001:
			phase = "black"
			fade = 1.0
			_dispose_ghost()
			black_reached.emit()
	elif phase == "in":
		var duration := QUICK_SECONDS if _reduced else IN_SECONDS
		_elapsed = minf(_elapsed + delta, duration)
		fade = 1.0 - _elapsed / duration
		if _elapsed >= duration - 0.0000001:
			phase = "release"
			fade = 0.0
	queue_redraw()

func _dispose_ghost() -> void:
	_walk_animation = null
	ghost_visual = null
	if is_instance_valid(ghost_viewport): ghost_viewport.queue_free()
	ghost_viewport = null

func card_layout() -> Dictionary:
	if _room_name.is_empty() or _card_left <= 0.0000001: return {}
	var font = PixelFont.get_font()
	var text := _room_name
	var max_width := _width - 32
	if font.measure(text) > max_width:
		text = ""
		for ch in _room_name:
			if font.measure(text + ch + "...") > max_width: break
			text += ch
		text = text.strip_edges() + "..."
	var width: int = font.measure(text)
	var alpha := clampf((CARD_SECONDS-_card_left)/CARD_FADE_IN,0.0,1.0) * clampf(_card_left/CARD_FADE_OUT,0.0,1.0)
	return {"text":text,"position":Vector2(roundf(float(_width-width)/2.0),32),
		"alpha":alpha,"color":Pack.ui("text", "#e8e0cc"),"shadow":Pack.ui("ink", "#0b0d12")}

func _draw() -> void:
	if phase == "out" and is_instance_valid(ghost_viewport):
		draw_texture_rect(ghost_viewport.get_texture(), Rect2(Vector2.ZERO, size), false)
	if fade > 0.0: draw_rect(Rect2(Vector2.ZERO, size), Color(0, 0, 0, fade))
	var layout := card_layout()
	if not layout.is_empty():
		PixelFont.get_font().draw(self, layout.position, layout.text, Color(layout.color, layout.alpha), Color(layout.shadow, layout.alpha * 0.8))

func _physics_process(_delta: float) -> void:
	if _entry_pending:
		_entry_pending = false
		entry_requested.emit()

func _freeze_boundary() -> void:
	if _freeze_pending and not _entry_pending:
		_freeze_pending = false
		freeze_requested.emit()

func _process(delta: float) -> void:
	advance(delta)
	if phase=="release" and release_provider.is_valid():
		release_input(release_provider.call(),release_dead_zone)

func _exit_tree() -> void:
	cancel()
