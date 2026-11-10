extends SceneTree
const View = preload("res://playtest/view.gd")
const Wire = preload("res://core/wire.gd")
const Dummy = preload("res://tests/controls_dummy.gd")
var view
var dummy
var failures := []
var receipts := []
func check(ok: bool, label: String) -> void:
	if not ok: failures.append(label); printerr("FAIL ",label)
func _initialize() -> void: call_deferred("run")
func frame(digital := []) -> void:
	view.actions.submit_frame({"digital":digital})
	await physics_frame; await process_frame
func input_for(case_number: int, t: int) -> Array:
	var d := []
	match case_number:
		1: if t<120: d=["move_up"]
		2: if t%60<[4,7,12,20][t/60]: d=["move_right"]
		3:
			if t<180: d=["move_up"]
			if t>=45 and t<90: d.append("walk")
		4: d=["move_up","move_right"] if t<60 else (["move_right"] if t<120 else [])
		5: d=["move_left"] if t<30 else (["move_left","move_right"] if t<90 else (["move_right"] if t<120 else []))
		6:
			if t<150 and t!=120: d=["move_up"]
			if t==60 or t==90: d.append("camera_cycle")
		7:
			if t<40: d=["move_up"]
			if t>=18 and t<120: d.append("focus")
			if t==30 or t==80: d.append("primary")
			if t==150: d.append("secondary")
		8:
			if t in [0,19,30,59]: d=["primary"]
		9:
			if t<40: d=["move_up","move_right","walk","primary"]
			elif t<80: d=["move_up","move_left","walk","dodge"]
			elif t<100: d=["move_up","walk","dodge"] # dropped key as received
		10:
			if t<90: d=["focus"]
			if t in [6,18,36]: d.append("primary")
			if t==39: d.append("dodge")
			if t>=95 and t<140: d.append("reset")
	return d
func run() -> void:
	view=View.new(); root.add_child(view)
	view.boot(Wire.read_json("res://game.json"),{"pack":"res://theme.json","bindings":"res://bindings.json","test":true,"save":"res://../matrix-save.json"})
	view.actions.set_source("bot")
	dummy=Dummy.new(); dummy.view=view; dummy.process_physics_priority=-75; view.add_child(dummy)
	view.replay.register_state("controls_test_fixture",dummy.snapshot,dummy.restore)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("--matrix_movie="):
			var opened: Dictionary = view.replay.load_movie(arg.trim_prefix("--matrix_movie="),true)
			if not opened.ok: printerr(opened); await view.quit_cleanly(2)
			return
	for i in 5: await frame()
	var initial: Dictionary = view.replay.state()
	for preset in ["left","right"]:
		for case_number in range(1,11):
			check(view.replay.restore_state(initial).ok,"fixture restore")
			view.actions.configure({"version":1,"preset":preset}); view.actions.set_source("bot")
			view.set_physics_process(true); view.player.set_physics_process(true)
			for i in 5: await frame()
			dummy.reset(case_number)
			var destination := "res://../matrix/%s-R%02d.h64movie.json" % [preset,case_number]
			DirAccess.make_dir_recursive_absolute(destination.get_base_dir())
			var trace:=FileAccess.open(destination+".trace.jsonl",FileAccess.WRITE)
			check(view.replay.start_record(destination,7).ok,"record case")
			for t in 240:
				await frame(input_for(case_number,t))
				trace.store_line(JSON.stringify({"tick":t+1,"input":view.actions.last_frame,"stick":view.actions.get_move().length(),"velocity":view.replay.vec(view.player.velocity),"position":view.replay.vec(view.player.position),"yaw":view.player.facing_yaw,"edges":view.actions.edges},"",true,true))
			trace.close()
			check(view.replay.stop_record().ok,"finish case")
			if case_number==8: check(dummy.accepted==["buffer3","coyote4"],"R08 precise windows once "+str(dummy.accepted))
			if case_number==9: check(view.actions.get_move()==Vector2.ZERO,"R09 released chord no sticky move")
			if case_number==10:
				check(dummy.hits==3 and dummy.damage==0,"R10 dummy swing counts and fifteen-tick dodge window")
				check(dummy.retry_tick>=0 and dummy.retry_tick-90<=90,"R10 dummy single-input retry within 1.5s")
			var movie: Dictionary = Wire.read_json(destination)
			var hashes := []
			for repeat in 2:
				check(view.replay.begin_playback(movie,false).ok,"playback case")
				for t in 250:
					await physics_frame; await process_frame
					if view.replay.finished: break
				check(view.replay.result.get("ok",false),"R%02d playback %s %s" % [case_number,preset,str(view.replay.result)])
				hashes.append(view.replay.result.duplicate(true))
			check(hashes[0]==hashes[1],"two runs exact")
			receipts.append({"preset":preset,"case":"R%02d"%case_number,"path":ProjectSettings.globalize_path(destination),"ticks":movie.frames.size(),"equal":hashes[0]==hashes[1] and hashes[0].get("ok",false),"scope":"test dummy only" if case_number==10 else "production provider/movie"})
	var f:=FileAccess.open("res://../matrix-results.json",FileAccess.WRITE); f.store_string(JSON.stringify({"failures":failures,"cases":receipts},"\t",true)); f.close()
	print("CONTROLS MATRIX cases=",receipts.size()," failures=",JSON.stringify(failures))
	await view.quit_cleanly(0 if failures.is_empty() else 1)
