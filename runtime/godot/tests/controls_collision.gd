extends SceneTree
const Player = preload("res://view/player.gd")
var p
var a
var failures := []
var measurements := []
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func box(at: Vector3, size: Vector3, angle := 0.0) -> StaticBody3D:
	var body := StaticBody3D.new(); var shape := CollisionShape3D.new(); var mesh := BoxShape3D.new()
	mesh.size = size; shape.shape = mesh; body.add_child(shape); root.add_child(body)
	body.position = at; body.rotation.z = angle
	return body
func reset_player(at: Vector3) -> void:
	if p != null: p.free()
	p = Player.new(); p.actions = a; root.add_child(p); p.set_physics_process(false)
	p.bounds = Vector2(100,100); p.position = at; a.restore({})
func step(digital := []) -> void:
	a.advance({"digital":digital}); p.motion_tick(); await physics_frame
func run() -> void:
	a = load("res://input/actions.gd").new()
	# Keep the pre-FEEL2 full-speed wall/step/slope stress, not only slower jog.
	check(a.configure({"version":1,"options":{"run_mode":"auto"}}).ok,"collision stress uses auto-run")
	var floor_body := box(Vector3(50,-0.1,50),Vector3(100,0.2,100))
	# Straight wall + perpendicular wall (corner); solver push-out is not replaced.
	var wall := box(Vector3(52,1,50),Vector3(0.2,2,10))
	var corner := box(Vector3(50,1,52),Vector3(10,2,0.2))
	reset_player(Vector3(50,0.01,50)); await physics_frame
	for t in 180: await step(["move_right","move_down"])
	check(p.position.x<51.75 and p.position.z<51.75,"M07 corner no tunneling")
	check(Vector2(p.actual_velocity.x,p.actual_velocity.z).length()<0.02,"M07 blocked actor not walking in place")
	for t in 60: await step(["move_left","move_up"])
	check(p.position.x<51.0 and p.position.z<51.0,"M07 corner escape no snag")
	wall.free(); corner.free()
	for height in [0.12,0.18,0.30]:
		var stair := box(Vector3(52,height/2,50),Vector3(2,height,5))
		reset_player(Vector3(50,0.01,50)); await physics_frame
		var max_y := 0.0
		for t in 100:
			await step(["move_right"]); max_y=maxf(max_y,p.position.y)
		if height <= 0.18 and p.position.x < 51.6:
			var motion := Vector3(0.053,0,0)
			var lifted: Transform3D = p.global_transform.translated(Vector3.UP*0.18)
			var contact := KinematicCollision3D.new()
			var land: bool = p.test_move(lifted.translated(motion),Vector3.DOWN*0.33,contact)
			print("STEP DIAGNOSTIC ",height," floor=",p.is_on_floor()," ahead=",p.test_move(p.global_transform,motion)," up=",p.test_move(p.global_transform,Vector3.UP*0.18)," raised=",p.test_move(lifted,motion)," land=",land," normal=",contact.get_normal() if land else Vector3.ZERO," travel=",contact.get_travel() if land else Vector3.ZERO)
		check(p.position.x>51.6 if height<=0.18 else p.position.x<51.0,"M07 step height " + str(height))
		measurements.append({"step":height,"x":p.position.x,"max_y":max_y})
		stair.free()
	for degrees in [25,39,50]:
		var angle := deg_to_rad(float(degrees))
		var ramp := box(Vector3(53,sin(angle)*3-0.1,50),Vector3(6,0.2,4),angle)
		reset_player(Vector3(49.5,0.01,50)); await physics_frame
		var peak := 0.0
		for t in 150:
			await step(["move_right"]); peak=maxf(peak,p.position.y)
		check(peak>0.5 if degrees<40 else peak<0.5,"M07 slope ceiling " + str(degrees))
		for t in 150: await step(["move_left"])
		check(p.position.y<0.05,"M07 slope descent grounds " + str(degrees))
		measurements.append({"slope_deg":degrees,"peak_y":peak,"end_y":p.position.y})
		ramp.free()
	# Simulated keyboard ghosting records what arrived, never sticks after release.
	for chord in [["move_up","move_right","walk","primary"],["move_up","move_left","walk","dodge"],["move_up","walk","dodge"]]:
		for t in 10: await step(chord)
	for t in 20: await step()
	check(a.get_move()==Vector2.ZERO and not a.is_pressed("primary") and not a.is_pressed("dodge"),"R09 ghosting tolerant release")
	check(Vector2(p.velocity.x,p.velocity.z).length()<0.001,"R09 no stuck velocity")
	print("CONTROLS COLLISION ",JSON.stringify({"failures":failures,"measurements":measurements}))
	p.free(); a.free(); floor_body.free(); await process_frame
	quit(0 if failures.is_empty() else 1)
