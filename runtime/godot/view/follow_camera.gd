extends Node
## Presentation-only fixed-tick targets + interpolated, spring-smoothed render rig.
## Authored cameras alone supply the unchanged locomotion basis/replay hashes.
const Smooth = preload("res://view/camera_smoothing.gd")
var render_camera: Camera3D
var centre_velocity := Vector3.ZERO
var yaw_velocity := 0.0
var pitch_velocity := 0.0
var distance_velocity := 0.0
var eye_velocity := Vector3.ZERO
var sample_velocity := Vector3.ZERO
var rotation_velocity := Vector3.ZERO
var fov_velocity := 0.0
var previous_pose := Transform3D.IDENTITY
var previous_aim := Vector3.ZERO
var next_aim := Vector3.ZERO
var render_aim := Vector3.ZERO
var aim_velocity := Vector3.ZERO
var next_pose := Transform3D.IDENTITY
var previous_fov := 55.0
var next_fov := 55.0
var presentation_ready := false
var reset_presentation := true
var recentering := false
var orbit_override := false
var render_last := {}
var trace_enabled := false
var render_seconds := 0.0
var presentation_rate := 1.0
var presentation_rate_velocity := 0.0
var view
var cam: Camera3D
var enabled := true
var anchor_steps := 0
var centre := Vector3.ZERO
var ready_centre := false
var last := {}
# Orbit is presentation ONLY: the authored camera still owns player.camera_basis.
# Mouse deltas never enter Actions/movie state; recorded key/pad camera frames
# may be displayed on playback, but can never steer the simulation.
const DEFAULT_PITCH := 0.5070985
const DEFAULT_DISTANCE := 5.147815
const IDLE_TICKS := 90
var yaw := 0.0
var pitch := DEFAULT_PITCH
var distance := DEFAULT_DISTANCE
var wanted_yaw := 0.0
var wanted_pitch := DEFAULT_PITCH
var wanted_distance := DEFAULT_DISTANCE
var idle_ticks := 0
var dragging := false
var mouse_delta := Vector2.ZERO
# MOVE: input/camera relationship. The camera is never faster than the player
# turns (65 deg/s yaw cap vs 720 deg/s turn) and never drifts past the latch.
const FOLLOW_MIN_FORWARD := 0.25
const MAX_HEADING_DRIFT := deg_to_rad(40.0)
var recenter_target := 0.0
var was_recentering := false
var was_recenter_key := false
var heading_orbit := false
var heading_yaw := 0.0
var heading_ready := false

## Recorded per live frame: yaw of the FIXED-TICK view source (never the
## interpolated render camera) and whether a deliberate orbit is in progress.
func heading() -> Variant:
	if view == null or view.room_root == null or not heading_ready: return null
	return [snappedf(heading_yaw,0.000001),1 if heading_orbit else 0]

func _input(event: InputEvent) -> void:
	if view == null or view.actions.source != "live" or view.actions.context != "gameplay" or not available():
		dragging = false; mouse_delta = Vector2.ZERO
		return
	if event is InputEventMouseButton:
		if event.button_index == MOUSE_BUTTON_LEFT: dragging = event.pressed
		elif event.pressed and event.button_index in [MOUSE_BUTTON_WHEEL_UP,MOUSE_BUTTON_WHEEL_DOWN]:
			wanted_distance = clampf(wanted_distance + (0.35 if event.button_index == MOUSE_BUTTON_WHEEL_DOWN else -0.35),2.0,6.0)
			idle_ticks = 0
	elif event is InputEventMouseMotion and dragging:
		mouse_delta += event.relative.limit_length(2048.0)

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		dragging = false; mouse_delta = Vector2.ZERO

