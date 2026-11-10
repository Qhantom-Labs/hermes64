extends SceneTree
const Character = preload("res://actors/character.gd")
var failures := []
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func run() -> void:
	var actor=Character.new(); root.add_child(actor)
	actor.animation=AnimationPlayer.new(); actor.add_child(actor.animation)
	var library:=AnimationLibrary.new()
	for name in ["walk","idle"]:
		var clip:=Animation.new(); clip.length=4.0; library.add_animation(name,clip)
	actor.animation.add_animation_library("",library)
	actor.manual_clock=true; actor.play_clip("walk")
	for speed in [0.5,1.0,2.0]:
		actor.clock=0.0; actor.pose_speed=speed
		var changes:=0
		for tick in 60:
			var old: float=actor.sample_time
			actor.advance_pose(1.0/60.0)
			if actor.sample_time!=old: changes+=1
			check(is_equal_approx(actor.sample_time*15,roundf(actor.sample_time*15)),"15 fps held poses")
		check(absf(actor.clock-speed)<0.0001,"pose rate matches velocity ratio")
		check(changes<=16,"fast playback still holds at fifteen visual updates per second")
		var before: float = actor.clock
		actor._process(10.0)
		check(actor.clock==before,"manual physics pose clock independent of render delta")
	check(actor.position==Vector3.ZERO,"animation cannot move physical root")
	actor.free(); await process_frame
	print("CONTROLS ANIMATION failures=",JSON.stringify(failures))
	quit(0 if failures.is_empty() else 1)
