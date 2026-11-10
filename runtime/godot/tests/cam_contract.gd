extends SceneTree
var view
var checks := 0
var failures := []
func _initialize() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	checks+=1
	if not ok: failures.append(message); print("FAIL ",message)
func run() -> void:
	view=load("res://main.tscn").instantiate();root.add_child(view)
	for i in 12: await physics_frame
	await process_frame
	var follow=view.follow_camera
	if not follow.has_method("present"):
		expect(false,"render interpolation API is required")
	else:
		for node in [view,view.player,view.actions,view.module_host,follow]:
			if node!=null: node.set_physics_process(false)
		follow.set_process(false)
		if view.module_host!=null and view.module_host.puzzle!=null and view.module_host.puzzle.active:
			follow.reset_presentation=true
			view.transition_action="move:"+str(view.runtime.state.location)+":cam_probe"
			view.transition_entry()
			expect(not follow.reset_presentation,"puzzle arrival is sampled before the room is revealed")
			view.transition_action=""
		var canonical: String=view.replay.digest(view.replay.state())
		var basis: Basis=view.player.camera_basis
		for i in 120:
			follow._physics_process(1.0/60.0)
			follow.present(1.0/144.0,float(i%12)/12.0)
		expect(canonical==view.replay.digest(view.replay.state()),"presentation ticks/render interpolation preserve exact canonical digest")
		expect(basis==view.player.camera_basis,"render camera never replaces authored locomotion basis")
		expect(view.viewport.get_camera_3d()==follow.render_camera,"one render camera owns the displayed frame")
		if view.module_host!=null:
			expect(view.module_host.combat_camera.current()==follow.render_camera,"combat HUD projects through the actual drawing camera")
		var visual=view.player.get_node_or_null("visual")
		var centre: Vector3=follow.centre
		if visual!=null: visual.position.y+=2.0
		follow._physics_process(1.0/60.0)
		expect(follow.centre.distance_to(centre)<0.01,"animated visual/head bob is excluded from stabilized aim")
		follow.yaw=wrapf(follow.yaw+0.8,-PI,PI); follow.wanted_yaw=follow.yaw
		var before: float=follow.yaw
		follow.reset()
		expect(absf(angle_difference(before,follow.yaw))<0.0001,"same-room rebuild does not pull yaw to authored entry")
		var old=load("res://tests/cam_old.gd").new();view.add_child(old);old.attach(view);old.set_physics_process(false)
		old.yaw=wrapf(old.yaw+0.8,-PI,PI)
		var old_before: float=old.yaw
		old.reset()
		expect(absf(angle_difference(old_before,old.yaw))>0.79,"known-bad old same-room reset discards the 0.8rad orbit offset")
		old.free()
		var smooth=load("res://view/camera_smoothing.gd")
		var slow: Vector2=smooth.scalar(0.0,0.0,1.0,12.0,0.15)
		var quick: Vector2=smooth.scalar(0.0,0.0,1.0,22.0,0.15)
		expect(quick.x>slow.x and quick.x<1.0,"reduced motion has shorter easing, not an instantaneous cut")
		var a: Array=smooth.spring(Vector3.ZERO,Vector3.ZERO,Vector3.ONE,12.0,0.1)
		var b: Array=smooth.spring(a[0],a[1],Vector3.ONE,12.0,0.1)
		var full: Array=smooth.spring(Vector3.ZERO,Vector3.ZERO,Vector3.ONE,12.0,0.2)
		expect((b[0] as Vector3).distance_to(full[0])<0.00001,"analytic critical spring is timestep composable for a constant target")
	print("CAM_CONTRACT ",JSON.stringify({"checks":checks,"failures":failures}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
