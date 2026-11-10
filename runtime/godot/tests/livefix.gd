extends SceneTree
# Integration regression: production sample_live/InputMap, never submit_frame or replay frames.
var view
var failures := []
var rows := []
var opts := {}
func _initialize() -> void: call_deferred("run")
func expect(ok: bool, message: String) -> void:
	if not ok: failures.append(message); print("FAIL ", message)
func ticks(n: int) -> void:
	for i in n: await physics_frame
	await process_frame
func key(code: int, down: bool) -> void:
	var event := InputEventKey.new()
	event.physical_keycode = code; event.keycode = code; event.pressed = down
	Input.parse_input_event(event)
func tap(code: int, hold := 8) -> void:
	key(code, true); await ticks(hold); key(code, false); await ticks(8)
func snap(label: String) -> void:
	var p: Vector3 = view.player.position
	var active: Camera3D = view.viewport.get_camera_3d()
	var eye: Vector3 = active.global_position
	var uv: Vector2 = active.unproject_position(p+Vector3.UP*0.7)
	var row := {"label":label,"tick":view.actions.tick,"source":view.actions.source,"context":view.actions.context,"raw":view.actions.last_frame,"position":[p.x,p.y,p.z],"camera":[eye.x,eye.y,eye.z],"screen":[uv.x,uv.y],"in_frustum":active.is_position_in_frustum(p+Vector3.UP*0.7),"dialogue":view.runtime.state.dialogue,"enabled":view.player.enabled,"text":view.n64_ui.dlg_text,"shown":view.n64_ui.dlg_on,"pages":view.text_pages.size(),"page":view.page_index,"actions":view.ui_actions.map(func(a): return a.id)}
	rows.append(row); print("LIVEFIX ",JSON.stringify(row))
	if opts.has("shots") and DisplayServer.get_name() != "headless": await view.capture(opts.shots.path_join(label+".png"))
func move_keys(v: Vector2) -> void:
	for row in [[KEY_A,v.x<0],[KEY_D,v.x>0],[KEY_W,v.y<0],[KEY_S,v.y>0]]: key(row[0],row[1])
func walk(at: Vector3, radius := 0.75) -> bool:
	# Real physical keys, steering from observed simulation positions, no teleports.
	for i in 1200:
		var diff: Vector3 = at-view.player.position; diff.y=0
		if diff.length()<radius:
			move_keys(Vector2.ZERO); await ticks(12); return true
		var b: Basis=view.player.camera_basis
		var local := Vector2(diff.dot(b.x),diff.dot(b.z)).normalized()
		var v := Vector2(signf(local.x) if absf(local.x)>0.35 else 0.0,signf(local.y) if absf(local.y)>0.35 else 0.0)
		move_keys(v); await ticks(1)
	move_keys(Vector2.ZERO); await ticks(12); return false
func talk_test() -> void:
	var thaw: bool=view.runtime.game.id=="thaw"
	if thaw:
		var door: Vector3=view.room_root.target_positions["move:pod_bay:workstation_hatch"]
		expect(await walk(door),"approach workstation door using live WASD")
		await tap(KEY_E); await ticks(24)
		expect(view.runtime.state.location=="workstation","live E enters workstation")
	if view.runtime.state.location != ("workstation" if thaw else "hub"): return
	var action_id := "interact:talk_neri" if thaw else "interact:learn"
	var target: Vector3=view.contextual.position_for(view,action_id)
	expect(await walk(target,0.35),"approach NPC using live WASD")
	await snap("npc-approach")
	print("CANDIDATES ",view.contextual.candidates(view))
	for round_index in 2:
		await tap(KEY_E)
		await snap("talk-%d-open"%round_index)
		expect(view.dialogue_active(),"held opening E must not immediately cancel the conversation")
		if not view.dialogue_active(): continue
		var pages: int=view.text_pages.size()
		for page in range(1,pages):
			await tap([KEY_E,KEY_SPACE,KEY_ENTER][(page-1)%3])
			expect(view.dialogue_active(),"advance every text page before choosing/closing")
		await snap("talk-%d-last-page"%round_index)
		await tap(KEY_ENTER)
		await snap("talk-%d-closed"%round_index)
		expect(not view.dialogue_active(),"Enter closes completed NPC dialogue")
		# The next tap closes a post-choice line, never reopens the NPC.
		if view.n64_ui.dlg_on: await tap(KEY_SPACE)
		expect(not view.n64_ui.dlg_on,"post-dialogue line closes")
		var before: Vector3=view.player.position
		key(KEY_S,true); await ticks(24); key(KEY_S,false); await ticks(12)
		expect(view.player.position.distance_to(before)>0.15,"player regains control and walks away")
		expect(await walk(target,0.35),"walk back to NPC for second conversation")