func orbit_tick(reduced: bool, dt := 1.0/60.0) -> void:
	var frame: Dictionary = view.actions.last_frame
	var raw: Array = frame.get("digital",[]).duplicate()
	raw.append_array(frame.get("buttons",[]))
	var orbit: Vector2 = view.actions.vector(frame.get("camera",[0,0]))
	orbit += Vector2(float("camera_right" in raw)-float("camera_left" in raw),float("camera_down" in raw)-float("camera_up" in raw))
	orbit = orbit.limit_length()
	if orbit.length()<0.15: orbit=Vector2.ZERO
	var manual: bool = orbit != Vector2.ZERO or mouse_delta != Vector2.ZERO or dragging
	if view.actions.context != "gameplay":
		manual=false; orbit=Vector2.ZERO; mouse_delta=Vector2.ZERO; dragging=false
	if manual:
		wanted_yaw = wrapf(wanted_yaw-orbit.x*1.65*dt-mouse_delta.x*0.006,-PI,PI)
		wanted_pitch = clampf(wanted_pitch+orbit.y*1.32*dt+mouse_delta.y*0.004,0.15,1.05)
		idle_ticks=0; recentering=false; orbit_override=true
	else:
		idle_ticks += 1
		if orbit_override and idle_ticks>IDLE_TICKS: orbit_override=false; recentering=true
	mouse_delta=Vector2.ZERO
	if recentering and not was_recentering: recenter_target=view.player.facing_yaw
	if "camera_recenter" in raw:
		recentering=true; orbit_override=false; idle_ticks=IDLE_TICKS+1
		# MOVE: the target is fixed at the press. Re-reading facing every tick
		# chases a player who (correctly) keeps re-latching S toward the lens.
		if not was_recenter_key: recenter_target=view.player.facing_yaw
	was_recenter_key="camera_recenter" in raw
	# Manual orbit has sole yaw authority until its quiet return. Ordinary follow
	# trails actual horizontal travel, NOT the fast animation/facing reversal.
	var velocity: Vector3=view.player.actual_velocity; velocity.y=0.0
	if not manual and not orbit_override:
		if recentering: wanted_yaw=recenter_target
		elif velocity.length()>0.18:
			# MOVE: swing behind travel only while it heads AWAY from the lens.
			# Backward/lateral travel previously spun the view up to 180 degrees
			# behind the player, so a held S ended up walking "forward" on screen.
			var forward := Vector3(-sin(yaw),0,-cos(yaw))
			if velocity.normalized().dot(forward)>FOLLOW_MIN_FORWARD: wanted_yaw=atan2(-velocity.x,-velocity.z)
			else: wanted_yaw=yaw
		wanted_pitch=DEFAULT_PITCH
	# MOVE heading guard: while a movement key is held its world direction is
	# latched to the view heading at press. Automatic follow may drift at most
	# MAX_HEADING_DRIFT from that heading, so W/S/A/D never reverse on screen.
	var guarded := false
	if not manual and not recentering and view.player.latched and view.player.frame_heading()!=null:
		var b: Basis=view.player.latched_basis
		var heading := atan2(b.z.x,b.z.z)
		var off := angle_difference(heading,wanted_yaw)
		if absf(off)>MAX_HEADING_DRIFT: wanted_yaw=wrapf(heading+signf(off)*MAX_HEADING_DRIFT,-PI,PI)
		guarded=true
	var omega := 10.0 if reduced else 5.0
	var error := angle_difference(yaw,wanted_yaw)
	var acceleration := clampf(omega*omega*error-2.0*omega*yaw_velocity,-deg_to_rad(130.0),deg_to_rad(130.0))
	yaw_velocity=clampf(yaw_velocity+acceleration*dt,-deg_to_rad(65.0),deg_to_rad(65.0))
	yaw=wrapf(yaw+yaw_velocity*dt,-PI,PI)
	if guarded:
		var b2: Basis=view.player.latched_basis
		var h2 := atan2(b2.z.x,b2.z.z)
		var off2 := angle_difference(h2,yaw)
		if absf(off2)>MAX_HEADING_DRIFT:
			yaw=wrapf(h2+signf(off2)*MAX_HEADING_DRIFT,-PI,PI); yaw_velocity=0.0
	if recentering and absf(angle_difference(yaw,recenter_target))<0.02 and absf(yaw_velocity)<0.05: recentering=false
	was_recentering=recentering
	heading_orbit = manual or recentering
	var p := Smooth.scalar(pitch,pitch_velocity,wanted_pitch,omega,dt)
	pitch=p.x; pitch_velocity=p.y
	var d := Smooth.scalar(distance,distance_velocity,wanted_distance,omega,dt)
	distance=d.x; distance_velocity=d.y

