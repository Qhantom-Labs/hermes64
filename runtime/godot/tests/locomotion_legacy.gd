extends SceneTree
## Base locomotion (docs/LOCOMOTION.md) is opt-in by file content. This proves both halves in real Godot (headless):
##   a file WITHOUT the hermes64_locomotion block plays tick for tick, bone for bone, as it did before the base
##   existed (control = the pre-base play_clip / advance_pose / bridge lines, reproduced here verbatim);
##   a file WITH the block takes the new path (run clip above run.enter_mps, every key of both cycles shown; at
##   continuous phase the key is the phase rounded to the nearest key).
## godot --headless --path runtime/godot --script res://tests/locomotion_legacy.gd -- <job.json> <report.json>
## job = {"characters": [{"id", "glb", "rig"}], "walk_stride_mps": 1.1, "speeds": [[seconds, m/s], ...]}
const Assets = preload("res://actors/assets.gd")
const Actor = preload("res://actors/character.gd")
const DT := 1.0 / 60.0

func _initialize() -> void:
	call_deferred("run")

func pose(s: Skeleton3D) -> Array:
	var out := []
	for i in s.get_bone_count(): out.append(s.get_bone_pose(i))
	return out

## actors/character.gd play_clip as it was before the base (commit b34ed130), on the actor's own fields.
func old_play_clip(a, value: String) -> void:
	if a.animation == null: return
	if not a.animation.has_animation(value): value = "idle"
	if value == a.clip: return
	a.clip = value
	a.clock = 0.0
	a.pose_elapsed = 0.0
	a.pose_tick = -1
	a.sample_time = 0.0
	if a.skeleton != null: a.skeleton.reset_bone_poses()
	a.animation.play(a.clip)
	a.animation.seek(0.0, true)

## actors/character.gd advance_pose as it was before the base (the face lines do not touch the skeleton).
func old_advance_pose(a, delta: float) -> void:
	if a.animation == null or a.clip == "": return
	a.clock += delta * a.pose_speed
	a.pose_elapsed += delta
	var next_tick := floori((a.pose_elapsed + 0.000001) * a.pose_fps)
	if next_tick == a.pose_tick: return
	a.pose_tick = next_tick
	var length: float = a.animation.get_animation(a.clip).length
	var held: float = floorf((a.clock + 0.000001) * a.pose_fps) / a.pose_fps
	a.sample_time = fmod(held, length) if length > 0.0 else 0.0
	a.animation.seek(a.sample_time, true)

func make(resolver, ch: Dictionary, with_block: bool):
	var model = resolver.instance_glb(ch.glb)
	if model == null: return null
	var actor = Actor.new()
	root.add_child(actor)
	actor.manual_clock = true
	actor.configure(model, {"character_id": ch.id, "source_rig": ch.rig})
	if with_block: actor.set_locomotion(resolver.locomotion_block(ch.glb))
	return actor

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
		var shipped = make(resolver, ch, true)       # the shipped path: block (if any) from the file
		var control = make(resolver, ch, false)      # never opted in, driven by the pre-base code above
		var row := {"id": ch.id, "loaded": shipped != null and control != null}
		report.characters.append(row)
		if not row.loaded:
			report.failures.append(ch.id + ": not loaded")
			continue
		row.baked = not shipped.locomotion.is_empty()
		row.clip_lengths = {}
		for name in ["walk", "run", "idle"]:
			if shipped.animation.has_animation(name): row.clip_lengths[name] = [shipped.animation.get_animation(name).length, control.animation.get_animation(name).length]
		var ticks := 0
		var mismatched_ticks := 0
		var mismatched_bones := {}
		var clips := {}
		var keys := {}
		var switches := []
		for seg in job.speeds:
			for i in int(round(float(seg[0]) / DT)):
				var speed := float(seg[1])
				# actors/bridge.gd, the lines that drive the player's character
				if shipped.locomotion.is_empty():
					shipped.pose_speed = speed / float(job.walk_stride_mps) if speed > 0.05 else 1.0
					shipped.play_clip("walk" if speed > 0.05 else "idle")
				else: shipped.drive(speed, 0.05)
				var before: String = shipped.clip
				shipped.advance_pose(DT)
				if shipped.clip != before: switches.append([before, shipped.clip, speed, ticks])
				# the same lines as they were before the base
				control.pose_speed = speed / float(job.walk_stride_mps) if speed > 0.05 else 1.0
				old_play_clip(control, "walk" if speed > 0.05 else "idle")
				old_advance_pose(control, DT)
				ticks += 1
				clips[shipped.clip] = int(clips.get(shipped.clip, 0)) + 1
				if not shipped.locomotion.is_empty() and shipped.cycle_clip(shipped.clip):
					if not keys.has(shipped.clip): keys[shipped.clip] = {}
					keys[shipped.clip][posmod(int(round(shipped.sample_time * float(shipped.locomotion.fps))), int(shipped.locomotion.cycle_keys))] = true
				var a := pose(shipped.skeleton)
				var b := pose(control.skeleton)
				var bad := false
				for j in a.size():
					var x: Transform3D = a[j]
					var y: Transform3D = b[j]
					if not x.is_equal_approx(y):
						bad = true
						mismatched_bones[shipped.skeleton.get_bone_name(j)] = true
				if bad or shipped.clip != control.clip or not is_equal_approx(shipped.sample_time, control.sample_time): mismatched_ticks += 1
		row.ticks = ticks
		row.mismatched_ticks = mismatched_ticks
		row.mismatched_bones = mismatched_bones.keys()
		row.clips = clips
		row.keys_shown = {}
		for c in keys: row.keys_shown[c] = keys[c].keys()
		row.switches = switches
		shipped.queue_free()
		control.queue_free()
	var f := FileAccess.open(args[1], FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " "))
	f.close()
	quit(0 if report.failures.is_empty() else 1)
