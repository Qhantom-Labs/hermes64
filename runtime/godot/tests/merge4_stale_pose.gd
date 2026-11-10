extends SceneTree
## MERGE4: the clip-from-rest fix in actors/character.gd play_clip (charsys 54759ca) on the shipped cast.
## godot --headless --path runtime/godot --script res://tests/merge4_stale_pose.gd -- <job.json> <report.json>
## job = {"characters": [{"id", "glb", "rig", "sha256"}], "probes": [[from, to], ...]}
## For every character and every ordered clip pair it plays `from` to its last key, switches to `to`, and compares
## every bone's pose on every key of `to` with `to` played by a fresh actor (rest + clip):
##   fixed   = the shipped play_clip (skeleton reset to rest first)            -> must match on every key
##   control = the pre-fix play_clip body (no reset), reproduced here verbatim -> stale bones expected
## "No clip regression": for every clip, the shipped path from a fresh actor equals the control path from a fresh
## actor on every key and bone (the reset changes nothing when nothing played before).
const Assets = preload("res://view/assets.gd")
const Actor = preload("res://actors/character.gd")
const KEYS := 16

func _initialize() -> void:
	call_deferred("run")

func pose(s: Skeleton3D) -> Array:
	var out := []
	for i in s.get_bone_count(): out.append(s.get_bone_pose(i))
	return out

func diff_bones(a: Array, b: Array, s: Skeleton3D) -> Array:
	var out := []
	for i in a.size():
		var x: Transform3D = a[i]
		var y: Transform3D = b[i]
		if not x.is_equal_approx(y): out.append(s.get_bone_name(i))
	return out

func old_play_clip(actor, value: String) -> void:
	# actors/character.gd play_clip before the fix, line for line, minus the reset
	if actor.animation == null: return
	if not actor.animation.has_animation(value): value = "idle"
	if value == actor.clip: return
	actor.clip = value
	actor.clock = 0.0
	actor.pose_elapsed = 0.0
	actor.pose_tick = -1
	actor.sample_time = 0.0
	actor.animation.play(actor.clip)
	actor.animation.seek(0.0, true)

func make_actor(world: Node3D, resolver, ch: Dictionary):
	var scene = resolver.load_row({"path": ch.glb, "sha256": ch.sha256})
	if scene == null: return null
	var actor = Actor.new()
	world.add_child(actor)
	actor.manual_clock = true
	actor.configure(scene, {"character_id": ch.id, "source_rig": ch.rig})
	return actor

func keyed_poses(actor, clip: String, use_fix: bool) -> Array:
	# poses at keys 0..15 of `clip`, entered from whatever the actor showed before
	if use_fix: actor.play_clip(clip)
	else: old_play_clip(actor, clip)
	var out := [pose(actor.skeleton)]
	for k in KEYS - 1:
		actor.advance_pose(1.0 / 15.0)
		out.append(pose(actor.skeleton))
	return out

func fresh_poses(world: Node3D, resolver, ch: Dictionary, clip: String, use_fix: bool) -> Array:
	var actor = make_actor(world, resolver, ch)
	actor.clip = ""                                   # configure() played idle; start `clip` from rest
	actor.skeleton.reset_bone_poses()
	var out := keyed_poses(actor, clip, use_fix)
	actor.queue_free()
	return out

func run() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() != 2:
		push_error("usage: -- <job.json> <report.json>")
		quit(2)
		return
	var job: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(args[0]))
	var world := Node3D.new()
	root.add_child(world)
	var resolver = Assets.new()
	resolver.configure({}, {})
	var report := {"characters": [], "checks": 0, "failures": [], "control_stale": 0, "fixed_stale": 0,
		"regression_mismatches": 0}
	for ch in job.characters:
		var probe = make_actor(world, resolver, ch)
		if probe == null:
			report.failures.append("%s: did not load" % ch.id)
			continue
		var clips: Array = Array(probe.animation.get_animation_list())
		var tracks := {}
		for c in clips: tracks[c] = probe.animation.get_animation(c).get_track_count()
		var bones: int = probe.skeleton.get_bone_count()
		probe.queue_free()
		var row := {"id": ch.id, "bones": bones, "clips": clips.size(), "tracks": tracks, "stale_control": {},
			"stale_fixed": {}, "regression": 0}
		var fresh := {}
		for c in clips:
			fresh[c] = fresh_poses(world, resolver, ch, c, true)
			var control_fresh := fresh_poses(world, resolver, ch, c, false)
			for k in KEYS:
				report.checks += 1
				var d := []
				var a: Array = fresh[c][k]
				var b: Array = control_fresh[k]
				for i in a.size():
					var x: Transform3D = a[i]
					var y: Transform3D = b[i]
					if not x.is_equal_approx(y): d.append(i)
				if not d.is_empty():
					row.regression += 1
					report.regression_mismatches += 1
					report.failures.append("%s %s key %d: fresh pose differs between the fixed and pre-fix path" % [ch.id, c, k])
		for pair in job.probes:
			var from: String = pair[0]
			var to: String = pair[1]
			if not (from in clips and to in clips): continue
			for use_fix in [false, true]:
				var actor = make_actor(world, resolver, ch)
				keyed_poses(actor, from, use_fix)
				var got := keyed_poses(actor, to, use_fix)
				var stale := {}
				for k in KEYS:
					report.checks += 1
					for name in diff_bones(got[k], fresh[to][k], actor.skeleton): stale[name] = true
				actor.queue_free()
				var key := "%s->%s" % [from, to]
				if use_fix:
					if not stale.is_empty():
						row.stale_fixed[key] = stale.keys()
						report.fixed_stale += 1
						report.failures.append("%s %s: stale bones with the fix: %s" % [ch.id, key, ", ".join(stale.keys())])
				elif not stale.is_empty():
					row.stale_control[key] = stale.keys()
					report.control_stale += 1
		report.characters.append(row)
	var f := FileAccess.open(args[1], FileAccess.WRITE)
	f.store_string(JSON.stringify(report, " ", true))
	f.close()
	print("MERGE4 STALE POSE characters=%d checks=%d control_stale=%d fixed_stale=%d regression=%d failures=%d" % [
		report.characters.size(), report.checks, report.control_stale, report.fixed_stale, report.regression_mismatches,
		report.failures.size()])
	quit(0 if report.failures.is_empty() else 1)