func attach(presenter) -> void:
	view = presenter
	process_physics_priority = 20 # after locomotion and module-owned grid/combat motion
	cam = Camera3D.new()
	cam.name = "follow_camera"
	view.world.add_child(cam)
	render_camera=Camera3D.new()
	render_camera.name="camera_flow_render"
	view.world.add_child(render_camera)
	process_priority=50 # sample/resolve after all fixed-tick camera producers
	view.actions.heading_provider=heading
	if OS.has_feature("web"):
		trace_enabled=bool(JavaScriptBridge.eval("new URLSearchParams(location.search).get('camera_trace')==='1'"))
		if trace_enabled:
			var cap := int(JavaScriptBridge.eval("Number(new URLSearchParams(location.search).get('cam_fps'))"))
			if cap in [30,60,144]: Engine.max_fps=cap
			JavaScriptBridge.eval("window.camFrames=[]")
		# Element capture, NOT pointer-lock: retain canvas/keyboard focus without
		# hiding the cursor, grabbing the OS pointer or changing key bindings.
		JavaScriptBridge.eval("""(() => { const c=document.querySelector('canvas'); if(!c||c.dataset.feel2drag)return; c.dataset.feel2drag='1'; c.addEventListener('pointerdown',e=>{if(e.button===0){c.focus({preventScroll:true});c.setPointerCapture(e.pointerId);}}); c.addEventListener('pointerup',e=>{if(c.hasPointerCapture(e.pointerId))c.releasePointerCapture(e.pointerId);}); c.addEventListener('pointercancel',e=>{if(c.hasPointerCapture(e.pointerId))c.releasePointerCapture(e.pointerId);}); })()""")
	reset()
func reset() -> void:
	# A same-room rebuild (pickup/collect) must not re-apply its authored hint.
	var identity: int=view.room_root.get_instance_id() if view.room_root!=null else 0
	var room_key: String=str(view.room_root.get_meta("cam_room_key",identity)) if view.room_root!=null else ""
	if view.get("runtime")!=null: room_key=str(view.runtime.state.location)
	var changed: bool=not has_meta("room_key") or str(get_meta("room_key"))!=room_key
	set_meta("room_key",room_key)
	if not changed and presentation_ready: return
	ready_centre = false; reset_presentation=true
	centre_velocity=Vector3.ZERO; yaw_velocity=0.0; pitch_velocity=0.0; distance_velocity=0.0
	dragging=false; mouse_delta=Vector2.ZERO; idle_ticks=0; recentering=false; orbit_override=false
	was_recentering=false; heading_orbit=false
	var back: Vector3 = view.camera.global_basis.z
	yaw=atan2(back.x,back.z); wanted_yaw=yaw
	heading_yaw=yaw; heading_ready=true
	pitch=DEFAULT_PITCH; wanted_pitch=pitch
	distance=DEFAULT_DISTANCE; wanted_distance=distance
func available() -> bool:
	return enabled and view.room_root != null and not (view.module_host != null and view.module_host.puzzle != null and view.module_host.puzzle.active)
func current() -> Camera3D:
	return cam if available() else view.camera
func cycle() -> void:
	view.select_camera(view.camera_index+1)
	anchor_steps += 1
	enabled = anchor_steps > view.room_root.camera_nodes.size()
	if enabled: anchor_steps = 0; reset()
	else: view.camera.current = true
