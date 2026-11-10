extends SceneTree
## Production camera, scripted physics paths sampled at exact 30/60/144 render caps.
## Synthetic scheduler, not a measured hardware FPS claim. No simulated actor writes
## occur in production camera code; this fixture alone supplies the trajectory.
var opts := {}
var rows := []
var failures := []
var view
class Actor extends Node3D:
	var actual_velocity := Vector3.ZERO
	var facing_yaw := 0.0
	func get_rid() -> RID: return RID()
class Inputs extends RefCounted:
	var source := "live"
	var context := "gameplay"
	var last_frame := {}
	var profile := {"options":{"reduced_motion":false}}
	func vector(a: Array) -> Vector2: return Vector2(a[0],a[1])
class RoomStub extends Node3D:
	var shell_info := {}
	var presentation := {"exterior":true}
	var camera_nodes := []
class CombatStub extends RefCounted:
	var weight := 0.0
	var cam: Camera3D
class PuzzleStub extends RefCounted:
	var active := false
class HostStub extends RefCounted:
	var combat_camera = CombatStub.new()
	var puzzle = PuzzleStub.new()
class ViewStub extends Node:
	var world: Node3D
	var camera: Camera3D
	var player
	var room_root
	var actions = Inputs.new()
	var module_host = null
	var simulation_enabled := true
	var camera_index := 0
	var room_transition = null
	func select_camera(_index): pass
func _initialize() -> void: call_deferred("run")
func point(path: String, t: float) -> Vector3:
	if path in ["straight","reduced"]: return Vector3(0,0,-minf(t,4.0)*2.0)
	if path == "reversal": return Vector3(0,0,-2.0*t if t<2.0 else -4.0+2.0*minf(t-2.0,3.0))
	if path in ["circle","stalls","loaded_circle"]: return Vector3(2.0*sin(t),0,2.0*(cos(t)-1.0))
	if path == "door": return Vector3(0,0,-minf(t,2.0)) if t<3.0 else Vector3(12,0,-2.0-minf(t-3.0,2.0))
	return Vector3.ZERO
func run() -> void:
	for arg in OS.get_cmdline_user_args():
		var parts := arg.trim_prefix("--").split("=",true,1)
		if parts.size()==2: opts[parts[0]]=parts[1]
	var script = load(opts.get("camera","res://view/follow_camera.gd"))
	for fps in [30,60,144]:
		for path in ["straight","circle","reversal","door","orbit","framing","reduced","stalls","obstruction_switch","loaded_circle"]:
			view=ViewStub.new();root.add_child(view)
			view.world=Node3D.new();view.add_child(view.world)
			view.player=Actor.new();view.world.add_child(view.player)
			view.camera=Camera3D.new();view.world.add_child(view.camera)
			view.camera.position=Vector3(0,3,5);view.camera.look_at(Vector3.UP*0.8)
			view.room_root=RoomStub.new();view.world.add_child(view.room_root)
			var follow=script.new();view.add_child(follow);follow.attach(view)
			follow.set_process(false);follow.set_physics_process(false)
			view.actions.profile.options.reduced_motion=path=="reduced"
			var tick := -1
			var t := 0.0
			for frame in range(fps*7+1):
				var dt: float=1.0/18.0 if path=="loaded_circle" else (0.13 if path=="stalls" and frame>30 and frame%fps==0 else 1.0/float(fps))
				if frame>0: t+=dt
				var next_tick := floori(t*60.0+0.000001)
				while tick<next_tick:
					tick+=1
					var at := point(path,float(tick)/60.0)
					view.player.actual_velocity=(at-view.player.position)*60.0
					view.player.position=at
					if view.player.actual_velocity.length()>0.1: view.player.facing_yaw=atan2(-view.player.actual_velocity.x,-view.player.actual_velocity.z)
					view.actions.last_frame={"digital":["camera_left"] if path=="orbit" and tick>60 and tick<100 else (["camera_recenter"] if path=="orbit" and tick==120 else [])}
					if path=="door" and tick==180:
						view.room_root.set_meta("cam_room_key","arrival")
						follow.reset()
					if path in ["framing","obstruction_switch"] and tick==60:
						view.module_host=HostStub.new()
						view.module_host.combat_camera.cam=Camera3D.new()
						view.world.add_child(view.module_host.combat_camera.cam)
						view.module_host.combat_camera.cam.global_transform=follow.cam.global_transform
						view.module_host.combat_camera.cam.position+=Vector3(0.7,0.2,0.4)
						view.module_host.combat_camera.cam.fov=70.0
						view.module_host.combat_camera.weight=1.0
					if path=="obstruction_switch" and tick in [90,120,150,180]:
						view.module_host.combat_camera.cam.position=follow.cam.position+Vector3(4.5 if tick%60==0 else -4.5,0,0)
					if path=="framing" and tick==180:
						view.module_host.combat_camera.weight=0.0
						view.module_host.puzzle.active=true
						view.camera.global_transform=follow.cam.global_transform
						view.camera.position+=Vector3(-0.7,0.1,0.3)
						view.camera.fov=52.0
					if path=="framing" and tick==300: view.module_host.puzzle.active=false
					follow._physics_process(1.0/60.0)
				# Arrival reset is allowed ONLY behind the fully opaque door envelope.
				if follow.has_method("present"): follow.present(dt,clampf(t*60.0-float(next_tick),0.0,1.0))
				var camera: Camera3D=follow.cam
				if follow.get("render_camera")!=null: camera=follow.render_camera
				var p := camera.global_position
				var e := camera.global_basis.get_euler()
				rows.append({"fps":fps,"path":path,"frame":frame,"t":t,"eye":[p.x,p.y,p.z],"yaw":e.y,"pitch":e.x,"fov":camera.fov,"lag":follow.last.get("lag",0.0),"target_eye":follow.last.get("eye",[]),"framed":camera.is_position_in_frustum(view.player.global_position+Vector3.UP*0.8),"hidden":path=="door" and t>=2.8 and t<=3.2})
			view.free()
	var file := FileAccess.open(opts.output,FileAccess.WRITE)
	file.store_string(JSON.stringify({"rows":rows}));file.close()
	print("CAM_FLOW samples=",rows.size())
	quit()
