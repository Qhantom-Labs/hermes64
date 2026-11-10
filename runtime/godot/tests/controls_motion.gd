extends SceneTree
const Player = preload("res://view/player.gd")
var failures := []
var a
var p
var rows := []
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	a = load("res://input/actions.gd").new()
	# These existing maximum-speed physics ceilings require explicit auto-run.
	check(a.configure({"version":1,"options":{"run_mode":"auto"}}).ok,"motion ceiling checks use auto-run")
	p = Player.new()
	if not p.has_method("motion_tick"):
		check(false,"production motion_tick missing")
		p.free(); a.free(); quit(1); return
	root.add_child(p); p.set_physics_process(false); p.actions = a
	p.bounds = Vector2(100,100); p.position = Vector3(50,0.01,50)
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new(); var box := BoxShape3D.new()
	box.size = Vector3(100,0.2,100); shape.shape = box; body.add_child(shape)
	root.add_child(body); body.position = Vector3(50,-0.1,50)
	await physics_frame
	for cap in [2.4,3.2]:
		p.tuning.run_speed_mps = cap; a.restore({}); p.velocity = Vector3.ZERO
		var at90 := -1; var stop_from := Vector3.ZERO; var stop_at := -1
		for t in 180:
			a.advance({"digital":["move_up"]} if t < 120 else {})
			if t == 120: stop_from = p.position
			p.motion_tick()
			if at90 < 0 and Vector2(p.velocity.x,p.velocity.z).length() >= cap*0.9: at90 = t+1
			if t >= 120 and stop_at < 0 and Vector2(p.velocity.x,p.velocity.z).length() < 0.001: stop_at = t-120+1
			await physics_frame
		check(at90 > 0 and at90 <= 16,"R01 ninety percent reached within 16 ticks cap="+str(cap))
		check(stop_at <= 15,"R01 stop within 15 ticks")
		rows.append({"id":"R01","cap":cap,"ticks90":at90,"stop_ticks":stop_at,"stop_distance_m":p.position.distance_to(stop_from)})
	p.tuning.run_speed_mps = 3.2
	var displacements := []
	for duration in [4,7,12,20]:
		a.restore({}); p.velocity = Vector3.ZERO
		var start: Vector3 = p.position
		for t in 60:
			a.advance({"digital":["move_right"]} if t < duration else {}); p.motion_tick(); await physics_frame
		displacements.append(p.position.distance_to(start))
	check(displacements[0] > 0.02 and displacements[0] < 0.3,"R02 shortest tap displacement")
	check(displacements[0] < displacements[1] and displacements[1] < displacements[2] and displacements[2] < displacements[3],"R02 monotonic taps")
	rows.append({"id":"R02","displacements_m":displacements})
	a.restore({}); p.velocity = Vector3.ZERO
	for t in 180:
		a.advance({"digital":["move_up","walk"] if t < 90 else ["move_up"]}); p.motion_tick(); await physics_frame
		if t == 89: check(Vector2(p.velocity.x,p.velocity.z).length() <= 1.101,"R03 walk speed cap")
		if t == 105: check(Vector2(p.velocity.x,p.velocity.z).length() >= 3.19,"R03 release walk reaches run within ramp")
	var peak := 0.0; var turn := 0.0
	for t in 180:
		var raw := ["move_up","move_right"] if t < 60 else (["move_right"] if t < 120 else ["move_left","move_right"])
		a.advance({"digital":raw}); var yaw: float = p.facing_yaw; p.motion_tick(); await physics_frame
		peak = maxf(peak,Vector2(p.velocity.x,p.velocity.z).length())
		turn = maxf(turn,absf(rad_to_deg(angle_difference(yaw,p.facing_yaw))))
		if t == 60: check(a.get_move().length() > 0.99,"R04 remaining axis no ramp restart")
	check(peak <= 3.201,"R04 no diagonal boost"); check(turn <= 18.001,"R05 turn cap")
	check(p.rotation == Vector3.ZERO,"visual facing never rotates collision capsule")
	rows.append({"id":"R04/R05","peak_speed":peak,"max_turn_deg_tick":turn})
	p.latched = false; p.camera_basis = Basis.IDENTITY; p.direction(Vector2.UP)
	for angle in [PI/2,PI,PI*1.5]:
		p.camera_cut(Basis(Vector3.UP,angle)); check(p.direction(Vector2.UP).distance_to(Vector3.FORWARD)<0.0001,"R06 repeated cut keeps oldest basis")
	p.direction(Vector2.ZERO); check(not p.latched,"R06 neutral releases")
	check(p.direction(Vector2.UP).distance_to(Vector3.RIGHT)<0.0001,"R06 fresh basis")
	a.advance({"digital":["move_up"]}); p.enabled = false; p.motion_tick()
	check(p.velocity == Vector3.ZERO,"M09 modal stops immediately")
	print("CONTROLS MOTION ",JSON.stringify({"failures":failures,"measurements":rows}))
	p.queue_free(); body.queue_free(); a.free(); await process_frame
	quit(0 if failures.is_empty() else 1)