func _physics_process(delta: float) -> void:
	if view==null or view.room_root==null: return
	if not view.simulation_enabled and delta>0.0: return
	if available(): update_follow(maxf(delta,1.0/60.0))
	var source: Camera3D=cam if available() else view.camera
	if view.module_host!=null and view.module_host.combat_camera.weight>0.0 and is_instance_valid(view.module_host.combat_camera.cam): source=view.module_host.combat_camera.cam
	previous_pose=next_pose; previous_fov=next_fov; previous_aim=next_aim
	var source_back: Vector3=source.global_basis.z
	if not presentation_ready and Vector2(source_back.x,source_back.z).length()>0.01:
		heading_yaw=atan2(source_back.x,source_back.z); heading_ready=true
	if source!=cam: heading_orbit=false
	var root_point: Vector3=view.player.global_position+Vector3.UP*0.8
	next_aim=source.global_position-source.global_basis.z*maxf(1.0,source.global_position.distance_to(root_point))
	if source==cam: next_aim=centre
	elif view.module_host!=null and source==view.module_host.combat_camera.cam:
		var combat_centre=view.module_host.combat_camera.get("centre")
		if combat_centre is Vector3: next_aim=combat_centre+Vector3.UP*0.85
	var desired_pose: Transform3D=source.global_transform
	if presentation_ready and not reset_presentation:
		var error_m: float=next_pose.origin.distance_to(desired_pose.origin)
		# A shoulder/occluder candidate can change by metres in one tick. Its
		# critically-damped filter slows continuously with that error instead of
		# treating a new collision solution as a demand for a high-speed pan.
		var sample_omega: float=(28.0 if view.actions.profile.options.reduced_motion else 18.0)/sqrt(1.0+pow(error_m/0.8,2.0))
		var sample: Array=Smooth.spring(next_pose.origin,sample_velocity,desired_pose.origin,sample_omega,maxf(delta,1.0/60.0))
		desired_pose.origin=sample[0]; sample_velocity=sample[1]
	next_pose=desired_pose; next_fov=source.fov
	if reset_presentation or not presentation_ready:
		previous_pose=next_pose; previous_fov=next_fov; previous_aim=next_aim
		render_aim=next_aim; aim_velocity=Vector3.ZERO
		render_camera.global_transform=next_pose; render_camera.fov=next_fov
		eye_velocity=Vector3.ZERO; sample_velocity=Vector3.ZERO; rotation_velocity=Vector3.ZERO; fov_velocity=0.0
		presentation_ready=true; reset_presentation=false
	for property in ["environment","attributes","cull_mask","near","far","keep_aspect"]: render_camera.set(property,source.get(property))

func update_follow(dt: float) -> void:
	# Root/capsule reference only. Never sample skeleton, head or animation bob.
	var target: Vector3 = view.player.global_position + Vector3.UP * 0.8
	var reduced: bool = view.actions.profile.options.reduced_motion
	if not ready_centre: centre=target; centre_velocity=Vector3.ZERO; ready_centre=true
	else:
		var desired: Vector3=centre+Smooth.soft_error(target-centre,0.035 if reduced else 0.08)
		var result: Array=Smooth.spring(centre,centre_velocity,desired,18.0 if reduced else 9.0,dt)
		centre=result[0]; centre_velocity=result[1]
	orbit_tick(reduced,dt)
	var solution := camera_solution(yaw,target)
	var avoided := false
	if (solution.eye as Vector3).distance_to(target)<1.6:
		# A new solid prop/NPC can be immediately beside the player. Pulling
		# through the near plane would put the lens inside their torso. Search
		# nearby shoulder angles, then the opposite side, with the SAME sweep.
		var held_heading=null
		if view.player.latched and view.player.frame_heading()!=null and not heading_orbit:
			var lb: Basis=view.player.latched_basis
			held_heading=atan2(lb.z.x,lb.z.z)
		for offset in [0.45,-0.45,0.9,-0.9,1.5,-1.5,PI]:
			# MOVE: while a direction is held, never swing the lens past the
			# drift budget to dodge a close-up; accept the pulled-in view.
			if held_heading!=null and absf(angle_difference(held_heading,yaw+offset))>MAX_HEADING_DRIFT: continue
			var alternative := camera_solution(yaw+offset,target)
			if (alternative.eye as Vector3).distance_to(target)>(solution.eye as Vector3).distance_to(target): solution=alternative
			if (solution.eye as Vector3).distance_to(target)>=1.6: break
		avoided=true
	var eye: Vector3=solution.eye
	var pulled: bool=solution.pulled
	cam.global_position=eye
	cam.look_at(centre)
	cam.fov=55.0; cam.near=0.08; cam.far=view.camera.far
	var combat_owns: bool=view.module_host != null and view.module_host.combat_camera.weight>0.0
	if not combat_owns: cam.current=true
	last={"centre":[centre.x,centre.y,centre.z],"eye":[eye.x,eye.y,eye.z],"lag":centre.distance_to(target),"pulled_in":pulled,"reduced_motion":reduced,"yaw":yaw,"pitch":pitch,"distance":distance,"dragging":dragging,"idle_ticks":idle_ticks,"avoided_close_up":avoided}

