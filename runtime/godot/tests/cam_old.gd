extends Node
## Presentation-only third-person follow. One update per fixed simulation tick;
## authored cameras still supply the unchanged locomotion basis and replay hashes.
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

func orbit_tick(reduced: bool) -> void:
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
		wanted_yaw = wrapf(wanted_yaw-orbit.x*(0.022 if reduced else 0.032)-mouse_delta.x*0.006,-PI,PI)
		wanted_pitch = clampf(wanted_pitch+orbit.y*0.022+mouse_delta.y*0.004,0.15,1.05)
		idle_ticks=0
	else: idle_ticks += 1
	mouse_delta=Vector2.ZERO
	if "camera_recenter" in raw or idle_ticks>IDLE_TICKS:
		wanted_yaw=view.player.facing_yaw
		wanted_pitch=DEFAULT_PITCH
	if reduced:
		yaw=wanted_yaw; pitch=wanted_pitch; distance=wanted_distance
	else:
		yaw=lerp_angle(yaw,wanted_yaw,0.16 if idle_ticks>IDLE_TICKS else 0.28)
		pitch=lerpf(pitch,wanted_pitch,0.24)
		distance=lerpf(distance,wanted_distance,0.24)

func attach(presenter) -> void:
	view = presenter
	process_physics_priority = 20 # after locomotion and module-owned grid/combat motion
	cam = Camera3D.new()
	cam.name = "follow_camera"
	view.world.add_child(cam)
	if OS.has_feature("web"):
		# Element capture, NOT pointer-lock: retain canvas/keyboard focus without
		# hiding the cursor, grabbing the OS pointer or changing key bindings.
		JavaScriptBridge.eval("""(() => { const c=document.querySelector('canvas'); if(!c||c.dataset.feel2drag)return; c.dataset.feel2drag='1'; c.addEventListener('pointerdown',e=>{if(e.button===0){c.focus({preventScroll:true});c.setPointerCapture(e.pointerId);}}); c.addEventListener('pointerup',e=>{if(c.hasPointerCapture(e.pointerId))c.releasePointerCapture(e.pointerId);}); c.addEventListener('pointercancel',e=>{if(c.hasPointerCapture(e.pointerId))c.releasePointerCapture(e.pointerId);}); })()""")
	reset()
func reset() -> void:
	ready_centre = false
	dragging=false; mouse_delta=Vector2.ZERO; idle_ticks=0
	var back: Vector3 = view.camera.global_basis.z
	yaw=atan2(back.x,back.z); wanted_yaw=yaw
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
func _physics_process(_delta: float) -> void:
	if not view.simulation_enabled or not available(): return
	var target: Vector3 = view.player.global_position + Vector3.UP * 0.8
	var reduced: bool = view.actions.profile.options.reduced_motion
	if not ready_centre or reduced: centre = target; ready_centre = true
	else:
		centre = centre.lerp(target,0.18)
		centre = target + (centre-target).limit_length(0.8)
	orbit_tick(reduced)
	var solution := camera_solution(yaw,target)
	var avoided := false
	if (solution.eye as Vector3).distance_to(target)<1.6:
		# A new solid prop/NPC can be immediately beside the player. Pulling
		# through the near plane would put the lens inside their torso. Search
		# nearby shoulder angles, then the opposite side, with the SAME sweep.
		for offset in [0.45,-0.45,0.9,-0.9,1.5,-1.5,PI]:
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
