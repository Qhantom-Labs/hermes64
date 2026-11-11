extends SceneTree
## COMBATFIX (tests/test_combatfix.py Hold): a baked body walking while a module holds a stance key (actor.hold).
## The shipped actors/character.gd drives the cycle (drive + advance_pose at 60 ticks/s) while the body travels along +z.
## Per play: the upper arm's local rotation per tick (held: constant, from the held key), the planted-boot slide (sole
## points within 12 mm of the lowest sole height at both ticks of a pair), and the clip after a stop.
## godot --headless --path runtime/godot --script res://tests/combatfix_hold.gd -- <body.glb> <report.json>
const Assets = preload("res://actors/assets.gd")
const Actor = preload("res://actors/character.gd")
const DT := 1.0 / 60.0

func _initialize() -> void:
	call_deferred("run")

func soles(actor) -> Array:
	var out := []
	for s in ["l", "r"]:
		var t: Transform3D = actor.skeleton.global_transform * actor.skeleton.get_bone_global_pose(actor.skeleton.find_bone("foot_" + s))
		var sole: Dictionary = actor.locomotion.sole[s]
		out.append([t * Vector3(sole.toe[0], sole.toe[1], sole.toe[2]), t * Vector3(sole.heel[0], sole.heel[1], sole.heel[2])])
	return out

func play(actor, hold: Dictionary, back: bool, mps: float) -> Dictionary:
	actor.position = Vector3.ZERO
	actor.hold = {}
	actor.clip = ""
	actor.play_clip("idle")
	actor.hold = hold
	var arm: int = actor.skeleton.find_bone("upper_arm_l")
	var rots := []
	var feet := []
	for i in 120:
		actor.drive(mps, 0.05, back)
		actor.advance_pose(DT)
		actor.position.z += (-mps if back else mps) * DT
		if i >= 30:
			rots.append(actor.skeleton.get_bone_pose_rotation(arm))
			feet.append(soles(actor))
	var spread := 0.0
	for q in rots: spread = maxf(spread, rad_to_deg(rots[0].angle_to(q)))
	var lo := INF
	for f in feet:
		for side in f:
			for p in side: lo = minf(lo, p.y)
	var slides := []
	for i in range(1, feet.size()):
		for s in 2:
			var d := []
			for j in 2:
				var a: Vector3 = feet[i - 1][s][j]
				var b: Vector3 = feet[i][s][j]
				if a.y - lo < 0.012 and b.y - lo < 0.012: d.append(Vector2(b.x - a.x, b.z - a.z).length() / DT)
			if not d.is_empty():
				var m := 0.0
				for x in d: m += x
				slides.append(m / d.size())
	slides.sort()
	var stop_ticks := 0
	while actor.loco_on and stop_ticks < 120:
		actor.drive(0.0, 0.05, back)
		actor.advance_pose(DT)
		stop_ticks += 1
	var held_rot = null
	if not hold.is_empty(): held_rot = actor.loco_held()[1][arm]
	var last: Quaternion = rots[-1]
	return {"arm_rot": [last.x, last.y, last.z, last.w], "arm_spread_deg": spread, "arm_vs_held_deg": rad_to_deg(rots[-1].angle_to(held_rot)) if held_rot != null else -1.0,
		"pairs": slides.size(), "slide_p50": slides[slides.size() / 2] if not slides.is_empty() else -1.0,
		"slide_max": slides[-1] if not slides.is_empty() else -1.0, "stop_ticks": stop_ticks, "clip_after_stop": str(actor.clip),
		"loco_on_after_stop": actor.loco_on}

func run() -> void:
	var args := OS.get_cmdline_user_args()
	var resolver = Assets.new()
	resolver.configure({}, {})
	var model = resolver.instance_glb(args[0])
	var actor = Actor.new()
	root.add_child(actor)
	actor.manual_clock = true
	actor.configure(model, {"character_id": "probe", "source_rig": "human16_v1"})
	actor.set_locomotion(resolver.locomotion_block(args[0]))
	var report := {"engine": Engine.get_version_info().string, "continuous": not actor.loco.is_empty()}
	if actor.loco.is_empty():
		report["error"] = "no locomotion tables"
	else:
		report["free"] = play(actor, {}, false, 1.2)
		report["held"] = play(actor, {"clip": "idle_combat", "key": 3}, false, 1.2)
		report["held_run"] = play(actor, {"clip": "idle_combat", "key": 3}, false, 3.2)
		report["held_control_swing"] = play(actor, {"clip": "swing", "key": 4}, false, 1.2)
		report["held_back"] = play(actor, {"clip": "idle_combat", "key": 3}, true, 1.0)
	var f := FileAccess.open(args[1], FileAccess.WRITE)
	f.store_string(JSON.stringify(report))
	f.close()
	quit(0)
