extends Node
## Presentation metadata and animation wiring, separate from authoritative story/save state.
var presenter
var previous_followers := {}
func attach(value) -> void:
	process_physics_priority = 10
	presenter = value
	presenter.room_entered.connect(place)
	presenter.state_changed.connect(dialogue)
	place(presenter.runtime.state.location)
func place(_room: String) -> void:
	var metadata: Dictionary = presenter.room_root.presentation.get("characters",{})
	var protagonist: String = presenter.runtime.game.metadata.get("protagonist","")
	var player_meta: Dictionary = metadata.get(protagonist,{})
	if player_meta.has("position"):
		presenter.player.position = presenter.room_root.vector(player_meta.position)
	presenter.player.set_facing_yaw(deg_to_rad(float(player_meta.get("yaw",0))))
	for cid in metadata:
		var actor = presenter.room_root.get_node_or_null("actor_"+cid)
		if actor != null:
			var row: Dictionary = metadata[cid]
			if row.has("scale"): actor.scale = presenter.room_root.vector(row.scale)
			if actor.get_meta("real_character",false): actor.play_clip(rest_clip(actor))
## Authored room clip (presentation characters.<id>.clip, e.g. a seated captive); the actor falls back to idle.
func rest_clip(n) -> String:
	return str(presenter.room_root.presentation.get("characters",{}).get(str(n.name).trim_prefix("actor_"),{}).get("clip","idle"))
func dialogue(_result: Dictionary) -> void:
	for n in presenter.room_root.get_children():
		if n.get_meta("real_character",false): n.play_clip(rest_clip(n))
	for did in presenter.runtime.state.dialogue:
		if presenter.runtime.state.dialogue[did] == "": continue
		for d in presenter.runtime.game.dialogues:
			if d.id != did: continue
			var cid: String = d.get("character",d.get("character_id",""))
			var actor = presenter.room_root.get_node_or_null("actor_"+cid)
			if actor != null and actor.get_meta("real_character",false): actor.play_clip("talk")
func _physics_process(_delta: float) -> void:
	if presenter == null or presenter.player == null: return
	var actor = presenter.player.get_node_or_null("visual")
	if actor != null and actor.get_meta("real_character",false) and not actor.get_meta("module_animation_owner",false):
		var speed: float = Vector2(presenter.player.actual_velocity.x,presenter.player.actual_velocity.z).length()
		actor.manual_clock = true
		if actor.locomotion.is_empty():
			actor.pose_speed = speed / float(presenter.player.tuning.walk_stride_mps) if speed > 0.05 else 1.0
			actor.play_clip("walk" if speed > 0.05 else "idle")
		else: actor.drive(speed, 0.05)  # baked locomotion (docs/LOCOMOTION.md): run above enter_mps, strides from the file
		if presenter.simulation_enabled: actor.advance_pose(1.0/60.0)
	for key in presenter.followers:
		var f = presenter.followers[key]
		if not f.get_meta("real_character",false): continue
		var last: Vector3 = previous_followers.get(key,f.position)
		var velocity: Vector3 = f.position-last
		f.face_velocity(velocity)
		if f.locomotion.is_empty(): f.play_clip("walk" if velocity.length() > 0.001 else "idle")
		else: f.drive(velocity.length() * float(Engine.physics_ticks_per_second), 0.06)
		previous_followers[key] = f.position
