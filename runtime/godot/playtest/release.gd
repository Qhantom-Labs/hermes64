extends "res://actors/main.gd"
## Portable entry only: same story/presentation, resource-relative data, user-local saves.
var diagnostics := false
var diagnostic_tick := -1
var diagnostic_checked := false
var diagnostic_room_root := 0
var diagnostic_geometry := {}
func boot(game: Dictionary, opts: Dictionary = {}) -> Dictionary:
	opts["pack"] = "res://theme.json"
	opts["bindings"] = "res://bindings.json"
	opts["save"] = "user://saves/slot1.json"
	var result: Dictionary = super.boot(game,opts)
	if result.ok:
		process_priority=80 # diagnostics observe the final render rig, after priority 50
		set_process(true)
		state_changed.connect(ship_event)
		if OS.has_feature("web"):
			JavaScriptBridge.eval("window.hermes64={booted:true,events:0,lastAction:null}")
		return {"ok":true}
	return result

func _process(_delta: float) -> void:
	# Opt-in, read-only receiving-game receipt for real browser-key regressions.
	# No action injection, persistence, wall-clock gameplay or default-play cost.
	if not diagnostic_checked:
		diagnostic_checked = true
		if OS.has_feature("web"):
			var requested = JavaScriptBridge.eval("new URLSearchParams(location.search).get('diagnostics') === '1'")
			diagnostics = bool(requested)
			if diagnostics: print("LIVEFIX read-only browser diagnostics enabled")
	if not diagnostics or actions == null: return
	if actions.tick-diagnostic_tick < 6 and (room_transition==null or not room_transition.active()): return
	diagnostic_tick = actions.tick
	var c: Camera3D = viewport.get_camera_3d()
	var p: Vector3 = player.position
	var b: Basis = player.move_basis() if player.has_method("move_basis") else (player.latched_basis if player.latched else player.camera_basis)
	var host = module_host
	var snapshot := {"tick":actions.tick,"room":runtime.state.location,"position":[p.x,p.y,p.z],"right":[b.x.x,b.x.z],"back":[b.z.x,b.z.z],"context":actions.context,"dialogue":dialogue_active(),"panel":n64_ui.dlg_on,"text":n64_ui.dlg_text,"page":page_index,"pages":text_pages.size(),"candidate":current_candidate.get("id",""),"targets":room_root.target_positions,"raw":actions.last_frame,"viewport":[viewport.size.x,viewport.size.y],"framed":c.is_position_in_frustum(p+Vector3.UP*0.7),"framed_body":c.is_position_in_frustum(p+Vector3.UP*0.05) and c.is_position_in_frustum(p+Vector3.UP*1.5),"active":host.active_id if host != null else "","swings":host.combat.swings if host != null and host.combat != null else 0}
	var targets := {}
	for id in room_root.target_positions:
		var at: Vector3 = room_root.target_positions[id]
		targets[id] = [at.x,at.y,at.z]
	if host != null:
		for a in ui_actions:
			var at: Vector3 = host.anchor(a.id)
			if at != Vector3.INF: targets[a.id] = [at.x,at.y,at.z]
	snapshot.targets = targets
	snapshot["velocity"]=[player.actual_velocity.x,player.actual_velocity.y,player.actual_velocity.z]
	snapshot["follow"]=follow_camera.last if follow_camera!=null else {}
	# MOVE: on-screen direction of the held movement intent through the DRAWN camera.
	var rc: Camera3D = follow_camera.render_camera if follow_camera!=null else c
	var intent := Vector3(player.desired_velocity.x,0,player.desired_velocity.z)
	var root_at: Vector3 = p+Vector3.UP*0.8
	var screen := Vector2.ZERO
	if intent.length()>0.05: screen=(rc.unproject_position(root_at+intent.normalized()*0.5)-rc.unproject_position(root_at)).normalized()
	snapshot["screen_intent"]=[screen.x,screen.y]
	var rb: Vector3 = rc.global_basis.z
	snapshot["drawn_yaw"]=atan2(rb.x,rb.z)
	snapshot["heading"]=actions.last_frame.get("heading",[])
	snapshot["boundary"]=room_root.get("boundary_source")
	snapshot["run_mode"]=actions.profile.options.run_mode
	snapshot["reduced_motion"]=actions.profile.options.reduced_motion
	snapshot["transition"]={"phase":room_transition.phase,"fade":room_transition.fade,"card":room_transition.card_layout(),"ghost":room_transition.ghost_visual!=null} if room_transition!=null else {}
	snapshot["contacts"]=[]
	for i in player.get_slide_collision_count():
		var collider=player.get_slide_collision(i).get_collider()
		if collider!=null and collider.has_meta("solid_id"): snapshot.contacts.append(collider.get_meta("solid_id"))
	snapshot["native_probe"]={}
	if player.desired_velocity.length_squared()>0.01:
		var probe:=KinematicCollision3D.new()
		if player.test_move(player.global_transform,player.desired_velocity.normalized()*0.12,probe):
			var collider=probe.get_collider()
			if collider!=null and collider.has_meta("solid_id"): snapshot.native_probe={"solid_id":collider.get_meta("solid_id"),"travel":[probe.get_travel().x,probe.get_travel().y,probe.get_travel().z]}
	if diagnostic_room_root!=room_root.get_instance_id():
		diagnostic_room_root=room_root.get_instance_id()
		var solids := []
		for row in room_root.solid_definitions:
			var box: AABB=row.transform*row.box
			solids.append({"id":row.id,"ref":row.ref,"box":[box.position.x,box.position.y,box.position.z,box.size.x,box.size.y,box.size.z]})
		var free := []
		if player.room_navigation!=null:
			for cell in player.room_navigation.free_cells: free.append([cell.x,cell.y])
		diagnostic_geometry={"solids":solids,"free":free,"cell":0.25}
	snapshot["navigation"]=diagnostic_geometry
	JavaScriptBridge.eval("window.hermes64.diagnostic="+JSON.stringify(snapshot))

func ship_event(result: Dictionary) -> void:
	if OS.has_feature("web"):
		JavaScriptBridge.eval("window.hermes64.events++;window.hermes64.lastAction="+JSON.stringify(result.get("action","")))