func _process(delta: float) -> void:
	if view==null: return
	if not presentation_ready: _physics_process(0.0)
	var alpha := Engine.get_physics_interpolation_fraction()
	if not view.simulation_enabled or not is_physics_processing(): alpha=1.0
	present(delta,alpha)
	if trace_enabled and not render_last.is_empty():
		render_seconds+=delta
		var row: Dictionary=render_last.duplicate()
		row["t"]=render_seconds; row["tick"]=view.actions.tick
		row["room"]=view.runtime.state.location
		row["phase"]=view.room_transition.phase if view.room_transition!=null else "idle"
		row["fade"]=view.room_transition.fade if view.room_transition!=null else 0.0
		row["target_eye"]=last.get("eye",[]); row["target_lag"]=last.get("lag",0.0)
		row["pulled_in"]=last.get("pulled_in",false); row["avoided_close_up"]=last.get("avoided_close_up",false)
		JavaScriptBridge.eval("if(window.camFrames.length<24000)window.camFrames.push("+JSON.stringify(row)+")")

func present(delta: float, alpha: float) -> void:
	if not presentation_ready or delta<=0.0: return
	# Interpolate *presentation samples*, never native body transforms. A second
	# analytic spring keeps velocity/acceleration continuous at sample boundaries
	# and at combat/puzzle/obstruction target switches. One renderer owns all modes.
	var target := previous_pose.interpolate_with(next_pose,clampf(alpha,0.0,1.0))
	var lens := lerpf(previous_fov,next_fov,clampf(alpha,0.0,1.0))
	var reduced: bool=view.actions.profile.options.reduced_motion
	var omega := 22.0 if reduced else 12.0
	# Substeps retain angular stability after slow/stalled renders without a cut.
	# Do not repay a missed render as one large visible camera move. The visual
	# clock drops excess wall time after a stall; physics/replay clocks do not.
	# This is a time budget, not a positional lag clamp or target teleport.
	if delta>1.0/30.0:
		presentation_rate=minf(presentation_rate,(1.0/30.0)/delta)
		presentation_rate_velocity=0.0
	else:
		var rate := Smooth.scalar(presentation_rate,presentation_rate_velocity,1.0,6.0,delta)
		presentation_rate=rate.x; presentation_rate_velocity=rate.y
	var remaining := minf(delta*presentation_rate,1.0/30.0)
	while remaining>0.0000001:
		var dt := minf(remaining,1.0/120.0); remaining-=dt
		var eye: Array=Smooth.spring(render_camera.global_position,eye_velocity,target.origin,omega,dt)
		var proposed: Vector3=eye[1]
		# Preserve the exact critical spring below ordinary pan speed. Extreme
		# obstruction/shoulder changes use a C2 soft velocity ceiling (6 -> 8m/s),
		# never a maximum-lag positional clamp or hard catch-up teleport.
		if proposed.length()>6.0 or eye_velocity.length()>6.0:
			if proposed.length()>6.0: proposed=proposed.normalized()*(6.0+2.0*tanh((proposed.length()-6.0)/2.0))
			render_camera.global_position+=(eye_velocity+proposed)*0.5*dt
			eye_velocity=proposed
		else:
			render_camera.global_position=eye[0]; eye_velocity=proposed
		var f := Smooth.scalar(render_camera.fov,fov_velocity,lens,omega,dt)
		render_camera.fov=f.x; fov_velocity=f.y
	# Aim from the actual smoothed eye, not the unfiltered candidate's basis.
	# Otherwise slow renders can leave eye and yaw on different sides of the
	# player. Aim keeps real-time bounded tracking while positional stall debt
	# is discarded; it never reads the animated head.
	var aim_target := previous_aim.lerp(next_aim,clampf(alpha,0.0,1.0))
	remaining=minf(delta,0.1)
	while remaining>0.0000001:
		var dt := minf(remaining,1.0/120.0); remaining-=dt
		var look: Array=Smooth.spring(render_aim,aim_velocity,aim_target,26.0 if reduced else 18.0,dt)
		render_aim=look[0]; aim_velocity=look[1]
		if render_aim.distance_to(render_camera.global_position)<0.05: continue
		var q := render_camera.global_basis.get_rotation_quaternion()
		var destination := Basis.looking_at(render_aim-render_camera.global_position,Vector3.UP).get_rotation_quaternion()
		var error := destination*q.inverse()
		if error.w<0.0: error=-error
		var angle := error.get_angle()
		if angle>0.00001:
			var axis := error.get_axis()
			var desired: Vector3=axis*angle
			var acceleration: Vector3=(desired*64.0-rotation_velocity*16.0).limit_length(deg_to_rad(240.0))
			rotation_velocity=(rotation_velocity+acceleration*dt).limit_length(deg_to_rad(85.0))
			var step := rotation_velocity*dt
			if step.length()>0.0000001: render_camera.global_basis=Basis(Quaternion(step.normalized(),step.length())*q)
		else: rotation_velocity=rotation_velocity.move_toward(Vector3.ZERO,deg_to_rad(240.0)*dt)
	render_camera.current=true
	# MOVE: the heading a new press latches is the yaw of the frame on screen.
	# The fixed-tick candidate can jump (shoulder/close-up avoidance) while the
	# drawn view eases; latching that candidate made W disagree with the image.
	# It is sampled into the recorded input frame, so replays stay exact.
	var drawn_back: Vector3=render_camera.global_basis.z
	if Vector2(drawn_back.x,drawn_back.z).length()>0.01:
		heading_yaw=atan2(drawn_back.x,drawn_back.z); heading_ready=true
	var eye: Vector3=render_camera.global_position
	var euler: Vector3=render_camera.global_basis.get_euler()
	render_last={"eye":[eye.x,eye.y,eye.z],"yaw":euler.y,"pitch":euler.x,"fov":render_camera.fov,"alpha":alpha,"framed":render_camera.is_position_in_frustum(view.player.global_position+Vector3.UP*0.8)}

func camera_solution(angle: float, target: Vector3) -> Dictionary:
	var back := Vector3(sin(angle),0,cos(angle))
	var eye := centre + back * cos(pitch) * distance + Vector3.UP * sin(pitch) * distance
	var shell: Dictionary=view.room_root.shell_info
	if not shell.is_empty() and not view.room_root.presentation.get("exterior",false):
		eye.y=minf(eye.y,maxf(centre.y+0.25,float(shell.get("meta",{}).get("height",3.0))-0.3))
	var pulled := false
	var right:=back.cross(Vector3.UP).normalized()*0.16
	for offset in [Vector3.ZERO,right,-right,Vector3.UP*0.16]:
		var query:=PhysicsRayQueryParameters3D.create(target+offset,eye+offset,1)
		query.exclude=[view.player.get_rid()]
		var hit: Dictionary=view.world.get_world_3d().direct_space_state.intersect_ray(query)
		if not hit.is_empty():
			eye=hit.position-offset+(target+offset-hit.position).normalized()*0.25
			pulled=true
	return {"eye":eye,"pulled":pulled}
