extends SceneTree
## Integrated presenter seams: settings, entry, freeze and strict movie playback.
var view
var failures := []
var checks := 0
func _initialize() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	checks+=1
	if not ok: failures.append(message); print("FAIL ",message)
func ticks(n: int) -> void:
	for i in n: await physics_frame
	await process_frame
func send(digital: Array, n := 1) -> void:
	for i in n:
		view.actions.submit_frame({"digital":digital})
		await ticks(1)
func run() -> void:
	view=load("res://main.tscn").instantiate(); root.add_child(view)
	await ticks(12)
	view.actions.configure({"version":1}); view.actions.set_source("bot")
	await send([],2)
	await send(["menu"],1); await send([],1)
	expect(view.belt.settings_open,"Esc opens actual settings")
	await send(["run"],1); await send([],1)
	expect(view.actions.profile.options.run_mode=="toggle","settings run row responds to new run action")
	await send(["menu"],1); await send([],2)
	var legacy: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://tests/fixtures/feel2_legacy_input.json"))
	view.actions.configure(legacy.cases[0].profile); view.actions.restore({})
	await send(["menu"],1); await send([],1)
	await send(["action_menu"],1); await send([],1)
	expect(not view.actions.profile.bindings.has("run") and view.actions.binding_glyph("walk")=="Sh","legacy preset switch preserves old Shift precision semantics")
	await send(["menu"],1); await send([],2)
	view.actions.configure({"version":1}); view.actions.restore({})
	var bad: Dictionary=view.replay.state(); bad.actions["run_toggle"]="not-a-bool"
	expect(not view.replay.valid_initial(bad),"movie validator rejects malformed optional run latch")
	view.actions.configure({"version":1}); view.actions.restore({})
	var door_id := "move:pod_bay:workstation_hatch"
	if not view.room_root.target_positions.has(door_id):
		expect(false,"integration fixture is shipped Thaw"); await finish(); return
	# Explicit fixture placement, not a claimed physical bot journey.
	view.player.position=view.room_root.target_positions[door_id]
	if view.player.has_method("place_in_room"): expect(view.player.place_in_room(view.room_root).ok,"door setup capsule-clear")
	await send([],3)
	var file := "res://feel2-integrated.h64movie.json"
	expect(view.replay.start_record(file).ok,"record from real presenter before portal")
	var observed_release := []
	var envelope=view.get("room_transition")
	if envelope!=null: envelope.finished.connect(func(): observed_release.append(not view.actions.blocked_move and view.actions.raw_previous.is_empty()))
	await send(["primary"],1)
	expect(view.runtime.state.location=="workstation","production contextual primary enters matching room")
	var transition=view.get("room_transition")
	expect(transition!=null and transition.active(),"successful room entry has an active presentation transition")
	if transition!=null:
		expect(transition.ghost_visual!=null,"real runtime unnamed player has a visible exit-walk clone")
		expect(transition.ghost_viewport.find_children("*","CollisionObject3D",true,false).is_empty(),"presentation exit clone contains no native physics entities")
	if transition==null: await finish(); return
	await ticks(2)
	var tick: int=view.actions.tick
	var cursor: int=view.replay.cursor
	var canonical: String=view.replay.digest(view.replay.state())
	await ticks(5)
	expect(view.actions.tick==tick and view.replay.cursor==cursor,"fade adds zero canonical/movie ticks")
	expect(canonical==view.replay.digest(view.replay.state()),"frozen fade leaves canonical snapshot unchanged")
	for i in 100:
		if not transition.active(): break
		await ticks(1)
	expect(not transition.active(),"transition completes for neutral bot without live OS dependency")
	expect(not observed_release.is_empty() and observed_release[0],"neutral release fence clears stale movement and held-edge latch before first new input")
	var room: Dictionary=view.runtime.rooms.workstation
	var destination: Dictionary={}
	for d in room.doors:
		if d.id=="pod_hatch": destination=d
	# Resolve exact reciprocal door from source data, not a guessed identifier.
	var source: Dictionary=view.runtime.rooms.pod_bay
	var to_door := ""
	for d in source.doors:
		if d.id=="workstation_hatch": to_door=d.to_door
	for d in room.doors:
		if d.id==to_door: destination=d
	var at: Vector3=view.room_root.target_anchors.get("move:workstation:"+to_door,view.room_root.door_position(destination,room.grid_size))
	var centre:=Vector3(room.grid_size[0]/2.0,0.1,room.grid_size[1]/2.0)
	var expected: Vector3=Vector3(at.x,0.1,at.z).lerp(centre,0.17)
	expect(Vector2(view.player.position.x,view.player.position.z).distance_to(Vector2(expected.x,expected.z))<0.5,"actor bridge cannot replace reciprocal-door arrival with default spawn")
	expect(view.drawing_camera().is_position_in_frustum(view.player.position+Vector3.UP*0.8),"arrival camera framed before reveal")
	expect(not view.n64_ui.dlg_on,"room name card does not become entry narration bubble")
	await send([],70)
	var recorded: Dictionary=view.replay.stop_record()
	expect(recorded.ok,"integrated transition movie saved")
	for repeat in 2:
		var played: Dictionary=view.replay.load_movie(file,false)
		expect(played.ok,"strict integrated movie loads")
		if not played.ok: print("REFUSED ",played); continue
		for i in 1000:
			if view.replay.finished: break
			await ticks(1)
		expect(view.replay.finished and view.replay.result.get("ok",false),"transition movie passes strict production playback")
		if not view.replay.result.get("ok",false): print(view.replay.result)
	await finish()
func finish() -> void:
	print("FEEL2_INTEGRATED ",JSON.stringify({"checks":checks,"failures":failures}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
