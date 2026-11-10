extends SceneTree
## Real InputMap/mouse events; camera presentation must not enter canonical state.
var view
var failures := []
var checks := 0
func _initialize() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	checks += 1
	if not ok: failures.append(message); print("FAIL ",message)
func ticks(n: int) -> void:
	for i in n: await physics_frame
	await process_frame
func mouse_button(code: int, down: bool) -> void:
	var event := InputEventMouseButton.new()
	event.button_index=code; event.pressed=down; event.position=Vector2(400,300)
	Input.parse_input_event(event)
func drag(amount: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position=Vector2(400,300); event.relative=amount; event.button_mask=MOUSE_BUTTON_MASK_LEFT
	Input.parse_input_event(event)
func key(code: int, down: bool) -> void:
	var event := InputEventKey.new()
	event.physical_keycode=code; event.keycode=code; event.pressed=down
	Input.parse_input_event(event)
func run() -> void:
	view=load("res://main.tscn").instantiate(); root.add_child(view)
	await ticks(12)
	view.actions.configure({"version":1}); view.actions.restore({})
	view.set_physics_process(false); view.player.set_physics_process(false)
	view.actions.set_physics_process(false)
	if view.module_host != null: view.module_host.set_physics_process(false)
	var follow=view.follow_camera
	follow.set_physics_process(false)
	follow._physics_process(1.0/60.0)
	var before: Transform3D=follow.cam.global_transform
	var basis: Basis=view.player.camera_basis
	var canonical: String=view.replay.digest(view.replay.state())
	mouse_button(MOUSE_BUTTON_LEFT,true); drag(Vector2(180,-50)); await process_frame
	for i in 12: follow._physics_process(1.0/60.0)
	expect(not before.basis.is_equal_approx(follow.cam.global_basis),"held left mouse drag orbits the real follow camera")
	expect(view.player.camera_basis.is_equal_approx(basis),"mouse orbit never changes authored locomotion basis")
	expect(canonical==view.replay.digest(view.replay.state()),"mouse orbit never changes canonical movie state")
	mouse_button(MOUSE_BUTTON_LEFT,false); await process_frame
	var released: Transform3D=follow.cam.global_transform
	drag(Vector2(180,100)); await process_frame
	follow._physics_process(1.0/60.0)
	expect(released.basis.get_euler().distance_to(follow.cam.global_basis.get_euler())<0.2,"unheld mouse motion does not orbit")
	view.actions.last_frame={"digital":["camera_left"]}
	before=follow.cam.global_transform
	for i in 20: follow._physics_process(1.0/60.0)
	expect(not before.basis.is_equal_approx(follow.cam.global_basis),"existing J camera-left action now orbits without C chord")
	view.actions.last_frame={"digital":["camera_down"]}
	before=follow.cam.global_transform
	for i in 12: follow._physics_process(1.0/60.0)
	expect(not before.basis.is_equal_approx(follow.cam.global_basis),"existing K camera-down action now pitches")
	view.actions.last_frame={}
	mouse_button(MOUSE_BUTTON_LEFT,true); drag(Vector2(10000,-10000)); await process_frame
	for i in 30: follow._physics_process(1.0/60.0)
	mouse_button(MOUSE_BUTTON_LEFT,false); await process_frame
	expect(follow.cam.position.is_finite(),"large drag remains finite")
	if follow.last.has("pitch"):
		expect(float(follow.last.pitch)>=0.15 and float(follow.last.pitch)<=1.05,"orbit pitch stays clamped")
	else: expect(false,"orbit exposes bounded pitch observation")
	for i in 100: mouse_button(MOUSE_BUTTON_WHEEL_DOWN,true)
	await process_frame
	for i in 20: follow._physics_process(1.0/60.0)
	expect(follow.cam.position.distance_to(view.player.position+Vector3.UP*0.8)<6.2,"camera distance is clamped")
	view.player.set_facing_yaw(0.6)
	key(KEY_V,true); view.actions.advance(view.actions.sample_live()); key(KEY_V,false)
	# CAM caps yaw at 65 degrees/s: a near-180 return cannot legally finish in
	# the old 2s assertion window. Four seconds includes bounded acceleration.
	for i in 240: follow._physics_process(1.0/60.0)
	var flat: Vector3=follow.cam.position-(view.player.position+Vector3.UP*0.8); flat.y=0
	expect(absf(angle_difference(atan2(flat.x,flat.z),0.6))<0.06,"V recenters behind player facing")
	view.actions.last_frame={}
	mouse_button(MOUSE_BUTTON_LEFT,true); drag(Vector2(150,0)); await process_frame
	for i in 10: follow._physics_process(1.0/60.0)
	mouse_button(MOUSE_BUTTON_LEFT,false); await process_frame
	for i in 240: follow._physics_process(1.0/60.0)
	flat=follow.cam.position-(view.player.position+Vector3.UP*0.8); flat.y=0
	expect(absf(angle_difference(atan2(flat.x,flat.z),0.6))<0.06,"idle delay smoothly returns camera behind player")
	view.actions.configure({"version":1,"options":{"reduced_motion":true}})
	follow._physics_process(1.0/60.0)
	expect(float(follow.last.lag)<0.001,"reduced motion removes positional follow lag")
	var blocker:=StaticBody3D.new()
	var shape:=CollisionShape3D.new(); var sphere:=SphereShape3D.new(); sphere.radius=0.5; shape.shape=sphere
	blocker.add_child(shape); view.world.add_child(blocker)
	blocker.position=(view.player.position+Vector3.UP*0.8).lerp(follow.cam.position,0.15)
	await ticks(2)
	follow._physics_process(1.0/60.0)
	expect(follow.cam.position.distance_to(view.player.position+Vector3.UP*0.8)>1.5,"near obstacle cannot pull camera inside player torso")
	blocker.queue_free(); await ticks(2)
	var untouched: String=view.replay.digest(view.replay.state())
	view.actions.source="replay"
	mouse_button(MOUSE_BUTTON_LEFT,true); drag(Vector2(-180,0)); await process_frame
	follow._physics_process(1.0/60.0)
	mouse_button(MOUSE_BUTTON_LEFT,false)
	expect(untouched==view.replay.digest(view.replay.state()),"strict replay ignores physical mouse input without canonical mutation")
	print("FEEL2_ORBIT ",JSON.stringify({"checks":checks,"failures":failures,"last":follow.last}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