func follow_test() -> void:
	await snap("follow-before")
	var maximum := 0.0
	var camera_trace := []
	for code in [KEY_W,KEY_D,KEY_S,KEY_A]:
		key(code,true)
		for i in 90:
			await ticks(1)
			var cam: Camera3D=view.viewport.get_camera_3d()
			var target: Vector3=view.player.position+Vector3.UP*0.7
			maximum=maxf(maximum,cam.global_position.distance_to(target))
			camera_trace.append([cam.position.x,cam.position.y,cam.position.z])
			expect(cam.is_position_in_frustum(target),"follow keeps player framed on every fixed tick")
		key(code,false); await ticks(12)
	await snap("follow-after")
	expect(maximum<7.0,"follow camera remains within seven metres of player")
	print("FOLLOW_BOUND ",maximum," CAMERA_TRACE ",JSON.stringify(camera_trace).sha256_text())
	if view.has_method("exploration_camera"):
		await tap(KEY_C)
		expect(not view.follow_camera.enabled and view.viewport.get_camera_3d()==view.camera,"C exposes authored framing")
		for i in view.room_root.camera_nodes.size(): await tap(KEY_C)
		expect(view.follow_camera.enabled,"C returns to follow after every authored anchor")
		view.actions.configure({"version":1,"options":{"reduced_motion":true}})
		key(KEY_W,true); await ticks(30); key(KEY_W,false); await ticks(12)
		expect(float(view.follow_camera.last.lag)<0.001,"reduced motion has no trailing camera lag or orbit")
		var blocker := StaticBody3D.new()
		var shape := CollisionShape3D.new()
		var sphere := SphereShape3D.new(); sphere.radius=0.6; shape.shape=sphere
		blocker.add_child(shape); view.world.add_child(blocker)
		blocker.position=(view.player.position+Vector3.UP*0.8).lerp(view.follow_camera.cam.position,0.6)
		await ticks(4)
		expect(view.follow_camera.last.pulled_in,"follow pulls in before a static obstruction")
		blocker.queue_free(); await ticks(4)

func combat_test(journey := false) -> void:
	if journey:
		await talk_test()
		expect(await walk(view.module_host.anchor("move:hub:to_arena")),"live walk to Cairn Ring portal")
		await tap(KEY_E); await ticks(30)
		expect(view.runtime.state.location=="arena","live E enters Cairn Ring after dialogue")
	var start := ""
	for a in view.ui_actions:
		if a.id.begins_with("challenge:start:"): start=a.id; break
	expect(start != "","combat entry is available")
	if start=="": return
	expect(await walk(view.module_host.anchor(start),0.4),"live WASD approaches combat entry")
	await tap(KEY_E); await ticks(12)
	var host=view.module_host
	expect(host.combat != null,"live E starts combat")
	if host.combat==null: return
	var fight_camera: Camera3D=view.viewport.get_camera_3d()
	print("COMBAT_FRAME ",JSON.stringify({"camera":str(fight_camera.name),"profile":host.combat_camera.profile,"frame":host.combat_camera.last,"feet":fight_camera.unproject_position(view.player.position+Vector3.UP*0.05),"head":fight_camera.unproject_position(view.player.position+Vector3.UP*1.5),"viewport":view.viewport.size}))
	expect(fight_camera.is_position_in_frustum(view.player.position+Vector3.UP*0.05) and fight_camera.is_position_in_frustum(view.player.position+Vector3.UP*1.5),"combat framing includes the player's feet and head, not only its centre")
	var swings: int=host.combat.swings
	await tap(KEY_E)
	expect(host.combat.swings>swings,"live E performs one combat swing")
	await snap("combat-swing")
	if opts.get("case")=="combat_aspect": await aspect_test()

func aspect_test() -> void:
	for dims in [Vector2i(1280,720),Vector2i(1280,800),Vector2i(960,720)]:
		root.size=dims; await ticks(6)
		var ratio: float = float(dims.x)/dims.y
		expect(absf(float(view.viewport.size.x)/view.viewport.size.y-ratio)<0.01,"low-resolution world fills %s without aspect distortion"%dims)
		expect(view.viewport.size.y==240,"N64 vertical pixel count stays 240")
		await tap(KEY_TAB)
		if DisplayServer.get_name() != "headless" and view.module_host != null and view.module_host.combat != null:
			await RenderingServer.frame_post_draw
			var image: Image=view.viewport.get_texture().get_image()
			var gold := 0
			for x in range(8,8+view.module_host.combat.max_health*5):
				for y in range(30,36):
					var pixel: Color=image.get_pixel(x,y)
					if pixel.is_equal_approx(view.n64_ui.C_LAMP): gold += 1
			expect(gold >= view.module_host.combat.max_health*12,"combat health pips occupy their own row below dialogue location/counters")
		await snap("aspect-%dx%d-menu"%[dims.x,dims.y])
		await tap(KEY_TAB)
		if opts.has("shots"): await snap("aspect-%dx%d-world"%[dims.x,dims.y])

func run() -> void:
	for arg in OS.get_cmdline_user_args():
		var a := arg.trim_prefix("--").split("=",true,1)
		if a.size()==2: opts[a[0]]=a[1]
	view=load("res://main.tscn").instantiate(); root.add_child(view)
	await ticks(12)
	if opts.get("case","empty") == "empty":
		await snap("before")
		await tap(KEY_E)
		await snap("after-E")
		expect(not view.n64_ui.dlg_on or view.n64_ui.dlg_text != "", "empty narration must not leave a blocking-looking blank panel")
		var before: Vector3=view.player.position
		key(KEY_W,true); await ticks(60); key(KEY_W,false); await ticks(12)
		await snap("after-W")
		expect(view.player.position.distance_to(before)>0.2,"live W moves from first screen")
	elif opts.get("case") == "talk": await talk_test()
	elif opts.get("case") == "follow": await follow_test()
	elif opts.get("case") == "aspect": await aspect_test()
	elif opts.get("case") in ["combat","combat_aspect","journey"]: await combat_test(opts.get("case")=="journey")
	print("LIVEFIX_RESULT ",JSON.stringify({"failures":failures,"rows":rows}))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
