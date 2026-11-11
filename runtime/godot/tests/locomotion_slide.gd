extends SceneTree
## Planted-boot slide of the baked cycles in play, headless (tests/test_locomotion.py ContinuousPhase). The shipped
## actors/character.gd drives the clips (drive + advance_pose at 60 ticks/s) while the character travels along +z;
## the sole points of both boots are read from the skeleton every tick. Known-bad controls per character row:
## "stepped": true plays the stepped path (a key held for whole ticks); "stride_scale" multiplies the strides of the
## block before the actor reads it (a wrong stride length). Each play also gets a digest of every tick's numbers.
## godot --headless --path runtime/godot --script res://tests/locomotion_slide.gd -- <job.json> <report.json>
## job = {"characters": [{"id", "glb", "rig", "sole": {"l": [[x,y,z]..], "r": [..]}, "stepped", "stride_scale", "plays"?}],
##        "plays": [{"name", "start_mps", "segments": [{"mps", "seconds", "accel"?, "brake"?}]}], "accel_mps2", "brake_mps2"}
## (a character's own "plays" replace the job's)
const Assets = preload("res://actors/assets.gd")
const Actor = preload("res://actors/character.gd")
const DT := 1.0 / 60.0

func _initialize() -> void:
	call_deferred("run")

func sole_points(actor, sole: Dictionary) -> Dictionary:
	var out := {}
	for side in ["l", "r"]:
		var t: Transform3D = actor.skeleton.global_transform * actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone("foot_" + side))
		var rows := []
		for q in sole[side]:
			var p: Vector3 = t * Vector3(q[0], q[1], q[2])
			rows.append([p.x, p.y, p.z])
		out[side] = rows
	return out

func pose_of(actor) -> Array:
	var out := []
	for name in ["foot_l", "foot_r", "thigh_l", "upper_arm_l"]:
		var t: Transform3D = actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone(name))
		for v in [t.origin, t.basis.x, t.basis.y]: out.append_array([snappedf(v.x, 0.00001), snappedf(v.y, 0.00001), snappedf(v.z, 0.00001)])
	return out

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("usage: -- <job.json> <report.json>")
		quit(2)
		return
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var resolver = Assets.new()
	resolver.configure({}, {})
	var report := {"engine": Engine.get_version_info().string, "characters": [], "failures": []}
	for ch in job.characters:
		var model = resolver.instance_glb(ch.glb)
		if model == null:
			report.failures.append(str(ch.id) + ": not loaded")
			continue
		var actor = Actor.new()
		root.add_child(actor)
		actor.manual_clock = true
		actor.configure(model, {"character_id": ch.id, "source_rig": ch.get("rig", "human16_v1")})
		var block: Dictionary = resolver.locomotion_block(ch.glb).duplicate(true)
		var k := float(ch.get("stride_scale", 1.0))
		if k != 1.0 and not block.is_empty():
			for c in ["walk", "run"]:
				if block.has(c): block[c].stride_mps = float(block[c].stride_mps) * k
		actor.set_locomotion(block)
		if ch.get("stepped", false): actor.loco = {}
		var row := {"id": ch.id, "baked": not actor.locomotion.is_empty(), "continuous": not actor.loco.is_empty(), "plays": []}
		if row.continuous: row.tables = {"windows": actor.loco.windows, "start": actor.loco.start, "planted": actor.loco.planted}
		for play in ch.get("plays", job.get("plays", [])):
			actor.position = Vector3.ZERO
			actor.clip = ""
			actor.play_clip("idle")
			var speed := float(play.get("start_mps", 0.0))
			var ticks := []
			var digest := ""
			for seg in play.segments:
				var accel := float(seg.get("accel", job.accel_mps2))
				var brake := float(seg.get("brake", job.brake_mps2))
				for i in int(round(float(seg.seconds) / DT)):
					var target := float(seg.mps)
					speed = minf(target, speed + accel * DT) if target > speed else maxf(target, speed - brake * DT)
					actor.position.z += speed * DT
					if actor.locomotion.is_empty():
						actor.pose_speed = speed / float(job.get("walk_stride_mps", 1.1)) if speed > 0.05 else 1.0
						actor.play_clip("walk" if speed > 0.05 else "idle")
					else: actor.drive(speed, 0.05)
					actor.advance_pose(DT)
					var rec := {"mps": speed, "z": actor.position.z, "clip": actor.clip, "key": roundi(actor.sample_time * 15.0), "pose": pose_of(actor), "sole": sole_points(actor, ch.sole)}
					digest = (digest + JSON.stringify(rec)).sha256_text()
					ticks.append(rec)
			row.plays.append({"name": play.name, "ticks": ticks, "digest": digest})
		if row.continuous:
			# a module's held pose (modules/animation_state.gd pose_placeholder): animation stopped, clip cleared, bones set
			# by hand while the cycles were playing; the next tick must leave that pose alone and end the cycles
			actor.play_clip("idle")
			for i in 30:
				actor.drive(3.2, 0.05)
				actor.advance_pose(DT)
			var was_on: bool = actor.loco_on
			actor.animation.stop()
			actor.clip = ""
			actor.skeleton.reset_bone_poses()
			var spine: int = actor.skeleton.find_bone("spine")
			var held := Quaternion.from_euler(Vector3(1.0, 0.0, 0.0))
			actor.skeleton.set_bone_pose_rotation(spine, held)
			actor.advance_pose(DT)
			row.held_pose = {"cycles_were_on": was_on, "cycles_on_after": actor.loco_on,
				"kept": actor.skeleton.get_bone_pose_rotation(spine).is_equal_approx(held)}
		report.characters.append(row)
		actor.queue_free()
	var f := FileAccess.open(args[1], FileAccess.WRITE)
	f.store_string(JSON.stringify(report))
	f.close()
	quit(0 if report.failures.is_empty() else 1)
